"""Verify filter effects on static B accuracy and SX loading branches.

Run without arguments to compare with analysis/filter_effect.json.
Use --write to regenerate that derived file. Raw data and models are read-only.
"""
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np
import reproduce_synchronized as RS
from data_access import raw_path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'analysis/filter_effect.json'


def ema(x, a=0.25):
    y = np.empty_like(x)
    y[0] = x[0]
    for i in range(1, len(x)):
        y[i] = a*x[i] + (1-a)*y[i-1]
    return y


def ma(x, n=32):
    c = np.cumsum(np.insert(x, 0, 0.0))
    y = np.empty_like(x)
    for i in range(len(x)):
        j = max(0, i-n+1)
        y[i] = (c[i+1]-c[j])/(i+1-j)
    return y


def amean(cid, filt):
    a = np.loadtxt(raw_path(cid), delimiter=',', skiprows=1, usecols=(2, 3, 4, 5, 6))
    t = (a[:, 0]-a[0, 0])/1e6
    s = a[:, 1:5].mean(1)
    lo, hi = (20, 50) if t[-1] > 40 else (10, 20)
    w = (t >= lo) & (t < hi)
    assert w.any(), cid
    return (filt(s) if filt else s)[w].mean()


def compute():
    model = json.loads((ROOT/'models/S1_S2_S3_S4_interpolation.json').read_text(encoding='utf8'))['state']
    X, Y = np.array(model['x_knots']), np.array(model['y_knots_N'])
    F = lambda q: float(np.interp(q, X, Y))
    bj = json.loads((ROOT/'analysis/B.json').read_text(encoding='utf8'))
    pred = bj['predictions']['S1_S2_S3_S4_interpolation']
    static = {}
    for name, fl in (('EMA0.25', ema), ('MA32', ma)):
        errs0, errs1 = [], []
        for p in pred:
            q0 = float(np.mean(p['response_adc']))
            dz = amean(p['zero_capture_id'], fl)-amean(p['zero_capture_id'], None)
            da = amean(p['capture_id'], fl)-amean(p['capture_id'], None)
            q1 = q0+dz-da
            e0 = p['error_N']
            e1 = e0+F(q1)-F(q0)
            errs0.append(e0)
            errs1.append(e1)
        errs0, errs1 = np.array(errs0), np.array(errs1)
        assert np.isfinite(errs1).all()
        static[name] = dict(MAE0=float(np.mean(np.abs(errs0))),
                            MAE1=float(np.mean(np.abs(errs1))),
                            max_abs_change=float(np.max(np.abs(errs1-errs0))))

    spec = RS.PLAN['SX']['analysis']
    lag = json.loads((ROOT/'analysis/synchronized_press.json').read_text(encoding='utf8'))['SX']['lag_s_used']
    rows = []
    for rec in RS.PLAN['SX']['records']:
        _, th, xh = RS.read_hall(rec['hall_capture_id'])
        _, tl, cl = RS.read_lc(rec['loadcell_capture_id'])
        zh = xh[th < th[0]+spec['zero_s']].mean(axis=0)
        zl = cl[tl < tl[0]+spec['zero_s']].mean()
        Fl = RS.B*(cl-zl)*RS.G
        q = (zh-xh).mean(axis=1)
        qs = {'raw': q, 'EMA0.25': ema(q), 'MA32': ma(q)}
        k = np.ones(spec['smoothing_samples'])/spec['smoothing_samples']
        dF = np.gradient(np.convolve(Fl, k, 'same'), tl)
        half = spec['hall_half_window_s']
        for t, fl, rate in zip(tl, Fl, dF):
            if fl <= spec['min_force_N'] or rate <= spec['branch_threshold_N_per_s']:
                continue
            mwin = (th >= t+lag-half) & (th < t+lag+half)
            if not mwin.any():
                continue
            f = {key: RS.hall_force(float(v[mwin].mean())) for key, v in qs.items()}
            rows.append((rate, f['EMA0.25']-f['raw'], f['MA32']-f['raw'], fl))
    R = np.array(rows)
    assert len(R) and np.isfinite(R).all()
    filters = {}
    for i, name in ((1, 'EMA0.25'), (2, 'MA32')):
        d = R[:, i]
        sl = np.polyfit(R[:, 0], d, 1)
        filters[name] = dict(median_diff_N=float(np.median(d)),
                             p5_diff_N=float(np.percentile(d, 5)),
                             minimum_diff_N=float(d.min()),
                             implied_lag_s=float(-sl[0]))
    inputs = ['analysis/B.json', 'analysis/synchronized_press.json',
              'protocols/synchronized_press_plan.json',
              'models/S1_S2_S3_S4_interpolation.json', 'models/H_loadcell.json',
              'reproduce_synchronized.py']
    return dict(
        schema_version=1,
        static=dict(n_placements=len(pred), force_unit='N', filters=static,
                    mae_change_N={name: v['MAE1']-v['MAE0'] for name, v in static.items()},
                    method='Apply each causal filter to the full four-channel mean stream before the window mean; adjust the stored B error by F(q_filtered)-F(q_raw).',
                    windows='Relative to first t_us: [20,50) s for recordings longer than 40 s; otherwise [10,20) s.'),
        SX_loading=dict(n_points=len(R), lag_s_used=lag,
                        difference='filtered Hall force minus raw Hall force, in N',
                        rate_N_per_s=dict(median=float(np.median(R[:, 0])),
                                          p90=float(np.percentile(R[:, 0], 90)),
                                          maximum=float(R[:, 0].max())),
                        filters=filters, records=RS.PLAN['SX']['records'],
                        selection=dict(zero_s=spec['zero_s'], min_force_N=spec['min_force_N'],
                                       rate_threshold_N_per_s=spec['branch_threshold_N_per_s'],
                                       loadcell_smoothing_samples=spec['smoothing_samples'],
                                       hall_half_window_s=half)),
        filter_initialization=dict(EMA0_25='First output equals first input.',
                                   MA32='Trailing arithmetic mean; expanding window for the first 31 samples.'),
        input_sha256={name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in inputs})


def compare(actual, expected, path='result'):
    if isinstance(actual, dict):
        assert actual.keys() == expected.keys(), path
        for k in actual:
            compare(actual[k], expected[k], f'{path}.{k}')
    elif isinstance(actual, list):
        assert len(actual) == len(expected), path
        for i, (a, e) in enumerate(zip(actual, expected)):
            compare(a, e, f'{path}[{i}]')
    elif isinstance(actual, float):
        np.testing.assert_allclose(actual, expected, atol=1e-7, rtol=0, err_msg=path)
    else:
        assert actual == expected, path


def print_results(result):
    print('STATIC', json.dumps(result['static']['filters'], indent=1))
    sx = result['SX_loading']
    rate = sx['rate_N_per_s']
    print('DYNAMIC loading points', sx['n_points'],
          'rate N/s median %.1f p90 %.1f max %.1f' % (rate['median'], rate['p90'], rate['maximum']))
    for name, v in sx['filters'].items():
        print(name, 'median diff %.3f N  p5 %.3f  min %.3f  slope vs rate %.3f s (implied lag)' %
              (v['median_diff_N'], v['p5_diff_N'], v['minimum_diff_N'], v['implied_lag_s']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Regenerate analysis/filter_effect.json')
    args = parser.parse_args()
    result = compute()
    if args.write:
        OUTPUT.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf8')
    else:
        compare(result, json.loads(OUTPUT.read_text(encoding='utf8')))
    print_results(result)
