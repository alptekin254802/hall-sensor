"""Synchronized hand presses, static control and exploratory ramps on the strain-gauge load cell.

Specification: protocols/synchronized_press_plan.json (extracted from the frozen plans).
S   Five rounds of centered, tilted and 15 mm offset hand presses at about 2.5 kg and one
    centered sequence at about 1, 2 and 3 kg, recorded simultaneously by the Hall head and
    the load cell beneath it.
SC  Static control on the same assembly: 1000 and 2003 g placed twice, each with its
    preceding unloaded record. Added after the S analysis; its analysis was fixed before
    acquisition.
SX  Two exploratory records of slow hand ramps, reported descriptively.

Post hoc sensitivity (S): the Hall leads the load cell by a median rising-edge lag, so the planned
host-time windows let the Hall plateau window reach into its release. The same windows are also
evaluated with the Hall windows shifted by the median lag (key 'w1_lag_aligned').

Hall indications use the frozen primary interpolation (models/S1_S2_S3_S4_interpolation.json);
load-cell forces use the frozen comparator slope (models/H_loadcell.json).

Run: python reproduce_synchronized.py           (compare with analysis/synchronized_press.json)
     python reproduce_synchronized.py --write   (regenerate the stored file)
Read-only for raw data and models.
"""
from pathlib import Path
import argparse
import csv
import json
import numpy as np
from data_access import open_raw
from force_analysis.models import Calibrator

ROOT = Path(__file__).resolve().parent
G = 0.00980665
PLAN = json.loads((ROOT/'protocols/synchronized_press_plan.json').read_text(encoding='utf-8'))
HALL = Calibrator.load(ROOT/'models/S1_S2_S3_S4_interpolation.json')
B = json.loads((ROOT/'models/H_loadcell.json').read_text(encoding='utf-8'))['mass_g_per_count']
# Host timestamps are referenced to a fixed epoch (2026-10-21T16:26:40Z) before conversion to seconds, and
# device time is centered before the clock regression, so the regression is well conditioned and window
# membership does not depend on platform-specific rounding.
REF_NS = 1_792_600_000_000_000_000
TOL = 1e-7


def hall_force(q):
    z = HALL.predict([float(q)])[0]
    return z['value_N'] if z['status'] == 'ok' else float('nan')


def read_rows(cid):
    with open_raw(cid) as f:
        return list(csv.DictReader(f))


def host_time(t_dev, host):
    assert np.all(np.diff(t_dev) > 0), 'device clock not monotonic'
    x = t_dev-t_dev[0]
    a, b = np.polyfit(x, host, 1)
    return a*x+b


def read_hall(cid):
    rows = read_rows(cid)
    t_dev = np.array([int(r['t_us']) for r in rows])/1e6
    host = np.array([int(r['host_utc_ns'])-REF_NS for r in rows])/1e9
    x = np.array([[int(r[f's{i}_adc']) for i in range(1, 5)] for r in rows], float)
    return t_dev, host_time(t_dev, host), x


def read_lc(cid):
    rows = read_rows(cid)
    t_dev = np.array([int(r['device_micros']) for r in rows])/1e6
    host = np.array([int(r['host_utc_ns'])-REF_NS for r in rows])/1e9
    elapsed = np.array([float(r['elapsed_s']) for r in rows])
    counts = np.array([float(r['raw_counts']) for r in rows])
    return elapsed, host_time(t_dev, host), counts


def wmean(t, x, lo, hi):
    m = (t >= lo) & (t < hi)
    return x[m].mean(axis=0), int(m.sum())


