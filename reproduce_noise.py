"""Reproduce comparator noise using all complete 10 s windows of test set B.

The window construction and sample SD (ddof=1) follow the original
comparator test analysis, including loaded and unloaded records.
"""
from pathlib import Path
import argparse, csv, json, statistics
from data_access import INDEX, open_raw

ROOT=Path(__file__).resolve().parent
G=0.00980665

def calculate():
    data=json.loads((ROOT/'analysis/H.json').read_text(encoding='utf-8'))
    model=json.loads((ROOT/'models/H_loadcell.json').read_text(encoding='utf-8'))
    slope=abs(model['mass_g_per_count'])
    windows=[]; rates=[]
    for record in data['test_records']:
        cid=record['capture_id']
        with open_raw(cid) as f: rows=list(csv.DictReader(f))
        duration=int(float(rows[-1]['elapsed_s'])//10)*10
        for start in range(0,duration,10):
            values=[int(r['raw_counts']) for r in rows if start<=float(r['elapsed_s'])<start+10]
            windows.append(dict(capture_id=cid,record_code=record['record_code'],
                load_state=record['load_state'],window_s=[start,start+10],n=len(values),
                sample_sd_N=statistics.stdev(values)*slope*G))
        if record['load_state']=='loaded':
            rates.append((len(rows)-1)/(float(rows[-1]['elapsed_s'])-float(rows[0]['elapsed_s'])))
    return dict(population='All 33 comparator B records: 26 loaded and 7 unloaded',
        window_rule='Every complete non-overlapping 10 s window starting at 0 s; sample SD, ddof=1',
        n_records=len(data['test_records']),n_windows=len(windows),
        sd_range_N=[min(w['sample_sd_N'] for w in windows),max(w['sample_sd_N'] for w in windows)],
        loaded_B_rate_range_Hz=[min(rates),max(rates)],windows=windows)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true',help='Write the derived analysis summary')
    args=parser.parse_args(); result=calculate()
    path=ROOT/'analysis/comparator_noise.json'
    if args.write:path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    elif path.exists():
        stored=json.loads(path.read_text(encoding='utf-8'))
        assert result==stored,'Comparator noise summary differs'
    print(json.dumps({k:v for k,v in result.items() if k!='windows'},indent=2))

if __name__=='__main__':main()
