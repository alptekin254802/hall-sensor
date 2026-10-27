"""Reproduce principal numerical results from this research-data package.

Run: python reproduce.py
Requires numpy. Never opens hardware or modifies the supplied data/models.
"""
from pathlib import Path
from data_access import raw_path, open_raw
import csv, hashlib, json
import numpy as np
from force_analysis.models import Calibrator

ROOT=Path(__file__).resolve().parent
G=0.00980665
SPAN=5000*G
def read(p): return json.loads((ROOT/p).read_text(encoding='utf-8'))
def report(name): return read('analysis/'+name+'.json')
def metrics(errors):
    e=np.asarray(errors,float)
    return {'n':len(e),'mae_N':float(np.mean(abs(e))), 'rmse_N':float(np.sqrt(np.mean(e*e)))}
cache={}
def mean_raw(cid,window=(10,20)):
    key=(cid,tuple(window))
    if key not in cache:
        with open_raw(cid, 'samples.csv') as f:
            data=[[float(row['t_us'])/1e6]+[float(row[f's{i}_adc']) for i in range(1,5)] for row in csv.DictReader(f)]
        data=np.asarray(data); t=data[:,0]
        keep=(t>=window[0])&(t<window[1])
        assert np.any(keep),(cid,window)
        cache[key]=data[keep,1:].mean(axis=0)
    return cache[key]

ANONYMIZED_AUTHOR_FILES = frozenset({'CITATION.cff', 'LICENSE', 'DATA_LICENSE.md'})
manifest=read('manifest.json')
for f in manifest['files']:
    path = ROOT/f['path']
    assert path.is_file(), f['path']
    if f['path'] in ANONYMIZED_AUTHOR_FILES:
        continue
    assert hashlib.sha256(path.read_bytes()).hexdigest()==f['sha256'], f['path']
print('Author names may be masked in anonymous copies; CITATION.cff, LICENSE and '
      'DATA_LICENSE.md are checked for presence only. All other integrity checks remain unchanged.')

model=Calibrator.load(ROOT/'models/S1_S2_S3_S4_interpolation.json')
state=read('models/S1_S2_S3_S4_interpolation.json')['state']
x=np.array(state['x_knots']); y=np.array(state['y_knots_N'])
def force(q):
    z=model.predict([float(q)])[0]
    assert z['status']=='ok',(q,z)
    return z['value_N']

b=report('B'); errs=[]
for obs in b['observations']:
    response=mean_raw(obs['zero_capture_id'])-mean_raw(obs['capture_id'])
    assert np.allclose(response,obs['response_adc'],atol=1e-9,rtol=0)
    errs.append(force(response.mean())-obs['mass_g']*G)
result={'B_from_raw':metrics(errs),'files_verified':len(manifest['files'])}
assert abs(result['B_from_raw']['mae_N']-0.6056428193524245)<1e-10
assert abs(result['B_from_raw']['rmse_N']-0.7727596633597605)<1e-10

# Verify all frozen central model predictions, without refitting or selecting a model.
count=0
for name,rows in b['predictions'].items():
    m=Calibrator.load(ROOT/'models'/(name+'.json'))
    for row,new in zip(rows,m.predict([r['feature_adc'] for r in rows])):
        if row['predicted_force_N'] is None: assert new['value_N'] is None
        else: assert abs(new['value_N']-row['predicted_force_N'])<1e-9
        count+=1
result['B_model_predictions_verified']=count

c=report('C_cycle1');c3=report('C_cycle2');result['C_max_pair_N']=[]
for pairs in (c['paired_levels'], c3['paired_levels']):
    result['C_max_pair_N'].append(max(abs(force(p['unloading_response_adc'])-force(p['loading_response_adc'])) for p in pairs))

d=report('D'); result['D_max_center_change_N']={}
for mass in (542,1042):
    result['D_max_center_change_N'][str(mass)]={}
    q0=np.interp(mass*G,y,x)
    for offset in (5,10,15,20):
        rows=[r for r in d['position_effects'] if r['reference_mass_g']==mass and max(abs(r['x_mm']),abs(r['y_mm']))==offset]
        result['D_max_center_change_N'][str(mass)][str(offset)]=max(abs(force(q0+r['mean_delta_from_center_adc'])-mass*G) for r in rows)

f=report('F'); loaded=f['loaded']; duration=loaded['duration_s']
start=loaded.get('analysis_start_s',0.0)  # first 4 min contained a step change
first=mean_raw(loaded['capture_id'],(start,start+60))
# The source report includes the boundary at max(t)-60.
with open_raw(loaded['capture_id'], 'samples.csv') as stream:
    tail=[ [float(row[f's{i}_adc']) for i in range(1,5)] for row in csv.DictReader(stream) if float(row['t_us'])/1e6>=duration-60]
