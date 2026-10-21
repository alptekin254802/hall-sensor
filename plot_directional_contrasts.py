"""Plot directional contrast magnitudes by condition, independent of record order."""
from pathlib import Path
import argparse
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
CONDITIONS = ('CENTER', 'TILT_XP', 'OFFSET_XP15')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    trials = json.loads((ROOT/'analysis/directional_press.json').read_text(encoding='utf-8'))['trials']
    plt.rcParams.update({'font.size':9, 'axes.spines.top':False,
                         'axes.spines.right':False, 'pdf.fonttype':42, 'ps.fonttype':42})
    fig,ax = plt.subplots(figsize=(5.7,3.1),layout='constrained')
    plotted=[]
    for block in range(1,6):
        rows=[r for r in trials if r['block']==block]
        cases={r['condition']:r for r in rows}
        assert len(rows)==len(cases)==3 and set(cases)==set(CONDITIONS)
        values=[cases[c]['primary']['Q_adc'] for c in CONDITIONS]
        assert values[0]<min(values[1:])
        plotted.append({'round':block, **dict(zip(CONDITIONS,values))})
        ax.plot(range(3),values,'-o',lw=1,label=f'Round {block}')
    ax.set_xticks(range(3),['Centered','Tilted','15 mm offset'])
    ax.set_ylabel('Contrast magnitude Q (ADC counts)')
    ax.legend(ncol=3,frameon=False,fontsize=8)
    ax.grid(alpha=.17,axis='y')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    fig.savefig(args.output_dir/'directional_contrasts.pdf')
    fig.savefig(args.output_dir/'directional_contrasts.png',dpi=180)
    plt.close(fig)
    print(json.dumps(plotted,indent=2))

if __name__=='__main__': main()
