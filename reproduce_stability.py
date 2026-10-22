"""Reproduce only the combined stability table from unchanged packaged raw data."""
from pathlib import Path
from data_access import raw_path, open_raw
import csv, json
import numpy as np
ROOT=Path(__file__).resolve().parent
expected=json.loads((ROOT/"analysis/stability.json").read_text())
model=json.loads((ROOT/"models/S1_S2_S3_S4_interpolation.json").read_text())["state"]
x=np.array(model["x_knots"]); y=np.array(model["y_knots_N"])
slope=(y[1]-y[0])/(x[1]-x[0])
results=[]
for row in expected["records"]:
    folder=ROOT/"raw"/row["capture_id"]
    a=np.loadtxt(raw_path(row["capture_id"], "samples.csv"),delimiter=",",skiprows=1,usecols=(2,3,4,5,6))
    t=a[:,0]/1e6; raw=a[:,1:].mean(axis=1)
    start=row.get("analysis_start_s",0.0); end=t[-1]
    keep=t>=start; t=t[keep]-start; raw=raw[keep]
    first=raw[t<60].mean()
    endpoint=raw[t>=t[-1]-60].mean()-first
    minutes=row.get("minute_count",180 if row["name"]=="three_hour_unloaded" else 60)
    delta=np.array([raw[(t>=i*60)&(t<(i+1)*60)].mean()-first for i in range(minutes)])
    if row["mass_g"]:
        force0=row["mass_g"]*.00980665; q0=np.interp(force0,y,x)
        force=np.interp(q0-delta,x,y)-force0
        endpoint_force=np.interp(q0-endpoint,x,y)-force0
    else:
        force=-slope*delta; endpoint_force=-slope*endpoint
    got=dict(endpoint_raw_ADC=float(endpoint),endpoint_N=float(endpoint_force),
             maximum_absolute_ADC=float(abs(delta).max()),maximum_absolute_N=float(abs(force).max()))
    for key,value in got.items():
        assert abs(value-row[key])<1e-9,(row["name"],key,value,row[key])
    with open_raw(row["capture_id"], "temperatures.csv") as f:temps=list(csv.DictReader(f))
    head="28128e9900000030" if row["name"]=="three_hour_unloaded" else "28a2d27f912506a3"
    for role,rom in [("head_probe",head),("ambient_probe","28e88f40912506b2")]:
        values=[float(z["temperature_c"]) for z in temps if z["rom"]==rom and int(z["status"])==0
                and start<=int(z["read_us"])/1e6<=end]
        assert [min(values),max(values)]==row["temperature_ranges_C"][role]
    results.append(dict(record=row["name"],**got))
print(json.dumps(results,indent=2))
