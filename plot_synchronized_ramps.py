"""Plot the exploratory synchronized hand ramps (SX): one ramp in time and all matched points."""
from pathlib import Path
import argparse
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reproduce_synchronized import ramp_points, read_hall, read_lc, hall_force, B, G, PLAN

ROOT = Path(__file__).resolve().parent
COLORS = {'load': '#1b6f8f', 'unload': '#b5532b', 'hold': '#9a9a9a'}
LABELS = {'load': 'Loading', 'unload': 'Unloading', 'hold': 'Hold'}


def trace(rec, lag, zero_s):
    _, th, xh = read_hall(rec['hall_capture_id'])
    _, tl, cl = read_lc(rec['loadcell_capture_id'])
    zh = xh[th < th[0]+zero_s].mean(axis=0)
    zl = cl[tl < tl[0]+zero_s].mean()
    q = (zh-xh).mean(axis=1)
    fh = np.array([hall_force(v) if np.isfinite(v) else np.nan for v in q])
    return th-lag-tl[0], fh, tl-tl[0], B*(cl-zl)*G


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    stored = json.loads((ROOT/'analysis/synchronized_press.json').read_text(encoding='utf-8'))
    lag = stored['SX']['lag_s_used']
    pts, _ = ramp_points(lag)
    plt.rcParams.update({'font.size': 9, 'axes.spines.top': False,
                         'axes.spines.right': False, 'pdf.fonttype': 42, 'ps.fonttype': 42})
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.0, 3.0), layout='constrained')
    rec = PLAN['SX']['records'][0]
    t_h, f_h, t_l, f_l = trace(rec, lag, PLAN['SX']['analysis']['zero_s'])
    a.plot(t_l, f_l, '-', color='#333333', lw=1.1, label='Load cell')
    a.plot(t_h, f_h, '-', color=COLORS['load'], lw=0.8, label='Hall head')
    a.set(xlabel='Time (s)', ylabel='Force (N)', title='(a) First ramp record', xlim=(0, t_l[-1]))
    a.legend(frameon=False, loc='upper center')
    a.grid(alpha=.17)
    for br in ('hold', 'load', 'unload'):
        p = [(l, h) for _, b_, l, h, _ in pts if b_ == br]
        if p:
            b.plot(*zip(*p), '.', ms=2.2, color=COLORS[br], label=LABELS[br])
    top = 5*np.ceil(max(l for _, _, l, _, _ in pts)/5)
    b.plot([0, top], [0, top], 'k--', lw=.8)
    b.set(xlabel='Load-cell force (N)', ylabel='Hall indication (N)', title='(b) Both records',
          xlim=(0, top), ylim=(0, top))
    b.set_aspect('equal')
    b.legend(frameon=False, markerscale=4, loc='upper left')
    b.grid(alpha=.17)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output_dir/'synchronized_ramps.pdf')
    fig.savefig(args.output_dir/'synchronized_ramps.png', dpi=180)
    plt.close(fig)
    print(json.dumps(dict(points=len(pts), lag_s=lag), indent=2))


if __name__ == '__main__':
    main()
