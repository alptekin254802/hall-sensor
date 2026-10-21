"""Human-readable, provenance-labelled derivatives. Never edits acquisition CSVs."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

LABEL_FIELDS = ['load_state', 'reference_mass_g', 'reference_force_N', 'object_id',
                'position', 'repetition', 'cycle', 'physical_loading_id',
                'experiment_id', 'data_role', 'label_source', 'label_timing']

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def initial_label(context, capture_id):
    state = context.get('load_state', 'unknown')
    mass = context.get('mass_g')
    if state not in {'unknown', 'loaded', 'unloaded', 'transition'}:
        raise ValueError('Unknown load state')
    if mass is not None:
        mass = float(mass)
        if not math.isfinite(mass) or mass < 0:
            raise ValueError('Mass must be finite and nonnegative')
        if state != 'loaded' and not (state == 'unloaded' and mass == 0):
            raise ValueError('Mass requires a loaded state; unloaded accepts only zero')
    if state == 'unloaded': mass = 0.0
    row = dict.fromkeys(LABEL_FIELDS)
    row.update(load_state=state, reference_mass_g=mass,
               physical_loading_id=context.get('physical_loading_id') or capture_id,
               label_source=context.get('label_source') or ('declared_before_capture' if state != 'unknown' else 'unknown'),
               label_timing='declared_whole_capture; not measured load onset')
    for key in ('object_id', 'position', 'repetition', 'cycle', 'experiment_id', 'data_role'):
        row[key] = context.get(key)
    # Force is deliberately not inferred with an unstated gravitational acceleration.
    return row

def apply_event(label, event, ordinal, capture_id):
    result = dict(label)
    kind = event.get('kind')
    if kind in {'load', 'unload'}:
        result.update(load_state='loaded' if kind == 'load' else 'unloaded',
                      reference_mass_g=0.0 if kind == 'unload' else None,
                      reference_force_N=None,
                      physical_loading_id=f'{capture_id}:event{ordinal}')
        if kind == 'load':
            unit, value = event.get('reference_unit'), event.get('reference_value')
            if value is not None:
                if not math.isfinite(value) or value < 0: raise ValueError('Invalid reference')
                if unit in {'g', 'kg'}: result['reference_mass_g'] = value * (1000 if unit == 'kg' else 1)
                elif unit == 'N': result['reference_force_N'] = value
            for key in ('position', 'repetition', 'cycle'):
                if event.get(key) is not None: result[key] = event[key]
        result.update(label_source=f'events.jsonl:{ordinal}',
                      label_timing='host mark; applies after latest received seq; transition/transport uncertainty')
    elif kind == 'position':
        result.update(position=event.get('position'), label_source=f'events.jsonl:{ordinal}',
                      label_timing='host position mark; not measured placement')
    return result

def export_capture(capture, destination, annotation=None):
    capture, destination = Path(capture), Path(destination)
    meta = json.loads((capture/'session.json').read_text(encoding='utf-8'))
    if meta['status'] == 'recording': raise ValueError('Close the capture before exporting')
    for name, expected in meta.get('files_sha256', {}).items():
        if digest(capture/name) != expected: raise ValueError('Raw artifact hash mismatch: '+name)
    context = dict(meta.get('context', {}))
    if annotation:
        if not annotation.get('label_source'): raise ValueError('Retrospective labels require their source')
        for key in ('load_state', 'mass_g', 'object_id', 'position', 'repetition', 'cycle',
                    'physical_loading_id', 'experiment_id', 'data_role'):
            if key in annotation:
                if context.get(key) is not None and context[key] != annotation[key]:
                    raise ValueError('Annotation conflicts with recorded context: '+key)
                context[key] = annotation[key]
        context['label_source'] = annotation['label_source']
    label = initial_label(context, meta['capture_id'])
    events = [json.loads(x) for x in (capture/'events.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (capture/'samples.csv').open(encoding='utf-8', newline='') as src, destination.open('x', encoding='utf-8', newline='') as out:
        reader = csv.DictReader(src)
        original_fields = reader.fieldnames or []
        writer = csv.DictWriter(out, fieldnames=['capture_id']+original_fields+LABEL_FIELDS)
        writer.writeheader()
        index = 0
        for sample in reader:
            seq = int(sample['seq'])
            while index < len(events):
                e = events[index]
                after = e.get('latest_received_seq')
                if after is not None and seq <= after: break
                label = apply_event(label, e, index+1, meta['capture_id'])
                index += 1
            writer.writerow(dict(sample, capture_id=meta['capture_id'], **label))
    return dict(capture_id=meta['capture_id'], status=meta['status'], issues=meta['issue_count'],
                records=meta['valid_samples'], source_sha256=meta['files_sha256'],
                derivative_sha256=digest(destination), initial_label=initial_label(context,meta['capture_id']),
                firmware_metadata=meta.get('firmware_metadata'),
                annotation=annotation, raw_samples_unchanged=True)

def slug(value):
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', str(value if value is not None else '')).strip('_')[:72] or 'unknown'

def export_catalog(root, out, annotations=None):
    root, out = Path(root), Path(out)
    out.mkdir(parents=True, exist_ok=False)
    annotations = annotations or {}
    captures = sorted(root.glob('*/session.json'), key=lambda p: json.loads(p.read_text(encoding='utf-8'))['created_utc_ns'])
    entries = []
    for path in captures:
        meta = json.loads(path.read_text(encoding='utf-8'))
        key = meta['capture_id']; context = dict(meta.get('context',{})); context.update(annotations.get(key,{}))
        label = initial_label(context,key)
        stamp = datetime.fromtimestamp(meta['created_utc_ns']/1e9,timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        mass = 'unknown' if label['reference_mass_g'] is None else f"{label['reference_mass_g']:g}g"
        filename = f"{stamp}_{mass}_{label['load_state']}_{slug(label.get('object_id'))}_{key[:8]}.csv"
        try:
            report = export_capture(path.parent,out/filename,annotations.get(key))
            temperature_source = path.parent/'temperatures.csv'
            if temperature_source.exists():
                companion = filename.removesuffix('.csv')+'_temperatures.csv'
                with (out/companion).open('xb') as target: target.write(temperature_source.read_bytes())
                report['temperature_file'] = companion
                report['temperature_sha256'] = digest(out/companion)
            (out/(filename+'.json')).write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
            entries.append(dict(capture_id=key,file=filename,created_utc=stamp,**label,
                                records=meta['valid_samples'],issues=meta['issue_count'],status=meta['status'],export_error=''))
        except (ValueError, OSError) as e:
            entries.append(dict(capture_id=key,file='',created_utc=stamp,**label,
                                records=meta['valid_samples'],issues=meta['issue_count'],status=meta['status'],export_error=str(e)))
    with (out/'index.csv').open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['capture_id','file','created_utc']+LABEL_FIELDS+['records','issues','status','export_error'])
        w.writeheader();w.writerows(entries)
    (out/'README.md').write_text('''# Hall pilot recordings\n\nEach named CSV is a labelled derivative; ADC values are unchanged. `index.csv` includes every capture, including unknown and failed runs. Times in filenames are UTC. Sidecar JSONs contain hashes and firmware metadata, without machine paths.\n\n`unloaded` means no applied test object (0 g **added** mass), not zero mechanical tare. A loaded mass includes the weighed object and its container. `unknown` is not zero. Labels added after acquisition are based on measurement notes and the acquisition sequence; physical load-transition times were not recorded by the device. Host event marks are not exact physical transitions.\n\nS1=PA0, S2=PA1, S3=PA5, S4=PA6. Physical X/Y assignment is unverified. ADC counts are raw 12-bit values, not grams. Force in N is blank for mass labels until an explicit gravity convention is chosen. These recordings are pilot/diagnostic data, not an independent final test set. Separate captures within one experiment are not automatically independent experiments.\n\nNo automatic upload or scientific calibration is performed. Incomplete/issue records remain visible and must not silently enter model training. Temperature measurements are copied unchanged into companion `*_temperatures.csv` files. Join by device timestamps and ROM, not row number; temperature conversions are not sample-synchronous. Events and transport timing remain in the source archive; sidecars preserve their hashes.\n''',encoding='utf-8')
    return entries

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('root',type=Path);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--annotations',type=Path)
    a=ap.parse_args(argv)
    rows=export_catalog(a.root,a.out,json.loads(a.annotations.read_text(encoding='utf-8')) if a.annotations else None)
    print(f'{len(rows)} captures indexed; {sum(bool(r["export_error"]) for r in rows)} export errors')
    return int(any(r['export_error'] for r in rows))

if __name__=='__main__':raise SystemExit(main())
