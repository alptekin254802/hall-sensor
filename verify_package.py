"""Verify the inventory and exact decompressed measurement hashes, without hardware."""
from pathlib import Path
import gzip
import csv
import math
import hashlib
import json

ROOT = Path(__file__).resolve().parent
ANONYMIZED_AUTHOR_FILES = frozenset({'CITATION.cff', 'LICENSE', 'DATA_LICENSE.md'})

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
listed = {f['path'] for f in manifest['files']}
actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*')
          if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts
          and p.relative_to(ROOT).parts[0] != 'figures'
          and p.name != 'manifest.json'}
assert listed == actual, (sorted(listed-actual), sorted(actual-listed))
for f in manifest['files']:
    p = ROOT / f['path']
    assert p.is_file(), f['path']
    if f['path'] in ANONYMIZED_AUTHOR_FILES:
        continue
    assert p.stat().st_size == f['bytes'], f['path']
    assert digest(p) == f['sha256'], f['path']
print('Author names may be masked in anonymous copies; CITATION.cff, LICENSE and '
      'DATA_LICENSE.md are checked for presence only. All other integrity checks remain unchanged.')
index = json.loads((ROOT / 'raw_index.json').read_text(encoding='utf-8'))
assert len({r['capture_id'] for r in index}) == len(index)

def analysis(name):
    return json.loads((ROOT / 'analysis' / (name+'.json')).read_text(encoding='utf-8'))

# Required recordings include the unloaded and centered references used by each analysis.
groups = {}
def rows(group, records, keys):
    groups[group] = {r[k] for r in records for k in keys}

rows('A', analysis('A_calibration_observations'), ['capture_id', 'preceding_zero_capture_id'])
rows('A_REFINE', analysis('A_REFINE')['observations'], ['capture_id', 'preceding_zero_capture_id'])
rows('B', analysis('B')['observations'], ['capture_id', 'zero_capture_id'])
groups['C_books'] = set(analysis('C_selected')['capture_ids_in_sequence'])
groups['C_books_excluded'] = set(analysis('C_excluded')['capture_ids_in_sequence'])
d = analysis('D')
groups['D'] = {r['capture_id'] for r in d['position_effects']} | {
    b[k] for b in d['blocks'] for k in ('center_start_id', 'center_end_id')}
groups['E'] = {analysis('E')['capture_id']}
groups['F'] = {r['capture_id'] for r in analysis('F').values()}
rows('G774', analysis('G774')['records'], ['capture_id'])
rows('G1000_check', analysis('G1000_check')['captures'], ['capture_id'])
groups['G_three_hour'] = {analysis('G_three_hour')['capture_id']}
h = analysis('H')
rows('H', h['calibration_records'] + h['test_records'], ['capture_id'])
for name in ('R_small', 'R_range'):
    rows(name, analysis(name)['pairs'], ['before_id', 'loaded_id', 'after_id'])
rows('T', analysis('T')['observations'], ['capture_id', 'zero_capture_id'])
groups['Nextion'] = {analysis('Nextion')['summary']['capture_id']}
rows('directional_press', analysis('directional_press')['trials'], ['capture_id'])
groups['manual_press'] = {p.stem.removeprefix('manual_') for p in (ROOT/'analysis').glob('manual_*.json')}
sync = analysis('synchronized_press')
for name, key in (('S_sync', 'S'), ('SC_static', 'SC'), ('SX_ramps', 'SX')):
    groups[name] = {r[k] for r in sync[key]['records'] for k in ('hall_capture_id', 'loadcell_capture_id')}
required = set.union(*groups.values())
assert required == {r['capture_id'] for r in index}
assert required == {p.name for p in (ROOT/'raw').iterdir() if p.is_dir()}
metadata = json.loads((ROOT/'release_metadata.json').read_text(encoding='utf-8'))
assert metadata['capture_count'] == manifest['captures'] == len(index)
assert metadata['analysis_groups'] == {k:len(v) for k,v in groups.items()}
measurement_count = 0
measurement_bytes = 0
for row in index:
    for name, f in row['measurement_files'].items():
        p = ROOT / f['path']
        assert digest(p) == f['sha256']
        h = hashlib.sha256()
        length = 0
        with gzip.open(p, 'rb') as stream:
            while chunk := stream.read(1024*1024):
                h.update(chunk)
                length += len(chunk)
        assert h.hexdigest() == f['original_sha256'], (row['capture_id'], name)
        assert length == f['original_bytes'], (row['capture_id'], name)
        measurement_count += 1
        measurement_bytes += length
assert measurement_count == metadata['measurement_files']
with (ROOT / 'analysis/reference_scale_check.csv').open(newline='', encoding='utf8') as f:
    reader = csv.DictReader(f)
    assert reader.fieldnames == ['object', 'crw7024_g_1', 'crw7024_g_2', 'crw7024_g_3', 'cas_g']
    scale_rows = list(reader)
assert len(scale_rows) == len({r['object'] for r in scale_rows}) == 5
scale_pairs = [(float(r['cas_g']), sum(float(r[f'crw7024_g_{i}']) for i in (1, 2, 3)) / 3)
               for r in scale_rows]
assert all(math.isfinite(v) and v > 0 for pair in scale_pairs for v in pair)
scale_k = sum(c * (s - c) for c, s in scale_pairs) / sum(c*c for c, s in scale_pairs)
scale_residual = max(abs(s - (1 + scale_k) * c) for c, s in scale_pairs)
assert round(100 * scale_k, 2) == 0.43
assert round(scale_residual, 1) == 1.7
print(json.dumps(dict(status='pass', files=len(manifest['files']), captures=len(index),
    measurement_files=measurement_count, original_measurement_bytes=measurement_bytes,
    reference_scale_check=dict(objects=len(scale_rows), proportional_difference_percent=100*scale_k,
                               maximum_absolute_residual_g=scale_residual)), indent=2))