last=np.mean(tail,axis=0)
assert np.allclose(first,loaded['first_60s_mean_adc'],atol=1e-9,rtol=0)
assert np.allclose(last,loaded['last_60s_mean_adc'],atol=1e-9,rtol=0)
q0=np.interp(1042*G,y,x)
result['F_loaded_endpoint_change_N']=force(q0+float(np.mean(first-last)))-1042*G

t=report('T');result['T']={}
for color in ('blue','red'):
    info=t[color]; result['T'][color]={}
    for method,rows in info['predictions'].items():
        errors=[]
        for row in rows:
            q=row['feature_adc']
            if method=='no_transfer': predicted=force(q)/G
            else:
                spec=info['models'][method]
                assert spec['target_response_adc'][0]<=q<=spec['target_response_adc'][-1]
                if method.startswith('source_inverse_warp'):
                    predicted=force(np.interp(q,spec['target_response_adc'],spec['green_response_adc']))/G
                else: predicted=float(np.interp(q,spec['target_response_adc'],spec['mass_g']))
            assert abs(predicted-row['predicted_mass_g'])<1e-8
            errors.append((predicted-row['mass_g'])*G)
        result['T'][color][method]=metrics(errors)
    result['T'][color]['observed_ratio_median']=float(np.median([r['mass_g']/r['predicted_mass_g'] for r in info['predictions']['no_transfer']]))


# Appended to the portable principal-result reproduction script.
# All operations below are read-only on supplied measurements/models.
from functools import lru_cache

@lru_cache(maxsize=8)
def raw_hall(cid):
    # seq, device time, S1-S4
    return np.loadtxt(raw_path(cid, "samples.csv"),delimiter=",",skiprows=1,usecols=(1,2,3,4,5,6))

for r in report("static_windows"):
    got=mean_raw(r["capture_id"],r["window_s"])
    np.testing.assert_allclose(got,r["mean_adc"],atol=1e-8,rtol=0)
result["static_windows_recomputed"]=len(report("static_windows"))
for name,rows,zkey in [
    ("A",report("A_calibration_observations"),"preceding_zero_capture_id"),
    ("A_REFINE",report("A_REFINE")["observations"],"preceding_zero_capture_id"),
    ("T",report("T")["observations"],"zero_capture_id")]:
    sw={r["capture_id"]:r["window_s"] for r in report("static_windows")}
    for r in rows:
        q=mean_raw(r[zkey],sw[r[zkey]])-mean_raw(r["capture_id"],sw[r["capture_id"]])
        np.testing.assert_allclose(q,r["response_adc"],atol=1e-8,rtol=0)
    result[name+"_responses_recomputed"]=len(rows)

# Recompute the selected stack trajectories from the unchanged raw recordings.
c=report("C_selected")
for j,cy in enumerate(c["cycles"]):
    assert cy["cycle"] == j + 1
    ids=c["capture_ids_in_sequence"][7*j:7*j+7]
    z=mean_raw(ids[0],(20,50)).mean()
    q=[0]+[z-mean_raw(cid).mean() for cid in ids[1:]]
    np.testing.assert_allclose(q,cy["q"],atol=1e-8,rtol=0)
    maximum=max(abs(force(q[b])-force(q[a])) for a,b in [(1,5),(2,4)])
    assert abs(maximum-cy["max_N"])<1e-9
    assert abs((q[3]-q[2])-cy["final_increment_adc"])<1e-8

# Excluded book-stack cycle (not used in reported results): final 619 g increment.
cx=report("C_excluded"); ids=cx["capture_ids_in_sequence"]
z=mean_raw(ids[0]).mean()
qx=[0]+[z-mean_raw(cid).mean() for cid in ids[1:]]
np.testing.assert_allclose(qx,cx["q"],atol=1e-8,rtol=0)
assert abs((qx[3]-qx[2])-cx["final_increment_adc"])<1e-8
result["C_final_increment_adc"]={"analyzed_cycles":[cy["final_increment_adc"] for cy in c["cycles"]],"excluded_cycle":qx[3]-qx[2]}

# E: final unloaded mean minus initial unloaded mean.
e=report("E"); zr=e["zero_return"]
ez=(mean_raw(e["capture_id"],zr["final_window_s"])-mean_raw(e["capture_id"],zr["initial_window_s"])).mean()
assert abs(ez-zr["final_minus_initial_four_channel_mean_adc"])<1e-9
result["E_final_minus_initial_adc"]=ez

# H: counts-to-mass verification on calibration, all tests and common tests.
h=report("H"); hm=read("models/H_loadcell.json")
hslope=hm["mass_g_per_count"]
for rows,zfield in [(h["calibration_records"],hm["calibration_zero_counts"]),
                    (h["test_records"],h["test_zero_counts"])]:
    for r in rows:
        a=np.loadtxt(raw_path(r["capture_id"], "samples.csv"),delimiter=",",skiprows=1,usecols=(1,4))
        w=r.get("window_s",r.get("analysis_window_s"))
        got=a[(a[:,0]>=w[0])&(a[:,0]<w[1]),1].mean()
        expected=r.get("mean_counts",r.get("analysis_mean_counts"))
        assert abs(got-expected)<1e-7,(r["capture_id"],got,expected)
        assert abs(hslope*(got-zfield)-r["predicted_g"])<1e-6
