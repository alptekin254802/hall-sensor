"""Raw HX711 recording. Port access requires an explicit Connection.open call."""
import binascii
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import secrets
import statistics
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
RELEASE='HX711_RAW_R1'

def encode(body):
    raw=body.encode('ascii')
    return raw+b'*'+f'{binascii.crc_hqx(raw,0xffff):04X}\n'.encode('ascii')

def parse(line):
    try:
        body,checksum=line.rstrip(b'\r\n').rsplit(b'*',1)
        if len(checksum)!=4 or int(checksum,16)!=binascii.crc_hqx(body,0xffff):
            raise ValueError('crc_mismatch')
        fields=body.decode('ascii').split(',');kind=fields[0]
        if kind=='M' and len(fields)==5:
            result={'kind':kind,'protocol':int(fields[1]),'release':fields[2],
                    'gain':int(fields[3]),'token':int(fields[4])}
            if result['protocol']!=1 or result['release']!=RELEASE or result['gain']!=128:
                raise ValueError('unsupported_firmware')
            return result
        if kind=='D' and len(fields)==6:
            token,seq,tick,raw,dropped=map(int,fields[1:])
            if not all(0<=v<=0xffffffff for v in (token,seq,tick,dropped)) or not -8388608<=raw<=8388607:
                raise ValueError('invalid_integer_range')
            return dict(kind=kind,token=token,seq=seq,tick=tick,raw=raw,dropped=dropped)
        if kind=='S' and len(fields)==4:
            return dict(kind=kind,token=int(fields[1]),count=int(fields[2]),dropped=int(fields[3]))
        if kind=='E' and len(fields)==3:return dict(kind=kind,token=int(fields[1]),code=fields[2])
        raise ValueError('unknown_frame')
    except (UnicodeError,IndexError) as exc:raise ValueError('malformed_frame') from exc

def fixture_mass_for_capacity(context):
    """Use actual moving mass, or a separately labelled whole-fixture upper bound."""
    moving=context.get('platform_mass_g')
    if moving is not None:
        value=moving
    else:
        if context.get('fixture_mass_basis')!='whole_fixture_measured_upper_bound':
            raise ValueError('Kapasite için tartılmış üst takım veya komple düzenek toplamı gerekli.')
        value=context.get('fixture_mass_upper_bound_g')
    if not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
        raise ValueError('Tartılan toplamı pozitif gram olarak gir.')
    return value

def validate_context(row,capacity_g,platform_g):
    if not all(math.isfinite(x) and x>0 for x in (capacity_g,platform_g)):
        raise ValueError('Kapasite ve hareketli platform kütlesini pozitif gram olarak gir.')
    mass=row['reference_mass_g']
    if mass is None or not math.isfinite(mass) or mass<0:raise ValueError('Geçersiz plan kütlesi.')
    # A tare does not restore capacity. Keep a 100 g handling margin.
    if mass+platform_g>capacity_g-100:
        raise ValueError(f"Bu satır kapasiteye uygun değil: {mass:g} + {platform_g:g} g. Bu ağırlığı koyma; satırı atla.")

class Tracker:
    def __init__(self,token):
        self.token=token;self.previous=None;self.elapsed_us=0;self.rows=[];self.issues=[];self.metadata=None
    def issue(self,code,**extra):self.issues.append(dict(code=code,**extra))
    def feed(self,line,host_s=0):
        try:f=parse(line)
        except ValueError as exc:self.issue(str(exc));return None
        if f['token']!=self.token:
            self.issue('session_token_mismatch',observed_token=f['token']);return None
        if f['kind']=='M':self.metadata=f;return None
        if f['kind']=='E':self.issue('device_error',message=f['code']);return None
        if f['kind']!='D':return None
        if self.metadata is None:self.issue('data_before_metadata');return None
        if self.previous:
            gap=(f['seq']-self.previous['seq'])&0xffffffff
            if gap!=1:self.issue('sequence_gap',previous=self.previous['seq'],current=f['seq'])
            dt=(f['tick']-self.previous['tick'])&0xffffffff
            if dt==0 or dt>3000000:self.issue('device_time_gap',delta_us=dt)
            self.elapsed_us+=dt
        elif f['seq']!=0:self.issue('initial_sequence_loss',first_sequence=f['seq'])
        if f['raw'] in (-8388608,8388607):self.issue('adc_rail',seq=f['seq'])
        if f['dropped'] and (not self.previous or f['dropped']!=self.previous['dropped']):
            self.issue('device_transmit_drop',count=f['dropped'])
        self.previous=f
        row=dict(host_elapsed_s=host_s,elapsed_s=self.elapsed_us/1e6,sequence=f['seq'],
                 device_micros=f['tick'],raw_counts=f['raw'],device_dropped=f['dropped'])
        self.rows.append(row);return row
    def report(self,expected_rate=10):
        rows=self.rows;duration=rows[-1]['elapsed_s'] if rows else 0
        rate=(len(rows)-1)/duration if duration>0 else None
        if rate is None or not expected_rate*.8<=rate<=expected_rate*1.2:
            self.issue('sample_rate_mismatch',measured_hz=rate,expected_hz=expected_rate)
        values=[r['raw_counts'] for r in rows if r['elapsed_s']>=max(0,duration-10)]
        first=[r['raw_counts'] for r in rows if r['elapsed_s']<5]
        last=[r['raw_counts'] for r in rows if r['elapsed_s']>=max(0,duration-5)]
        return dict(valid_records=len(rows),duration_s=duration,measured_rate_hz=rate,
            mean_last_10s_counts=statistics.mean(values) if values else None,
            sd_last_10s_counts=statistics.stdev(values) if len(values)>1 else None,
            last_minus_first_5s_counts=statistics.mean(last)-statistics.mean(first) if first and last else None,
            issues=self.issues,metadata=self.metadata,
            interpretation='HX711 raw counts; Hall 15 ADC threshold does not apply; no gram accuracy verdict.')

