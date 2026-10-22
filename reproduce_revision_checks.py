"""Revision checks derived from packaged data and frozen models.

1. Off-center change by channel configuration (position blocks, each configuration's own
   A-fitted cubic calibration; primary four-channel interpolation for reference).
2. Allan deviation of the raw-count mean at 10 s in the unloaded one-hour hold.
3. Seed sensitivity of the four-channel MLP (13 A anchors, held-out B).
4. Book-cycle unloaded return converted to force.
5. Local response-to-force sensitivity of the primary anchors.
6. Expected small-addition responses at the 619 g base from the primary anchors.

Run: python reproduce_revision_checks.py           (compare with analysis/revision_checks.json)
     python reproduce_revision_checks.py --write   (regenerate the stored file)
Read-only for raw data and models.
"""
from pathlib import Path
import argparse, json
import numpy as np
from data_access import raw_path
from force_analysis.models import Calibrator

ROOT = Path(__file__).resolve().parent
G = 0.00980665
def read(rel): return json.loads((ROOT/rel).read_text(encoding='utf-8'))

def load(rel): return Calibrator.load(ROOT/rel)

def value(model, q):
    z = model.predict([float(q)])[0]
    return z['value_N'] if z['status'] == 'ok' else None

def inverse(model, force_N):
    lo, hi = model.state['bounds']
    a, b = lo, hi
    fa = value(model, a) - force_N
    for _ in range(200):
        m = 0.5*(a+b); fm = value(model, m) - force_N
        if (fa <= 0) == (fm <= 0): a, fa = m, fm
        else: b = m
    return 0.5*(a+b)

result = {}

# 1. Off-center change by configuration.
d = read('analysis/D.json')['position_effects']
configs = {'S1': [1], 'S2': [2], 'S3': [3], 'S4': [4], 'S1/S3': [1, 3], 'S2/S4': [2, 4], 'S1/S2/S3/S4': [1, 2, 3, 4]}
files = {'S1': 'S1_cubic', 'S2': 'S2_cubic', 'S3': 'S3_cubic', 'S4': 'S4_cubic',
         'S1/S3': 'S1_S3_cubic', 'S2/S4': 'S2_S4_cubic', 'S1/S2/S3/S4': 'S1_S2_S3_S4_cubic'}
position = {}
def summarize(model, chans):
    out = {}
    for mass in (542, 1042):
        q0 = inverse(model, mass*G); changes = []; rejected = 0
        for r in d:
            if r['reference_mass_g'] != mass: continue
            dq = float(np.mean([r['channel_delta_from_center_adc'][i-1] for i in chans]))
            v = value(model, q0+dq)
            if v is None: rejected += 1; continue
            changes.append(v-mass*G)
        c = np.array(changes)
        out[str(mass)] = {'n': len(c), 'rejected': rejected, 'rms_N': float(np.sqrt(np.mean(c*c))),
                          'max_abs_N': float(np.max(abs(c)))}
    return out
for name, chans in configs.items():
    position[name+' cubic'] = summarize(load(f"models/additional_channels/{files[name]}.json"), chans)
position['S1/S2/S3/S4 interpolation (primary)'] = summarize(load('models/S1_S2_S3_S4_interpolation.json'), [1, 2, 3, 4])
assert abs(position['S1/S2/S3/S4 interpolation (primary)']['1042']['max_abs_N']-4.443) < 1e-3
result['position_by_configuration'] = position

# 2. Allan deviation at 10 s, unloaded one-hour hold.
f = read('analysis/F.json')['unloaded']
a = np.loadtxt(raw_path(f['capture_id'], 'samples.csv'), delimiter=',', skiprows=1, usecols=(2, 3, 4, 5, 6))
t = a[:, 0]/1e6; raw = a[:, 1:].mean(axis=1)
means = np.array([raw[(t >= k*10) & (t < (k+1)*10)].mean() for k in range(int(t[-1]//10))])
adev = float(np.sqrt(0.5*np.mean(np.diff(means)**2)))
slope = read('analysis/stability.json')['first_segment_slope_N_per_ADC']
result['allan_deviation_10s'] = {'windows': len(means), 'adc': adev, 'N': adev*slope}

# 3. MLP seed sensitivity.
frozen = load('models/S1_S2_S3_S4_mlp8.json')
spec = dict(frozen.state['spec'])
anchors = read('analysis/A_calibration_anchors.json')
b = read('analysis/B.json')
rows = b['predictions']['S1_S2_S3_S4_mlp8']
x_anchor = np.array([np.mean(r['response_adc']) for r in anchors]); y_anchor = np.array([r['force_N'] for r in anchors], dtype=float)
assert np.allclose(x_anchor, frozen.state['bounds'][0]+0*x_anchor) is False
q = [r['feature_adc'] for r in rows]; truth = np.array([r['mass_g']*G for r in rows])
interp_mae = float(np.mean(abs(np.array([r['predicted_force_N'] for r in b['predictions']['S1_S2_S3_S4_interpolation']])-truth)))
maes = []
for seed in range(30):
    s = dict(spec); s['seed'] = seed
    m = Calibrator.fit(x_anchor, y_anchor, s)
    p = np.array([z['value_N'] for z in m.predict(q)], dtype=float)
    maes.append(float(np.mean(abs(p-truth))))
result['mlp_seed_sensitivity'] = {'seeds': 30, 'mae_N_min': min(maes), 'mae_N_median': float(np.median(maes)),
                                  'mae_N_max': max(maes), 'below_interpolation': int(sum(m < interp_mae for m in maes)),
                                  'interpolation_mae_N': interp_mae}

# 4. Book-cycle unloaded return.
primary = load('models/S1_S2_S3_S4_interpolation.json')
result['book_cycle_return_N'] = [value(primary, c['q'][-1]) for c in read('analysis/C_selected.json')['cycles'] if c['included']]

# 5. Local sensitivity of the primary anchors (ADC counts per N).
xs = np.array(primary.state['x_knots']); ys = np.array(primary.state['y_knots_N'])
masses = np.round(ys/G).astype(int).tolist()
result['local_sensitivity_adc_per_N'] = [{'from_g': masses[i], 'to_g': masses[i+1], 'adc_per_N': float((xs[i+1]-xs[i])/(ys[i+1]-ys[i]))}
                                         for i in range(len(xs)-1)]

# 6. Expected small-addition responses at 619 g base.
q619 = inverse(primary, 619*G)
result['expected_small_addition_adc'] = {str(m): float(inverse(primary, (619+m)*G)-q619) for m in (54, 100)}

parser = argparse.ArgumentParser(); parser.add_argument('--write', action='store_true'); args = parser.parse_args()
path = ROOT/'analysis/revision_checks.json'
if args.write:
    path.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
else:
    stored = read('analysis/revision_checks.json')
    def close(u, v):
        if isinstance(u, dict): return set(u) == set(v) and all(close(u[k], v[k]) for k in u)
        if isinstance(u, list): return len(u) == len(v) and all(close(i, j) for i, j in zip(u, v))
        if isinstance(u, float): return abs(u-v) < 1e-9
        return u == v
    assert close(result, stored), 'Recomputed values differ from analysis/revision_checks.json'
print(json.dumps(result, indent=2))
