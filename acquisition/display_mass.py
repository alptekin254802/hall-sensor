"""PC counterpart of the frozen A display mapping; no fitting or hardware access."""
import csv, hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'firmware/stm32/v0_5_0/display_model.json'
STATES=('wait_zero','ok','negative_zero_extension','low','high','adc_rail','data_gap')

def convert(response):
    m=json.loads(MODEL.read_text())['state'];x=m['x_knots'];y=[v/.00980665 for v in m['y_knots_N']]
    if response < -x[1]:return 3,None
    if response < 0:status,g=2,response*y[1]/x[1]
    elif response > x[-1]:return 4,None
    else:
        status=1
        i=next(i for i in range(1,len(x)) if response<=x[i])
        g=y[i-1]+(response-x[i-1])*(y[i]-y[i-1])/(x[i]-x[i-1])
    mg=math.floor(g*1000+.5) if g>=0 else math.ceil(g*1000-.5)
    return status,mg

def review(folder):
    folder=Path(folder);session=json.loads((folder/'session.json').read_text())
    hashes={}
    for name in ('samples.csv','display.csv'):
        hashes[name]=hashlib.sha256((folder/name).read_bytes()).hexdigest()
        if hashes[name]!=session.get('files_sha256',{}).get(name):raise ValueError('source_hash_mismatch:'+name)
    expected_id=json.loads(MODEL.read_text())['model_id']
    if session['firmware_metadata'].get('display_model_id')!=expected_id:raise ValueError('unexpected_display_model')
    with (folder/'display.csv').open(encoding='utf-8') as f:rows=list(csv.DictReader(f))
    mismatches=[];valid=[];counts={k:0 for k in STATES}
    for row in rows:
        status=int(row['status']);counts[STATES[status]]+=1
        if status in (1,2,3,4):
            exp_status,mg=convert((int(row['zero_sum_adc'])-int(row['sum_adc']))/(4*int(row['count'])))
            actual=None if not row['mass_mg'] else int(row['mass_mg'])
            if status!=exp_status or actual!=mg:mismatches.append(int(row['last_seq']))
            if mg is not None:valid.append(mg/1000)
    return {'capture_id':folder.name,'display_frames':len(rows),'states':counts,
            'pc_conversion_mismatches':mismatches,'mass_mean_g':sum(valid)/len(valid) if valid else None,
            'mass_min_g':min(valid) if valid else None,'mass_max_g':max(valid) if valid else None,
            'model_id':expected_id,'source_hashes':hashes,
            'raw_capture_status':session['status'],'raw_issue_count':session['issue_count'],
            'actual_screen_pixels_verified':False,'physical_accuracy_test':False}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    r=review(a.folder);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r,indent=2))
