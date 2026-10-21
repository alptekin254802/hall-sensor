"""Reproduce the primary and paired-model mass-group bootstrap intervals.

The paired calculation preserves the original implementation: Python's
random.Random, sorted mass groups, choices with replacement, a fresh seed for
each alternative, and the 250th and 9750th sorted draws (one-based ranks).
Primary intervals preserve NumPy default_rng and linear percentile extraction.
All placements at a sampled mass remain together, and models are never refitted.
"""
from pathlib import Path
import argparse, json, random, statistics as st
import numpy as np
from bootstrap_settings import (REPLICATES, PRIMARY_MASS_GROUP_SEED,
    PAIRED_MODEL_MASS_GROUP_SEED, PERCENTILE_LIMITS, PAIRED_ORDER_INDICES)

ROOT=Path(__file__).resolve().parent
G=0.00980665

def calculate():
    b=json.loads((ROOT/'analysis/B.json').read_text(encoding='utf-8'))
    base=b['predictions']['S1_S2_S3_S4_interpolation']
    assert len(base)==23 and len({p['capture_id'] for p in base})==23
    masses=sorted({p['mass_g'] for p in base})
    groups=[[p['error_g'] for p in base if p['mass_g']==m] for m in masses]
    rng=np.random.default_rng(PRIMARY_MASS_GROUP_SEED); boots=[]
    for _ in range(REPLICATES):
        errors=np.concatenate([groups[i] for i in rng.integers(0,len(groups),len(groups))])
        boots.append([np.mean(abs(errors)),np.sqrt(np.mean(errors**2))])
    intervals=np.percentile(boots,PERCENTILE_LIMITS,axis=0).T
    result={'primary':dict(seed=PRIMARY_MASS_GROUP_SEED,replicates=REPLICATES,
        mass_groups=len(masses),placements=len(base),generator='numpy.random.default_rng',
        percentile_rule='numpy.percentile, method=linear',
        intervals_g=dict(zip(['mae','rmse'],intervals.tolist())),
        intervals_N=dict(zip(['mae','rmse'],(intervals*G).tolist()))),'paired':{}}
    for name in ['S1_S2_S3_S4_mlp8','S1_S2_S3_S4_cubic']:
        alt={p['capture_id']:p for p in b['predictions'][name]}
        assert set(alt)=={p['capture_id'] for p in base}
        groups={}
        for p in base:
            groups.setdefault(p['mass_g'],[]).append((abs(alt[p['capture_id']]['error_g'])-abs(p['error_g']))*G)
        masses=sorted(groups); rng=random.Random(PAIRED_MODEL_MASS_GROUP_SEED)
        draws=sorted(st.mean([x for m in rng.choices(masses,k=len(masses)) for x in groups[m]]) for _ in range(REPLICATES))
        result['paired'][name]=dict(estimand='alternative MAE minus interpolation MAE',
            observed_difference_N=st.mean([x for g in groups.values() for x in g]),
            percentile95_N=[draws[i] for i in PAIRED_ORDER_INDICES],
            seed=PAIRED_MODEL_MASS_GROUP_SEED,replicates=REPLICATES,mass_groups=len(masses),
            placements=len(base),generator='random.Random, fresh seed per alternative',
            percentile_rule='sorted draw indices 249 and 9749 (zero-based)',
            scope='Conditional on observed masses and frozen fits; exploratory, no retuning, no population equivalence claim.')
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true',help='Write the derived summary')
    args=parser.parse_args(); result=calculate()
    path=ROOT/'analysis/bootstrap_intervals.json'
    if args.write:path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    elif path.exists():
        stored=json.loads(path.read_text(encoding='utf-8'))
        for metric in ('mae','rmse'):
            np.testing.assert_allclose(result['primary']['intervals_N'][metric],stored['primary']['intervals_N'][metric],rtol=0,atol=1e-12)
        for name,row in result['paired'].items():
            np.testing.assert_allclose(row['percentile95_N'],stored['paired'][name]['percentile95_N'],rtol=0,atol=1e-12)
            assert abs(row['observed_difference_N']-stored['paired'][name]['observed_difference_N'])<1e-12
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
