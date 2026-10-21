"""Reproduce all channel comparisons and error correlations from packaged raw data.

Read-only: fits additional models in memory using A only; does not replace frozen
models, tune on B, or modify any measurement or result file.
"""
from pathlib import Path
import csv, json
import numpy as np
from data_access import open_raw
from force_analysis.models import Calibrator

ROOT=Path(__file__).resolve().parent
def read(rel):return json.loads((ROOT/rel).read_text(encoding='utf8'))
expected=read('analysis/channel_comparison.json')
a=read('analysis/A_calibration_observations.json')
b=read('analysis/B.json')['observations']
windows={r['capture_id']:r for r in read('analysis/static_windows.json')}
cache={}
def mean(cid):
    if cid not in cache:
        lo,hi=windows[cid]['window_s']
        with open_raw(cid) as f:
            rows=[r for r in csv.DictReader(f) if lo*1e6<=int(r['t_us'])<hi*1e6]
        assert rows,cid
        cache[cid]=np.mean([[int(r[f's{i}_adc']) for i in range(1,5)] for r in rows],axis=0)
        np.testing.assert_allclose(cache[cid],windows[cid]['mean_adc'],atol=1e-9,rtol=0)
    return cache[cid]
def response(obs,zkey):
    q=mean(obs[zkey])-mean(obs['capture_id'])
    np.testing.assert_allclose(q,obs['response_adc'],atol=1e-9,rtol=0)
    return q
qa=np.array([response(r,'preceding_zero_capture_id') for r in a])
qb=np.array([response(r,'zero_capture_id') for r in b])
mass_a=np.array([r['mass_g'] for r in a]); levels=sorted(set(mass_a))
anchors=np.vstack([np.zeros(4)]+[qa[mass_a==m].mean(axis=0) for m in levels])
y=np.array([0]+levels)*.00980665
assert len(a)==24 and len(anchors)==13 and len(b)==23
for m in levels:assert np.count_nonzero(mass_a==m)==2
stored=read('analysis/channel_predictions.json')
by_model={k:{r['capture_id']:r for r in stored if r['model']==k} for k in expected['results']}
predictions={};results={}
def metrics(rows):
    es=np.array([v for v in rows if v is not None])
    return {'n':len(es),'MAE_N':float(np.mean(abs(es))),'RMSE_N':float(np.sqrt(np.mean(es*es))),'bias_N':float(np.mean(es))}
for channels in expected['subsets']:
    ix=np.array(channels)-1; name='_'.join(f'S{i}' for i in channels)
    x=anchors[:,ix].mean(axis=1);q=qb[:,ix].mean(axis=1)
    for family,spec in expected['model_rules'].items():
        key=name+'_'+family;ref=expected['results'][key]
        try:model=Calibrator.fit(x,y,spec)
        except ValueError:
            assert ref['status']=='not_applicable',key
            results[key]={'status':'not_applicable','coverage':0};continue
        assert ref['status']=='fitted'
        prediction=model.predict(q); errors={}
        for obs,p in zip(b,prediction):
            old=by_model[key][obs['capture_id']]
            assert p['status']==old['status']
            e=None if p['value_N'] is None else p['value_N']-obs['mass_g']*.00980665
            if e is not None:assert abs(e-old['error_N'])<1e-8,(key,obs['capture_id'])
            errors[obs['capture_id']]=e
        predictions[key]=errors
        m=metrics(errors.values())
        assert m['n']==ref['coverage_n']
        for metric in ['MAE_N','RMSE_N','bias_N']:assert abs(m[metric]-ref['metrics'][metric])<1e-8
        results[key]={'status':'fitted','coverage':m['n'],'own_metrics':m}
common=set.intersection(*({cid for cid,e in p.items() if e is not None} for k,p in predictions.items() if k.endswith('_cubic')))
assert common==set(expected['common_capture_ids']) and len(common)==22
for key,prediction in predictions.items():
    m=metrics(prediction[cid] for cid in sorted(common))
    for metric in ['MAE_N','RMSE_N','bias_N']:assert abs(m[metric]-expected['results'][key]['common_metrics'][metric])<1e-8
    results[key]['common_metrics']=m
errors=np.array([[predictions[f'S{i}_cubic'][cid] for cid in sorted(common)] for i in range(1,5)])
matrix=np.corrcoef(errors)
np.testing.assert_allclose(matrix,expected['correlation']['matrix'],atol=1e-10,rtol=0)
print(json.dumps({'status':'pass','raw_windows_recomputed':len(cache),'calibration_placements':len(a),
                  'test_placements':len(b),'common_n':len(common),'models':results,
                  'single_channel_error_correlation':matrix.tolist()},indent=2))
