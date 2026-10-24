"""Reproduce absolute force errors for Reviewer 4, comment 1 only."""
from pathlib import Path
from collections import Counter
import argparse
import hashlib
import json
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data_access import raw_path

G = 0.00980665
MODEL = 'models/S1_S2_S3_S4_interpolation.json'
OUTPUT = Path(__file__).with_suffix('.json')
ZERO_IDS = {
    'primary': '43902f60258f44b193994385c76ce99d',
    'alternative': '8a41d11b7403432fa562c11860d39efc',
}
BLOCK2_POSITIONS = frozenset({
    'YM5', 'YM10', 'YM15', 'YM20', 'YP5', 'YP10', 'YP15', 'YP20',
    'XM5', 'XM10', 'XM15',
})


def selected_offsets(position_effects):
    selected = []
    for row in position_effects:
        key = (row['reference_mass_g'], row['block'])
        if key in ((542, 1), (1042, 1)) or (
                key == (542, 2) and row['position'] in BLOCK2_POSITIONS):
            selected.append(row)
    assert Counter((r['reference_mass_g'], r['block']) for r in selected) == {
        (542, 1): 16, (1042, 1): 16, (542, 2): 11,
    }, 'Unexpected offset population'
    assert len({r['capture_id'] for r in selected}) == 43
    all_positions = {f'{axis}{sign}{distance}' for axis in 'XY'
                     for sign in 'PM' for distance in (5, 10, 15, 20)}
    for key, expected in [((542, 1), all_positions), ((1042, 1), all_positions),
                          ((542, 2), BLOCK2_POSITIONS)]:
        assert {r['position'] for r in selected
                if (r['reference_mass_g'], r['block']) == key} == expected
    return selected


def window(capture_id, start_s, end_s):
    a = np.loadtxt(raw_path(capture_id), delimiter=',', skiprows=1,
                   usecols=(2, 3, 4, 5, 6), ndmin=2)
    assert len(a) and np.isfinite(a).all(), capture_id
    assert np.all(np.diff(a[:, 0]) > 0), capture_id
    t = (a[:, 0] - a[0, 0]) / 1e6
    values = a[(t >= start_s) & (t < end_s), 1:5]
    # Captures ending one nominal 10 ms scan before the boundary are retained.
    assert len(values) in (int((end_s-start_s)*100)-1,
                           int((end_s-start_s)*100)), capture_id
    return dict(mean_adc=float(values.mean()), sample_count=len(values),
                channel_mean_adc=values.mean(axis=0).tolist())


def force(response, x, y):
    if not np.isfinite(response) or not x[0] <= response <= x[-1]:
        raise ValueError(f'Response outside frozen model support: {response}')
    return float(np.interp(response, x, y))


def metrics(errors):
    e = np.asarray(errors, dtype=float)
    assert len(e) and np.isfinite(e).all()
    return dict(n=len(e), mae_N=float(np.abs(e).mean()),
                rmse_N=float(np.sqrt(np.mean(e**2))), bias_N=float(e.mean()),
                maximum_absolute_error_N=float(np.abs(e).max()),
                positive_errors=int((e > 0).sum()), negative_errors=int((e < 0).sum()))


