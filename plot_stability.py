"""Regenerate the thermal and three-hour plots with embedded TrueType fonts."""
from pathlib import Path
import argparse, csv, json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from data_access import raw_path, open_raw

ROOT=Path(__file__).resolve().parent
def read(name):return json.loads((ROOT/'analysis'/f'{name}.json').read_text(encoding='utf-8'))
def temperatures(cid):
    with open_raw(cid,'temperatures.csv') as f:return list(csv.DictReader(f))
def save(fig,out,name):
    fig.savefig(out/f'{name}.pdf')
    fig.savefig(out/f'{name}.png',dpi=180)
    plt.close(fig)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();out=args.output_dir;out.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,
                         'pdf.fonttype':42,'ps.fonttype':42})
    model=json.loads((ROOT/'models/S1_S2_S3_S4_interpolation.json').read_text(encoding='utf-8'))['state']
    x=np.array(model['x_knots']);y=np.array(model['y_knots_N'])
    def force(q):return np.where((q>=x[0])&(q<=x[-1]),np.interp(q,x,y),np.nan)
    thermal=read('G774');expected=thermal['verified_force_results']
    zero=expected['initial_zero_adc'];start=None
    fig,axes=plt.subplots(2,1,figsize=(7,4.8),sharex=True,layout='constrained')
    records=expected['records']
    for i,record in enumerate(records):
        cid=record['capture_id']
        # The final loaded record pairs with the final unloaded record for the
        # fresh-zero endpoint; the fixed-reference trace ends before it.
        plotted=i<len(records)-1
        # The first loaded record began before the book was placed (settled by 90 s).
        first_minute=2 if i==0 else 0
        a=np.loadtxt(raw_path(cid),delimiter=',',skiprows=1,usecols=(1,2,3,4,5,6,11))
        temps=temperatures(cid)
        if start is None:start=a[0,-1]/1e9
        for rom,label,color in [(thermal['head_probe_rom'],'Head probe','#b64b32'),(thermal['ambient_probe_rom'],'Ambient probe','#427d9c')]:
            values=np.array([[int(r['host_utc_ns'])/1e9,float(r['temperature_c'])] for r in temps if r['rom']==rom and int(r['status'])==0])
            if plotted:axes[0].plot((values[:,0]-start)/3600,values[:,1],color=color,lw=1,label=label if i==0 else None)
        sec=(a[:,1]-a[0,1])/1e6;bins=np.floor(sec/60).astype(int)
        times=[];values=[]
        for b in range(first_minute,int(sec[-1]//60)):
            w=a[bins==b];times.append((w[:,-1].mean()/1e9-start)/3600)
            values.append(float(force(zero-w[:,2:6].mean())))
        end60=float(force(zero-a[a[:,1]>=a[-1,1]-60e6,2:6].mean()))
        assert abs(end60-record['indication_last60s_N'])<1e-9
        if plotted:axes[1].plot(times,values,color='#235f58',lw=1.4)
    axes[0].set_ylabel('Temperature (°C)');axes[0].legend(loc='lower right',frameon=False,ncol=2)
    axes[1].set_ylabel('Indication (N)\ninitial unloaded reference')
    axes[1].set_xlabel('Time from first loaded record (h)')
    axes[1].axhline(thermal['mass_g']*.00980665,color='#666',ls='--',lw=.8,label='Applied load: 774 g')
    axes[1].legend(loc='lower left',frameon=False)
    for ax in axes:ax.grid(alpha=.17)
    save(fig,out,'thermal_cycle')
    expected=next(r for r in read('stability')['records'] if r['name']=='three_hour_unloaded')
    cid=expected['capture_id']
    a=np.loadtxt(raw_path(cid),delimiter=',',skiprows=1,usecols=(2,3,4,5,6))
    t=a[:,0]/1e6;raw=a[:,1:].mean(axis=1);first=raw[t<60].mean();slope=(y[1]-y[0])/(x[1]-x[0])
    values=-slope*np.array([raw[(t>=i*60)&(t<(i+1)*60)].mean()-first for i in range(180)])
    assert abs(max(abs(values))-expected['maximum_absolute_N'])<1e-9
    fig,axes=plt.subplots(2,1,figsize=(7,4.3),sharex=True,layout='constrained')
    temps=temperatures(cid)
    for rom,label,color in [('28128e9900000030','Head probe','#b64b32'),('28e88f40912506b2','Ambient probe','#427d9c')]:
        rows=[r for r in temps if r['rom']==rom and int(r['status'])==0 and int(r['read_us'])<=10799990000]
        axes[0].plot([int(r['read_us'])/3.6e9 for r in rows],[float(r['temperature_c']) for r in rows],label=label,color=color,lw=.8)
    axes[0].set_ylabel('Temperature (°C)');axes[0].legend(frameon=False,ncol=2)
    axes[1].plot((np.arange(180)+.5)/60,values,color='#235f58')
    axes[1].axhline(0,color='gray',lw=.7)
    axes[1].set_ylabel('Zero-change equivalent (N)');axes[1].set_xlabel('Elapsed time (h)')
    for ax in axes:ax.grid(alpha=.17)
    save(fig,out,'three_hour_zero')
    print('Thermal endpoints and three-hour range verified; figures regenerated.')

if __name__=='__main__':main()