def detect_presses(t, kg, rules):
    above = kg > rules['threshold_kg']
    spans, i = [], 0
    while i < len(kg):
        if above[i]:
            j = i
            while j+1 < len(kg) and above[j+1]:
                j += 1
            if t[j]-t[i] >= rules['min_duration_s']:
                spans.append((i, j))
            i = j+1
        else:
            i += 1
    out = []
    for i, j in spans:
        P = float(np.median(kg[i+(j-i)//4: j-(j-i)//4+1]))
        k = max(m for m in range(i, j+1) if kg[m] >= rules['release_fraction']*P)
        o = i
        while o > 0 and kg[o] > rules['onset_kg']:
            o -= 1
        out.append(dict(t_on=t[o], t_rel=t[k], P_kg=P, t_start=t[i]))
    return out


def rise_time(t, y, level):
    idx = np.where(y >= level)[0]
    return float(t[idx[0]]) if len(idx) else float('nan')


def med(v):
    return float(np.median(v)) if len(v) else float('nan')


def analyze_S():
    spec = PLAN['S']
    rules = spec['analysis']['press_detection']
    zero_s, gap_s = spec['analysis']['zero_window_s'], spec['analysis']['zero_gap_s']
    presses, cache = [], []
    for rec in spec['records']:
        _, th, xh = read_hall(rec['hall_capture_id'])
        _, tl, cl = read_lc(rec['loadcell_capture_id'])
        z0 = cl[tl < tl[0]+spec['analysis']['detection_zero_s']].mean()
        kg = B*(cl-z0)/1000
        found = detect_presses(tl, kg, rules)
        assert len(found) == len(rec['conditions']), (rec['code'], len(found))
        for n, (p, cond) in enumerate(zip(found, rec['conditions'])):
            out = dict(code=rec['code'], index=n+1, condition=cond, plateau_kg=p['P_kg'],
                       hold_s=p['t_rel']-p['t_start'])
            zh, nzh = wmean(th, xh, p['t_on']-zero_s-gap_s, p['t_on']-gap_s)
            zl, nzl = wmean(tl, cl, p['t_on']-zero_s-gap_s, p['t_on']-gap_s)
            for w in spec['analysis']['plateau_windows_s']:
                ph, nph = wmean(th, xh, p['t_rel']-w, p['t_rel'])
                pl, npl = wmean(tl, cl, p['t_rel']-w, p['t_rel'])
                r = zh-ph
                q = float(r.mean())
                F_h, F_l = hall_force(q), float(B*(pl-zl)*G)
                out[f'w{w}'] = dict(n_hall=nph, n_lc=npl, q_adc=q, hall_N=F_h, lc_N=F_l, diff_N=F_h-F_l,
                                    c24=float(r[1]-r[3]), c31=float(r[2]-r[0]),
                                    Q=float(np.hypot(r[1]-r[3], r[2]-r[0])))
            out['zero_samples'] = dict(hall=nzh, lc=nzl)
            sh = (th > p['t_on']-0.5) & (th < p['t_rel'])
            sl = (tl > p['t_on']-0.5) & (tl < p['t_rel'])
            qh = (zh-xh[sh]).mean(axis=1)
            ql = B*(cl[sl]-zl)
            pl1 = wmean(tl, cl, p['t_rel']-1, p['t_rel'])[0]
            out['lag_s'] = rise_time(th[sh], qh, 0.5*out['w1']['q_adc'])-rise_time(tl[sl], ql, 0.5*B*(pl1-zl))
            presses.append(out)
            cache.append((th, xh, tl, cl, p, out))
    lag = med([r['lag_s'] for r in presses if np.isfinite(r['lag_s'])])
    for th, xh, tl, cl, p, out in cache:
        zh, _ = wmean(th, xh, p['t_on']-zero_s-gap_s+lag, p['t_on']-gap_s+lag)
        zl, _ = wmean(tl, cl, p['t_on']-zero_s-gap_s, p['t_on']-gap_s)
        ph, nph = wmean(th, xh, p['t_rel']-1+lag, p['t_rel']+lag)
        pl, npl = wmean(tl, cl, p['t_rel']-1, p['t_rel'])
        r = zh-ph
        q = float(r.mean())
        F_h, F_l = hall_force(q), float(B*(pl-zl)*G)
        out['w1_lag_aligned'] = dict(n_hall=nph, n_lc=npl, q_adc=q, hall_N=F_h, lc_N=F_l, diff_N=F_h-F_l,
                                     c24=float(r[1]-r[3]), c31=float(r[2]-r[0]),
                                     Q=float(np.hypot(r[1]-r[3], r[2]-r[0])))
    summary = {}
    for cond in spec['conditions']:
        rows = [r for r in presses if r['condition'] == cond]
        summary[cond] = {f'w{w}': dict(n=len(rows),
                                       median_diff_N=med([r[f'w{w}']['diff_N'] for r in rows]),
                                       median_lc_N=med([r[f'w{w}']['lc_N'] for r in rows]),
                                       median_Q=med([r[f'w{w}']['Q'] for r in rows]),
                                       median_rel_diff=med([r[f'w{w}']['diff_N']/r[f'w{w}']['lc_N'] for r in rows]))
                         for w in spec['analysis']['plateau_windows_s']}
    lad = [r for r in presses if r['condition'] in spec['ladder_conditions']]
    x = np.array([r['w1']['lc_N'] for r in lad])
    y = np.array([r['w1']['hall_N'] for r in lad])
    summary['ladder'] = dict(n=len(lad), slope_through_origin=float((x*y).sum()/(x*x).sum()),
                             slope_intercept=[float(v) for v in np.polyfit(x, y, 1)],
                             diffs_N=[float(v) for v in y-x], lc_N=[float(v) for v in x])
    rounds = [r for r in presses if r['condition'] in spec['conditions']]
    summary['rounds'] = dict(n=len(rounds), n_hall_below=int(sum(r['w1']['diff_N'] < 0 for r in rounds)),
                             diff_N_min=min(r['w1']['diff_N'] for r in rounds),
                             diff_N_max=max(r['w1']['diff_N'] for r in rounds),
                             lc_N_min=min(r['w1']['lc_N'] for r in rounds),
                             lc_N_max=max(r['w1']['lc_N'] for r in rounds))
    summary['lag_s_median'] = lag
    al = 'w1_lag_aligned'
    summary['lag_aligned'] = {cond: dict(n=len([r for r in presses if r['condition'] == cond]),
                                         median_diff_N=med([r[al]['diff_N'] for r in presses if r['condition'] == cond]),
                                         median_rel_diff=med([r[al]['diff_N']/r[al]['lc_N'] for r in presses if r['condition'] == cond]),
                                         median_Q=med([r[al]['Q'] for r in presses if r['condition'] == cond]))
                              for cond in spec['conditions']}
    summary['lag_aligned']['ladder_diffs_N'] = [r[al]['diff_N'] for r in lad]
    summary['lag_aligned']['rounds'] = dict(n_hall_below=int(sum(r[al]['diff_N'] < 0 for r in rounds)),
                                            diff_N_min=min(r[al]['diff_N'] for r in rounds),
                                            diff_N_max=max(r[al]['diff_N'] for r in rounds))
    counts = {}
    for cond in spec['conditions'][1:]:
        c = dict(rounds=0, Q_above_center=0, Q_over_q_above_center=0)
        for code in sorted({r['code'] for r in rounds}):
            ctr = next(r for r in rounds if r['code'] == code and r['condition'] == spec['conditions'][0])['w1']
            alt = next(r for r in rounds if r['code'] == code and r['condition'] == cond)['w1']
            c['rounds'] += 1
            c['Q_above_center'] += int(alt['Q'] > ctr['Q'])
            c['Q_over_q_above_center'] += int(alt['Q']/alt['q_adc'] > ctr['Q']/ctr['q_adc'])
        counts[cond] = c
    summary['contrast_rounds'] = counts
    return dict(records=spec['records'], presses=presses, summary=summary)


def analyze_SC():
    spec = PLAN['SC']
    lo, hi = spec['analysis']['window_s']
    recs = {r['code']: r for r in spec['records']}

    def hall_mean(cid):
        t_dev, _, x = read_hall(cid)
        return wmean(t_dev, x, lo, hi)

    def lc_mean(cid):
        elapsed, _, c = read_lc(cid)
        return wmean(elapsed, c, lo, hi)

    rows = []
    for rec in spec['records']:
        if rec['load_state'] != 'loaded':
            continue
        z = recs[rec['previous_unloaded_code']]
        hl, nh = hall_mean(rec['hall_capture_id'])
        hz, _ = hall_mean(z['hall_capture_id'])
        cl, nl = lc_mean(rec['loadcell_capture_id'])
        cz, _ = lc_mean(z['loadcell_capture_id'])
        r = hz-hl
        F_h, F_l, F0 = hall_force(float(r.mean())), float(B*(cl-cz)*G), rec['reference_mass_g']*G
        rows.append(dict(code=rec['code'], mass_g=rec['reference_mass_g'], hall_N=F_h, lc_N=F_l,
                         hall_err_N=F_h-F0, lc_err_N=F_l-F0, hall_minus_lc_N=F_h-F_l,
                         c24=float(r[1]-r[3]), c31=float(r[2]-r[0]), n_hall=nh, n_lc=nl))
    b = json.loads((ROOT/'analysis/B.json').read_text(encoding='utf-8'))['predictions']['S1_S2_S3_S4_interpolation']
    ref = [dict(record=r['record_code'], mass_g=r['mass_g'], error_N=r['predicted_force_N']-r['mass_g']*G)
           for r in b if r['mass_g'] in spec['analysis']['B_reference_mass_g']]
    return dict(records=spec['records'], rows=rows, B_reference=ref)


def ramp_points(lag):
    """Matched (record, branch, load-cell force, Hall indication) points for the SX ramps."""
    spec = PLAN['SX']['analysis']
    pts, caps = [], []
    for rec in PLAN['SX']['records']:
        _, th, xh = read_hall(rec['hall_capture_id'])
        _, tl, cl = read_lc(rec['loadcell_capture_id'])
        zh = xh[th < th[0]+spec['zero_s']].mean(axis=0)
        zl = cl[tl < tl[0]+spec['zero_s']].mean()
        Fl = B*(cl-zl)*G
        half = spec['hall_half_window_s']
        Fh = []
        for t in tl:
            m = (th >= t+lag-half) & (th < t+lag+half)
            Fh.append(hall_force(float((zh-xh[m]).mean(axis=1).mean())) if m.any() else float('nan'))
        Fh = np.array(Fh)
        k = np.ones(spec['smoothing_samples'])/spec['smoothing_samples']
        dF = np.gradient(np.convolve(Fl, k, 'same'), tl)
        th_ = spec['branch_threshold_N_per_s']
        branch = np.where(dF > th_, 'load', np.where(dF < -th_, 'unload', 'hold'))
        for t, f_l, f_h, br in zip(tl, Fl, Fh, branch):
            if np.isfinite(f_h) and f_l > spec['min_force_N']:
                pts.append((rec['code'], br, float(f_l), float(f_h), float(t-tl[0])))
        caps.append(dict(code=rec['code'], n=len(tl), max_lc_N=float(Fl.max())))
    return pts, caps


def analyze_SX(lag):
    spec = PLAN['SX']['analysis']
    pts, caps = ramp_points(lag)
    table = []
    for br in ('load', 'hold', 'unload'):
        for lo in np.arange(0, spec['bin_max_N'], spec['bin_width_N']):
            d = [h-l for c, b_, l, h, _ in pts if b_ == br and lo <= l < lo+spec['bin_width_N']]
            if len(d) >= spec['min_points_per_bin']:
                table.append(dict(branch=br, lc_bin_N=[float(lo), float(lo+spec['bin_width_N'])], n=len(d),
                                  median_diff_N=float(np.median(d))))
    return dict(records=PLAN['SX']['records'], lag_s_used=lag, captures=caps, table=table)


def compute():
    s = analyze_S()
    return dict(S=s, SC=analyze_SC(), SX=analyze_SX(s['summary']['lag_s_median']))


def differences(u, v, path='', out=None):
    out = [] if out is None else out
    if isinstance(u, dict):
        if set(u) != set(v):
            out.append((path, 'keys differ'))
        for k in set(u) & set(v):
            differences(u[k], v[k], f'{path}/{k}', out)
    elif isinstance(u, list):
        if len(u) != len(v):
            out.append((path, f'length {len(u)} vs {len(v)}'))
        for i, (a, b) in enumerate(zip(u, v)):
            differences(a, b, f'{path}[{i}]', out)
    elif isinstance(u, float) or isinstance(v, float):
        if not ((np.isnan(u) and np.isnan(v)) or abs(u-v) <= TOL*max(1.0, abs(v))):
            out.append((path, f'{u!r} vs stored {v!r}'))
    elif u != v:
        out.append((path, f'{u!r} vs stored {v!r}'))
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    result = compute()
    path = ROOT/'analysis/synchronized_press.json'
    if args.write:
        path.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    else:
        stored = json.loads(path.read_text(encoding='utf-8'))
        diff = differences(result, stored)
        if diff:
            for d in diff[:20]:
                print('DIFF', *d)
            raise SystemExit(f'{len(diff)} recomputed values differ from analysis/synchronized_press.json')
    s, sc, sx = result['S']['summary'], result['SC']['rows'], result['SX']['table']
    print(json.dumps(dict(S={k: (v['w1'] if 'w1' in v else v) for k, v in s.items() if isinstance(v, dict)},
                          lag_s_median=s['lag_s_median'],
                          SC=[(r['code'], r['hall_err_N'], r['lc_err_N']) for r in sc],
                          SX=[(r['branch'], r['lc_bin_N'], r['n'], r['median_diff_N']) for r in sx]), indent=1))
