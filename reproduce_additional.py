"""Recompute small additions, loading plateaus, causal filters and manual pairs."""
from pathlib import Path
from functools import lru_cache
import csv
import json
import numpy as np
from data_access import raw_path, open_raw

ROOT = Path(__file__).resolve().parent
G = 0.00980665

def read(name):
    return json.loads((ROOT / 'analysis' / (name+'.json')).read_text(encoding='utf-8'))

@lru_cache(maxsize=40)
def hall(cid):
    return np.loadtxt(raw_path(cid), delimiter=',', skiprows=1, usecols=(1,2,3,4,5,6))

def static(cid):
    a=hall(cid)
    # Original R protocol uses the final 1000 scans, with the final aperture
    # extended by one 10 ms scan period to define the half-open window.
    end=a[-1,1]+10000
    window=a[a[:,1]>=end-10e6,2:]
    assert len(window)==1000
    return window.mean(axis=0)

results={}
for name in ['R_small','R_range']:
    rows=read(name)['pairs']
    for r in rows:
        before=static(r['before_id']); loaded=static(r['loaded_id']); after=static(r['after_id'])
        w=r['interpolation_weight']
        q=before*(1-w)+after*w-loaded
        np.testing.assert_allclose(q,r['response_adc'][:4],atol=1e-8,rtol=0)
        assert abs(q.mean()-r['response_adc'][4])<1e-8
    results[name+'_pairs_verified']=len(rows)

e=read('E'); a=hall(e['capture_id']); t=a[:,1]/1e6; x=a[:,2:]
for cycle in e['cycles']:
    window=x[(t>=cycle['plateau_start_s'])&(t<cycle['plateau_end_s'])]
    assert len(window)==cycle['plateau_samples']
    np.testing.assert_allclose(window.mean(axis=0),cycle['channel_mean_adc'],atol=1e-8,rtol=0)
    np.testing.assert_allclose(window.std(axis=0,ddof=1),cycle['channel_sd_adc'],atol=1e-8,rtol=0)
results['loading_plateaus_verified']=len(e['cycles'])

def filt(x, kind, value=None):
    if kind=='raw': return x.copy()
    if kind=='ema':
        y=np.empty_like(x); y[0]=x[0]
        for i in range(1,len(x)): y[i]=value*x[i]+(1-value)*y[i-1]
        return y
    n=int(value); y=np.full_like(x,np.nan)
    cs=np.vstack([np.zeros(x.shape[1]),np.cumsum(x,axis=0)])
    y[n-1:]=(cs[n:]-cs[:-n])/n
    return y

settings=[('Raw','raw',None),('EMA 0.10','ema',.1),('EMA 0.25','ema',.25),
          ('EMA 0.50','ema',.5),('MA 8','ma',8),('MA 32','ma',32)]
stored=read('filter_results')['filters']; filters=[]
for (label,kind,value),expected in zip(settings,stored):
    assert label==expected['filter']
    y=filt(x,kind,value); channel_sd=[]; mean_sd=[]
    for cycle,summary in zip(e['cycles'],expected['cycles']):
        w=y[(t>=cycle['plateau_start_s'])&(t<cycle['plateau_end_s'])]
        sd=w.std(axis=0,ddof=1); msd=w.mean(axis=1).std(ddof=1)
        np.testing.assert_allclose(sd,summary['channel_sd_adc'],atol=1e-8,rtol=0)
        assert abs(msd-summary['mean_signal_sd_adc'])<1e-8
        channel_sd.extend(sd); mean_sd.append(msd)
    step=np.vstack([np.zeros((1000,1)),np.ones((1000,1))])
    t90=float(np.where(filt(step,kind,value)[1000:,0]>=.9)[0][0]/100)
    assert abs(t90-expected['synthetic_step_t90_s'])<1e-12
    assert abs(np.median(channel_sd)-expected['median_channel_sd_adc'])<1e-8
    assert abs(np.median(mean_sd)-expected['median_mean_signal_sd_adc'])<1e-8
    filters.append(dict(filter=label,median_mean_SD_ADC=float(np.median(mean_sd)),t90_s=t90))
results['filters']=filters

# The earlier 18 manual comparisons are numerical display-versus-reported-scale
# pairs. They are not the deliberately directional 15-press series.
all_errors=[]
for path in sorted((ROOT/'analysis').glob('manual_*.json')):
    cid=path.stem.removeprefix('manual_'); a=hall(cid)
    with open_raw(cid,'display.csv') as f:
        frames=list(csv.DictReader(f))
    for pair in json.loads(path.read_text(encoding='utf-8'))['pairs']:
        matching=[r for r in frames if int(r['first_seq'])==pair['first_seq'] and int(r['last_seq'])==pair['last_seq']]
        assert len(matching)==1
        frame=matching[0]
        window=a[(a[:,0]>=pair['first_seq'])&(a[:,0]<=pair['last_seq']),2:]
        assert len(window)==int(frame['count'])
        assert int(window.sum())==int(frame['sum_adc'])
        mass=float(frame['mass_mg'])/1000
        assert abs(mass-pair['recorded_device_g'])<1e-9
        error=mass-pair['reported_scale_indication_g']
        assert abs(error-pair['device_minus_reported_scale_g'])<1e-9
        all_errors.append(error)
assert len(all_errors)==18 and sum(e<0 for e in all_errors)==15
results['manual_pairs']=dict(n=len(all_errors),device_lower=sum(e<0 for e in all_errors))
print(json.dumps(results,indent=2))