result["H_common_from_raw"]=metrics([r["loadcell_error_N"] for r in h["matched_pairs"]])

# Nextion: exact source sums and readout agreement for every stored frame.
cid="586aec83cda84995bf66d52770ef569b"
aa=raw_hall(cid); byseq={int(r[0]):r[2:] for r in aa}
with open_raw(cid, "display.csv") as stream:
    frames=list(csv.DictReader(stream))
max_error_mg=0
for r in frames:
    counts=np.array([byseq[k] for k in range(int(r["first_seq"]),int(r["last_seq"])+1)])
    assert len(counts)==int(r["count"])
    assert int(counts.sum())==int(r["sum_adc"])
    q=(int(r["zero_sum_adc"])-int(r["sum_adc"]))/(4*int(r["count"]))
    estimate=np.interp(q,x,y) if q>=0 else q*y[1]/x[1]
    max_error_mg=max(max_error_mg,abs(estimate/G*1000-int(r["mass_mg"])))
assert len(frames)==369 and max_error_mg<10
result["Nextion"]={"frames_with_exact_raw_sum":len(frames),"max_numerical_difference_mg":max_error_mg}

# Deliberate directional test: each prespecified sequence window, all 15 trials.
dp=report("directional_press")
for trial in dp["trials"]:
    a=raw_hall(trial["capture_id"]); means={}
    for mode in ["baseline","primary","sensitivity_3s"]:
        w=trial["windows"][mode]
        rows=a[(a[:,0]>=w["first_seq"])&(a[:,0]<=w["last_seq"]),2:]
        assert len(rows)==w["n"]
        means[mode]=rows.mean(axis=0)
        np.testing.assert_allclose(means[mode],w["mean_adc"],atol=1e-9,rtol=0)
    for mode in ["primary","sensitivity_3s"]:
        r=means["baseline"]-means[mode]
        Q=np.linalg.norm([r[1]-r[3],r[2]-r[0]])
        assert abs(Q-trial[mode]["Q_adc"])<1e-8
result["directional_raw_windows_verified"]=15*3

# Fixed 774 g endpoints, including the separately measured final zero.
g=report("G774"); ep=g["endpoints"]
def tail(cid,seconds,inclusive=True):
    a=raw_hall(cid)
    mask=a[:,1]>=a[-1,1]-seconds*1e6 if inclusive else a[:,1]>a[-1,1]-seconds*1e6
    return a[mask,2:].mean()
z0=tail(ep["initial_zero_capture"],600)
z1=tail(ep["final_unloaded_capture"],10,False)
assert abs(z0-ep["initial_zero_mean_adc"])<1e-8
assert abs(z1-ep["final_unloaded_mean_adc"])<1e-8
gout={}
for seconds in [10,60,600]:
    initial=force(z0-tail(ep["initial_loaded_capture"],seconds))
    final=force(z1-tail(ep["final_loaded_capture"],seconds))
    fixed=force(z0-tail(ep["final_loaded_capture"],seconds))
    expected=g["verified_force_results"][f"last{seconds}s"]
    assert abs((final-initial)-expected["local_difference_N"])<1e-8
    assert abs((fixed-initial)-expected["fixed_difference_N"])<1e-8
    gout[f"{seconds}s"]={"new_zero_difference_N":final-initial,"fixed_zero_difference_N":fixed-initial}
result["G774_endpoints_from_raw"]=gout
kg=report("G1000_check")
for r in kg["captures"]:
    a=raw_hall(r["capture_id"])
    w=a[(a[:,1]>=r["window_start_us"])&(a[:,1]<=r["window_end_us"]),2:]
    assert len(w)==r["window_samples"]
    expected=r["channel_mean_adc"]
    if isinstance(expected,dict):
        expected=list(expected.values())
    np.testing.assert_allclose(w.mean(axis=0),expected,atol=1e-8,rtol=0)
result["G1000_check_g"]=kg["primary_pre_load_reference"]["mass_equivalent_g"]

# Retained overnight interval, signed first-segment conversion.
ov=report("G_three_hour"); cid=ov["capture_id"]; a=raw_hall(cid)
assert len(a)==1080000
z=mean_raw(cid,(0,60)).mean()
end=a[a[:,1]>=a[-1,1]-60e6,2:].mean()
equivalent=(z-end)*ov["conversion"]["N_per_adc"]
assert abs(equivalent-ov["conversion"]["endpoint_mean_N"])<1e-8
result["three_hour_endpoint_N"]=equivalent
print(json.dumps(result,indent=2))