def recompute():
    model_path = ROOT / MODEL
    model = json.loads(model_path.read_text(encoding='utf8'))
    state = model['state']
    x = np.array(state['x_knots']); y = np.array(state['y_knots_N'])
    assert np.all(np.diff(x) > 0) and np.all(np.diff(y) >= 0)
    d_path = ROOT / 'analysis/D.json'
    d = json.loads(d_path.read_text(encoding='utf8'))
    offsets = selected_offsets(d['position_effects'])
    zeros = {key: dict(capture_id=cid, window_s=[5, 10], **window(cid, 5, 10))
             for key, cid in ZERO_IDS.items()}
    rows = []
    for offset in offsets:
        w = window(offset['capture_id'], 10, 20)
        mass = offset['reference_mass_g']
        row = {k: offset[k] for k in ('capture_id', 'record_code',
                                     'reference_mass_g', 'block', 'position', 'x_mm', 'y_mm')}
        row.update(distance_mm=abs(offset['x_mm'])+abs(offset['y_mm']),
                   window_s=[10, 20], offset_mean_adc=w['mean_adc'],
                   sample_count=w['sample_count'], reference_force_N=mass*G)
        for key, zero in zeros.items():
            response = zero['mean_adc'] - w['mean_adc']
            estimate = force(response, x, y)
            error = estimate - mass*G
            row[key] = dict(response_adc=response, estimate_N=estimate,
                            signed_error_N=error, absolute_error_N=abs(error))
        rows.append(row)
    summaries = {}
    for mass in (542, 1042):
        sub = [r for r in rows if r['reference_mass_g'] == mass]
        summaries[str(mass)] = {
            key: dict(**metrics([r[key]['signed_error_N'] for r in sub]),
                      by_offset_mm={str(distance): metrics([
                          r[key]['signed_error_N'] for r in sub if r['distance_mm'] == distance])
                          for distance in (5, 10, 15, 20)})
            for key in zeros}
    return dict(
        schema_version=1, analysis_id='RR_D_absolute_errors',
        scope='Reviewer-response analysis (Reviewer 4, comment 1); not reported in the manuscript.',
        role='reviewer_response_only', force_N_per_g=G,
        error_definition='F(unloaded four-channel mean - offset four-channel mean) - reference_mass_g * force_N_per_g',
        model_file=MODEL, model_id=model['model_id'],
        model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
        offset_source='analysis/D.json', offset_source_sha256=hashlib.sha256(d_path.read_bytes()).hexdigest(),
        windows=dict(time_origin='first sample t_us of each recording',
                     interval='start inclusive, end exclusive',
                     unloaded_s=[5, 10], offset_s=[10, 20]),
        population=[dict(reference_mass_g=542, block=1, offsets=16, positions='all'),
                    dict(reference_mass_g=1042, block=1, offsets=16, positions='all'),
                    dict(reference_mass_g=542, block=2, offsets=11,
                         positions=sorted(BLOCK2_POSITIONS))],
        excluded=dict(blocks=[dict(reference_mass_g=1042, block=2)],
                      positions=[dict(reference_mass_g=542, block=2,
                                      labels=['XM20', 'XP5', 'XP10', 'XP15', 'XP20'])]),
        references=zeros, n_offsets=len(rows),
        positive_errors=sum(r['primary']['signed_error_N'] > 0 for r in rows),
        summary_by_mass_g=summaries, offsets=rows)


def check_targets(result):
    expected = {'542': (0.734, 0.479, 1.377, 0.616),
                '1042': (1.561, 0.515, 2.850, 1.423)}
    for mass, target in expected.items():
        group = result['summary_by_mass_g'][mass]
        actual = [group['primary']['mae_N'], group['primary']['by_offset_mm']['5']['mae_N'],
                  group['primary']['maximum_absolute_error_N'], group['alternative']['mae_N']]
        np.testing.assert_allclose(actual, target, atol=0.005, rtol=0,
                                   err_msg=f'{mass} g response-letter values')
    assert result['n_offsets'] == 43 and result['positive_errors'] == 42


def compare(actual, expected, path='result'):
    if isinstance(actual, dict):
        assert isinstance(expected, dict) and actual.keys() == expected.keys(), path
        for key in actual:
            compare(actual[key], expected[key], f'{path}.{key}')
    elif isinstance(actual, list):
        assert isinstance(expected, list) and len(actual) == len(expected), path
        for i, (a, e) in enumerate(zip(actual, expected)):
            compare(a, e, f'{path}[{i}]')
    elif isinstance(actual, float):
        np.testing.assert_allclose(actual, expected, atol=1e-9, rtol=0, err_msg=path)
    else:
        assert actual == expected, path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Regenerate the derived JSON')
    args = parser.parse_args()
    result = recompute()
    check_targets(result)
    if args.write:
        OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf8')
    else:
        compare(result, json.loads(OUTPUT.read_text(encoding='utf8')))
    print(json.dumps(dict(status='pass', n_offsets=result['n_offsets'],
                          positive_errors=result['positive_errors'],
                          summary_by_mass_g=result['summary_by_mass_g']), indent=2))


if __name__ == '__main__':
    main()
