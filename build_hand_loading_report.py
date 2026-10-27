"""Format stored hand-loading results as an HTML report; no analysis is rerun."""
from pathlib import Path
import argparse
import html
import json

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'docs/hand_loading_observations.html'

def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))

def table(headers, rows, caption):
    head = ''.join(f'<th scope="col">{html.escape(str(x))}</th>' for x in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{html.escape(str(x))}</td>' for x in row) + '</tr>' for row in rows)
    return f'<div class="table-scroll"><table><caption>{caption}</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'

def render():
    initial = read('analysis/manual_66c0b8ea13c5411b95ba2c51c7ca6e9c.json')
    followup = read('analysis/manual_15a216a084594cd28d0df6cc6a5b0010.json')
    sync = read('analysis/synchronized_press.json')
    plan = read('protocols/synchronized_press_plan.json')
    assert len(initial['pairs']) == 15 and len(followup['pairs']) == 3
    assert len(sync['S']['presses']) == 18 and len(sync['SC']['rows']) == 4 and len(sync['SX']['records']) == 2
    manual = []
    for batch, source in [('Initial',initial),('Follow-up',followup)]:
        for i,row in enumerate(source['pairs'],1):
            manual.append([f'{batch} {i}',f"{row['reported_scale_indication_g']:.0f}",
                           f"{row['recorded_device_g']:.0f}",f"{row['device_minus_reported_scale_N']:+.2f}"])
    applications = {'CENTER':'Centered','TILT_XP':'Tilted','OFFSET_XP15':'15 mm offset',
                    'CENTER_1KG':'Centered, 1 kg','CENTER_2KG':'Centered, 2 kg','CENTER_3KG':'Centered, 3 kg'}
    synchronized=[]
    for row in sync['S']['presses']:
        w=row['w1']
        synchronized.append([row['code'].replace('S_R','') if row['code']!='S_LADDER' else '1-3 kg sequence',
            applications[row['condition']],f"{w['lc_N']:.2f}",f"{w['hall_N']:.2f}",f"{w['diff_N']:.2f}",
            f"{row['w1_lag_aligned']['diff_N']:.2f}",f"{w['Q']:.1f}"])
    static=[]
    for row in sync['SC']['rows']:
        static.append([row['code'],f"{row['mass_g']:.0f}",f"{row['lc_err_N']:+.3f}",f"{row['hall_err_N']:+.2f}"])
    for row in sorted(sync['SC']['B_reference'],key=lambda x:x['mass_g']):
        static.append([f"Independent test: {row['record']}",f"{row['mass_g']:.0f}",'',f"{row['error_N']:+.2f}"])
    capture_rows=[]
    for group in ('S','SC','SX'):
        for row in sync[group]['records']:
            capture_rows.append([row['code'],row['hall_capture_id'],row['loadcell_capture_id']])
    lag=sync['SX']['lag_s_used']
    assert round(lag,2)==-0.18
    body = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hand-loading observations</title>
<style>body{font:16px/1.55 system-ui,sans-serif;color:#202a35;background:#fff;margin:0 auto;padding:36px 24px;max-width:1160px}h1{font-size:30px}h2{margin-top:36px;font-size:23px}a{color:#175b91}nav{display:flex;flex-wrap:wrap;gap:18px}p,li{max-width:95ch}.scope{border-left:4px solid #577b91;padding:8px 20px;background:#f3f6f8}.table-scroll{overflow-x:auto;margin:22px 0}table{width:100%;border-collapse:collapse;font-size:14px;font-variant-numeric:tabular-nums}caption{text-align:left;font-weight:600;padding-bottom:10px}th,td{padding:8px 10px;border-bottom:1px solid #dce2e7;text-align:right;vertical-align:top}th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}thead{background:#eef2f5}tbody tr:nth-child(even){background:#fafbfd}figure{margin:20px 0}img{width:100%;height:auto}figcaption{font-size:14px}code{font-size:.9em;overflow-wrap:anywhere}.ids td{font-family:monospace;font-size:12px}footer{border-top:1px solid #ccd5db;margin-top:32px;padding-top:16px;font-size:14px}@media print{body{font-size:11pt;padding:0}nav{display:none}table{font-size:9pt}tr{break-inside:avoid}h2{break-after:avoid}}</style>
<header><p><a href="../README.md">Data package</a> / Supplementary Material S7</p>
<h1>Hand-loading observations</h1>
<p>Complete manual and synchronized results, with the static controls and exploratory ramp figure.</p>
<nav><a href="#scope">Scope and setup</a><a href="#manual">Manual readings</a><a href="#synchronized">Synchronized presses</a><a href="#static">Static controls</a><a href="#ramps">Ramps</a><a href="#records">Records</a></nav></header>
<section id="scope"><h2>Scope and setup</h2>
<p>Series labels are synchronized presses (S), static controls on the same assembly (SC), exploratory ramps (SX), and held-out test (B).</p>
<div class="scope"><p>The manual scale readings were approximate; their temporal correspondence to the Hall averaging windows was not independently verified. In the synchronized assembly the Hall head was not mechanically fastened to the load-cell platform. A later setup check showed support deflection under load, which was not quantified during the recorded trials. The indication differences therefore are not used to quantify the force accuracy of the head itself or identify a friction mechanism.</p></div>
<p>The centered manual series used a CRW-7024 zeroed with the 343 g Hall assembly in place. The synchronized series placed the head on a 111 g load-cell platform and applied hand force to the Hall tray. The <code>setup.description</code> in the preserved <a href="../protocols/synchronized_press_plan.json">plan export</a> specifies intended taped mounting; it does not describe the actual unfastened assembly. <a href="../RECORDING_NOTES.md#hand-press-assembly-and-clock-alignment">Recording notes</a> describe the actual arrangement.</p>
<p>The S synchronized-press analysis rules were fixed before acquisition. SC was added after the S analysis, with its rules fixed before SC acquisition. SX had a separate exploratory plan from the outset. The later time-shift sensitivity is distinguished below. The separate 15-press directional-contrast experiment remains in manuscript Figure 4 and Supplementary Material S7; it is not the S series tabulated here.</p></section>
<section id="manual"><h2>Manual scale readings: all 18 pairs</h2>
<p>For each press, the last complete 100-sample device window ending before the reading cue was paired with the entered scale indication. All 15 initial presses and three follow-up presses are shown. The follow-up used a new display zero and the same calibration. No synchronized scale stream or video was recorded. The difference column uses the stored unrounded readings, so rounded gram columns may not reproduce its last digit.</p>
'''
    body += table(['Press','Entered scale (g)','Recorded device (g)','Device minus scale (N)'],manual,'Table 1. Manual indication pairs.')
    body += '''<p>Sources: <a href="../analysis/manual_66c0b8ea13c5411b95ba2c51c7ca6e9c.json">initial series</a> and <a href="../analysis/manual_15a216a084594cd28d0df6cc6a5b0010.json">follow-up series</a>. The records include window timing, scale entries and device output checks.</p></section>
<section id="synchronized"><h2>Synchronized presses: all 18 presses</h2>
<p>Hall and load-cell device clocks were mapped to host UTC by linear regression. A press was detected above 0.3 kg for at least 1.5 s. Release was the last sample at or above 90% of the median force over the middle half of that interval. The analysis window was the final 1 s before release; a 3 s window was also evaluated. Onset was the last sample at or below 0.05 kg preceding the interval. Both systems used the 3 s ending 0.2 s before onset as unloaded reference. Hall indications used the frozen four-channel interpolation. These rules are in the preserved plan export.</p>
'''
    body += f'<p>The later timing sensitivity shifted the Hall windows by the median edge lag ({lag:.2f} s, Hall minus load-cell edge time). Each edge was the rising 50% crossing of that system\'s own plateau. The lag-shifted column remains a sensitivity calculation; it does not replace the original window result.</p>'
    body += table(['Round','Application','Load cell (N)','Hall (N)','Hall minus load cell (N)','Lag-shifted difference (N)','Q (ADC counts)'],synchronized,'Table 2. Synchronized calibrated indications and contrast magnitude.')
    body += '''<p><i>Q</i> is the magnitude of the two signed channel contrasts. Stored one-second, three-second and shifted-window values are in <a href="../analysis/synchronized_press.json">synchronized_press.json</a>; <a href="../reproduce_synchronized.py">reproduce_synchronized.py</a> reconstructs them.</p></section>
<section id="static"><h2>Static controls on the synchronized assembly</h2>
<p>Each loaded record used its preceding unloaded record and the mean over 10-20 s of device time. Indication minus known mass times 0.00980665 N/g is listed for both systems. The four nearest-mass independent B placements are retained below for comparison; they used a different test arrangement and are not matched repetitions of SC.</p>
'''
    body += table(['Record','Mass (g)','Load cell minus applied load (N)','Hall minus applied load (N)'],static,'Table 3. All four SC placements and the previously listed B comparisons.')
    body += '''</section><section id="ramps"><h2>Separate exploratory ramps</h2>
<p>Two 90 s records each contained two slow centered loading and unloading ramps, approximately 0 to 3 kg in 10 s, a 2 s hold, and return to zero in 10 s. Both systems were referenced to the first 3 s of each record. At each load-cell sample, the Hall indication was averaged over +/-0.05 s around the time shifted by the median S lag. Loading, unloading and hold branches used the gradient of the five-sample smoothed load-cell force; an absolute gradient below 0.2 N/s was classified as hold.</p>
<figure><img src="figures/synchronized_ramps.png" alt="Recorded calibrated Hall and load-cell indications during the first ramp record, and paired indications from both records grouped by loading, unloading and hold.">
<figcaption>Figure 1. Left: the first ramp record. Right: paired indications from both records, with branches shown separately. The dashed line denotes equal indications. These traces describe the two recorded indications on the combined assembly; they do not isolate the contribution of the head or support.</figcaption></figure>
<p>The stored summaries are in <a href="../analysis/synchronized_press.json">synchronized_press.json</a>. Reproduction: <code>python reproduce_synchronized.py</code>. Figure regeneration: <code>python plot_synchronized_ramps.py --output-dir figures</code>.</p></section>
<section id="records"><h2>Record links and analysis history</h2>
<p>The <a href="../raw_index.json">raw index</a> maps the capture IDs below to the compressed measurement files. The <a href="../DATA_DICTIONARY.md">data dictionary</a> defines the timestamp and channel fields. Initial manual capture: <code>66c0b8ea13c5411b95ba2c51c7ca6e9c</code>; follow-up capture: <code>15a216a084594cd28d0df6cc6a5b0010</code>.</p>
<div class="ids">
'''
    body += table(['Record','Hall capture','Load-cell capture'],capture_rows,'Capture pairs used by the stored S, SC and SX analyses.')
    body += '</div><p>The original frozen plan hashes are retained in <a href="../protocols/synchronized_press_plan.json">synchronized_press_plan.json</a>. The S, SC and SX roles are distinct:</p><ul>'
    for key in ('S','SC','SX'):
        body += f'<li><strong>{key}:</strong> {html.escape(plan[key]["role"])}</li>'
    body += '''</ul></section><footer>This report formats the stored numerical results without refitting models, choosing new windows or excluding rows. To check its rendering against those values, run <code>python build_hand_loading_report.py --check</code>.</footer></html>'''
    return body

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Check the report without writing files.')
    args=parser.parse_args()
    content=render()
    if args.check:
        assert OUTPUT.read_text(encoding='utf-8')==content, 'Stored report differs from formatted results'
        assert (ROOT/'docs/figures/synchronized_ramps.png').is_file()
        print('PASS: 18 manual pairs, 18 synchronized presses, 4 static controls, 4 B comparisons and 2 ramp records.')
    else:
        OUTPUT.parent.mkdir(parents=True,exist_ok=True)
        OUTPUT.write_text(content,encoding='utf-8',newline='\n')
        print(OUTPUT)

if __name__=='__main__':
    main()