class Connection:
    def __init__(self,port):self.port=port;self.serial=None
    def open(self):
        import serial
        self.serial=serial.Serial(self.port,115200,timeout=.2,write_timeout=1)
        # Uno USB DTR normally resets once when opening, not between records.
        time.sleep(2);self.serial.reset_input_buffer();self.serial.write(b'HELLO\n')
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            line=self.serial.readline(256)
            try:f=parse(line)
            except ValueError:continue
            if f['kind']=='M':return f
        self.close();raise RuntimeError('HX711 firmware yanıtı yok; port/kart ve yüklenen yazılımı kontrol et.')
    def close(self):
        if self.serial:
            try:self.serial.write(b'STOP\n')
            except Exception:pass
            self.serial.close();self.serial=None
    def record(self,row,context,stop_event,notify=lambda _:None,out_root=None):
        if not self.serial:raise RuntimeError('Önce Arduino bağlantısını aç.')
        validate_context(row,context['capacity_g'],fixture_mass_for_capacity(context))
        out=(Path(out_root) if out_root else ROOT/'recordings/loadcell')/uuid.uuid4().hex
        out.mkdir(parents=True,exist_ok=False)
        token=secrets.randbelow(0xfffffffe)+1;tracker=Tracker(token)
        started=time.monotonic();last_data=started;status='recording';duration=row['duration_s'];stop_ack=None
        session=dict(schema_version=1,capture_id=out.name,record=row,context=context,token=token,
                     started_utc=datetime.now(timezone.utc).isoformat(),status=status,
                     timestamp_meaning='device_micros at observed ready signal; host timestamps are receipt times',
                     firmware_source_sha256=hashlib.sha256((ROOT/'firmware/hx711_reference/hx711_reference.ino').read_bytes()).hexdigest())
        (out/'session.json').write_text(json.dumps(session,indent=2)+'\n',encoding='utf-8')
        try:
            self.serial.reset_input_buffer();self.serial.write(f'START,{token}\n'.encode('ascii'))
            with (out/'serial.raw').open('wb') as rawfile,(out/'samples.csv').open('w',newline='',encoding='utf-8') as table:
                writer=csv.DictWriter(table,fieldnames=['host_elapsed_s','elapsed_s','sequence','device_micros','raw_counts','device_dropped']);writer.writeheader()
                pending=b'';last_notice=-1
                while not stop_event.is_set():
                    chunk=self.serial.readline(256);rawfile.write(chunk);rawfile.flush();pending+=chunk
                    if len(pending)>1024:tracker.issue('oversize_line');pending=b''
                    while b'\n' in pending:
                        line,pending=pending.split(b'\n',1)
                        record=tracker.feed(line+b'\n',time.monotonic()-started)
                        if record:
                            writer.writerow(record);table.flush();last_data=time.monotonic()
                            second=int(record['elapsed_s'])
                            if second!=last_notice:notify(f"{row['record_code']} — {second}/{duration:g} s, {len(tracker.rows)} örnek");last_notice=second
                    if tracker.rows and tracker.rows[-1]['elapsed_s']>=duration:
                        status='finished';break
                    if time.monotonic()-last_data>3:
                        tracker.issue('data_stale');status='failed';break
                    if time.monotonic()-started>duration+10:
                        tracker.issue('duration_timeout');status='failed';break
                else:status='stopped_early';tracker.issue('manual_stop')
                if pending:tracker.issue('partial_line_at_stop')
        except Exception as exc:
            status='failed';tracker.issue('capture_exception',message=str(exc))
        finally:
            try:
                self.serial.write(b'STOP\n')
                deadline=time.monotonic()+1
                with (out/'serial.raw').open('ab') as rawfile:
                    while time.monotonic()<deadline:
                        line=self.serial.readline(256);rawfile.write(line)
                        try:frame=parse(line)
                        except ValueError:continue
                        if frame['kind']=='S' and frame['token']==token:
                            stop_ack=frame;break
                if stop_ack is None:tracker.issue('stop_ack_missing')
                elif stop_ack['dropped']:
                    tracker.issue('device_drop_at_stop',count=stop_ack['dropped'])
            except Exception:tracker.issue('stop_command_failed')
            report=tracker.report(context.get('expected_rate_hz',10))
            if status=='finished' and tracker.issues:status='finished_with_issues'
            session.update(status=status,ended_utc=datetime.now(timezone.utc).isoformat(),summary=report,stop_ack=stop_ack)
            session['source_hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.name in ('samples.csv','serial.raw')}
            (out/'issues.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in tracker.issues),encoding='utf-8')
            (out/'session.json').write_text(json.dumps(session,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
            (out/'review.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        return out,session
