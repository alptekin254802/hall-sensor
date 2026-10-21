"""Capture diagnostic frames and separately marked events. Never flashes a device."""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import queue
import shlex
import sys
import threading
import time
import uuid
import csv
from collections import deque
from .protocol import LineDecoder, ProtocolError, parse_line, valid_rom

from .labels import initial_label, export_capture

ROOT = Path(__file__).resolve().parents[1]

def event_from_text(text):
    parts = shlex.split(text)
    if not parts:
        return None
    kind, *args = parts
    event = dict(kind=kind, reference_value=None, reference_unit=None, position=None,
                 repetition=None, cycle=None, tare_s1_adc=None, tare_s2_adc=None,
                 tare_s3_adc=None, tare_s4_adc=None,
                 temperature_c=None, note=None)
    if kind == "load":
        if len(args) not in {0, 2, 3, 4, 5}:
            raise ValueError("load [VALUE UNIT [POSITION [REPETITION [CYCLE]]]]")
        if args:
            event["reference_value"] = float(args[0])
            if event["reference_value"] < 0: raise ValueError("Reference cannot be negative")
            if args[1] not in {"N", "g", "kg"}:
                raise ValueError("Reference unit must be N, g or kg; no implicit conversion")
            event["reference_unit"] = args[1]
        if len(args) > 2: event["position"] = args[2]
        if len(args) > 3: event["repetition"] = int(args[3])
        if len(args) > 4: event["cycle"] = int(args[4])
    elif kind == "unload":
        event["note"] = " ".join(args) or None
    elif kind == "tare":
        if len(args) not in {0, 2, 4}: raise ValueError("tare [S1 S2 [S3 S4]]")
        if args:
            for i,value in enumerate(args,1): event[f"tare_s{i}_adc"] = float(value)
            if not all(0 <= event[f"tare_s{i}_adc"] <= 4095 for i in range(1,len(args)+1)):
                raise ValueError("ADC references must lie in 0..4095")
        event["note"] = "Annotation only; firmware raw values are unchanged"
    elif kind == "temp":
        if len(args) != 1: raise ValueError("temp MEASURED_CELSIUS")
        event["temperature_c"] = float(args[0])
    elif kind in {"note", "position"}:
        event["position" if kind == "position" else "note"] = " ".join(args) or None
    else:
        raise ValueError("Use load, unload, tare, temp, position, note or quit")
    for value in event.values():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Use missing fields for unknowns, not NaN/inf")
    return event

class Session:
    def __init__(self, out, capture_id=None, expected_session=None, origin="serial", context=None):
        self.capture_id = capture_id or uuid.uuid4().hex
        if not self.capture_id.isalnum(): raise ValueError("Unsafe capture id")
        self.path = Path(out) / self.capture_id
        self.path.mkdir(parents=True, exist_ok=False)
        self.files = []
        def open_new(name, mode):
            f = (self.path / name).open(mode, **({} if "b" in mode else {"encoding":"utf-8", "newline":""}))
            self.files.append(f)
            return f
        self.raw = open_new("serial.raw", "xb")
        self.transport = open_new("transport.jsonl", "x")
        self.issues = open_new("issues.jsonl", "x")
        self.events = open_new("events.jsonl", "x")
        self.samples_file = open_new("samples.csv", "x")
        self.temperatures_file = open_new("temperatures.csv", "x")
        self.temperature_writer=csv.DictWriter(self.temperatures_file,fieldnames=[
            "session_id","cycle","slot","rom","role","start_us","ready_us","read_us",
            "raw16","temperature_c","status","host_utc_ns","host_monotonic_ns"])
        self.temperature_writer.writeheader()
        self.temperature_metadata=None
        self.temperature_last={}
        self.temperature_count=0
        self.display_writer=None
        self.display_count=0
        self.display_last=None
        self.display_window=deque(maxlen=100)
        self.writer = None  # Columns come from validated metadata, not guessed channels.
        self.decoder = LineDecoder()
        self.expected_session = expected_session
        self.metadata = None
        self.last = None
        self.count = 0
        self.issue_count = 0
        self.live_monitor = None
        self.live_monitor_disabled = False
        self.end = None
        self.fatal = False
        self.offset = 0
        self.state = {"capture_id":self.capture_id, "origin":origin, "context":context or {},
                      "created_utc_ns":time.time_ns(), "status":"recording",
                      "capture_code_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      "event_time_semantics":"host mark linked to latest received sample, not exact ADC load onset"}
        self._save()

    def _save(self):
        self.state.update(firmware_metadata=self.metadata, valid_samples=self.count,
                          temperature_metadata=self.temperature_metadata,
                          temperature_records=self.temperature_count,
                          display_records=self.display_count,
                          issue_count=self.issue_count, end_record=self.end)
        (self.path / "session.json").write_text(json.dumps(self.state, indent=2, allow_nan=False), encoding="utf-8")

    def issue(self, reason, **extra):
        self.issue_count += 1
        self.issues.write(json.dumps(dict(reason=reason, host_utc_ns=time.time_ns(), **extra), allow_nan=False)+"\n")
        self.issues.flush()
        self.monitor_call('issue',reason,**extra)

    def monitor_call(self, method, *args, **kwargs):
        if self.live_monitor is None or self.live_monitor_disabled:return
        try:getattr(self.live_monitor,method)(*args,**kwargs)
        except Exception as exc:
            self.live_monitor_disabled=True
            print('LIVE_MONITOR_ERROR '+str(exc),flush=True)
            self.issue('live_monitor_failed',message=str(exc))

    def ingest(self, chunk, utc_ns=None, monotonic_ns=None):
        utc_ns = time.time_ns() if utc_ns is None else utc_ns
        monotonic_ns = time.monotonic_ns() if monotonic_ns is None else monotonic_ns
        self.raw.write(chunk)
        self.transport.write(json.dumps(dict(offset=self.offset, length=len(chunk),
                                host_utc_ns=utc_ns, host_monotonic_ns=monotonic_ns))+"\n")
        self.offset += len(chunk)
        for line, error in self.decoder.feed(chunk):
            if error:
                self.issue(error); continue
            try:
                kind, value = parse_line(line)
            except ProtocolError as e:
                self.issue(str(e), line_ascii=line.decode("ascii", errors="backslashreplace")); continue
            if kind == "M":
                if self.expected_session and value["session_id"] != self.expected_session:
                    self.issue("unexpected_session"); self.fatal=True; continue
                if self.metadata and value != self.metadata:
                    self.issue("metadata_changed_or_device_restarted"); self.fatal=True; continue
                self.metadata=value
                if self.writer is None:
                    count=value.get("channel_count",2)
                    fields=["session_id","seq","t_us"] + [f"s{i}_adc" for i in range(1,count+1)]
                    fields += ["flags","dropped","tx_errors","dma_phase_us","host_utc_ns","host_monotonic_ns"]
                    self.writer=csv.DictWriter(self.samples_file,fieldnames=fields)
                    self.writer.writeheader()
                self._save()
            elif kind == "Q":
                if self.fatal or self.end is not None or not self.metadata or self.metadata.get("temperature_stream")!=1:
                    self.issue("temperature_metadata_without_active_session");continue
                if self.temperature_metadata and self.temperature_metadata!=value:
                    self.issue("temperature_metadata_changed");continue
                self.temperature_metadata=value
                for name in ("device_probe_rom","ambient_probe_rom"):
                    rom=self.state["context"].get(name)
                    if rom and rom not in value["roms"][:value["count"]]:self.issue("configured_probe_missing",role=name,rom=rom)
                self._save()
            elif kind == "T":
                if self.fatal or self.end is not None or not self.temperature_metadata:
                    self.issue("temperature_without_active_metadata");continue
                if value.rom!=self.temperature_metadata["roms"][value.slot]:
                    self.issue("temperature_identity_changed");continue
                previous=self.temperature_last.get(value.slot)
                expected=previous.cycle+1 if previous else 0
                if value.cycle!=expected:
                    self.issue("temperature_cycle_gap_or_reordered",slot=value.slot,expected=expected,received=value.cycle)
                    if value.cycle<expected:continue
                if previous and value.start_us<previous.read_us:
                    self.issue("temperature_time_reversed");continue
                if value.status:self.issue("temperature_probe_fault",rom=value.rom,status=value.status,cycle=value.cycle)
                role="unassigned"
                for label,key in [("device_local","device_probe_rom"),("ambient","ambient_probe_rom")]:
                    if value.rom==self.state["context"].get(key):role=label
                self.temperature_writer.writerow(dict(session_id=self.metadata["session_id"],**asdict(value),
                    role=role,temperature_c=value.temperature_c,host_utc_ns=utc_ns,host_monotonic_ns=monotonic_ns))
                self.temperature_last[value.slot]=value;self.temperature_count+=1
            elif kind == "V":
                if self.fatal or self.end is not None or not self.metadata or self.metadata.get('display_stream')!=1:
                    self.issue('display_without_active_metadata');continue
                if self.display_last and value.last_seq<=self.display_last.last_seq:
                    self.issue('display_reordered');continue
                w=self.display_window
                if (len(w)!=value.count or w[0].seq!=value.first_seq or w[-1].seq!=value.last_seq
                    or any(b.seq!=a.seq+1 for a,b in zip(w,list(w)[1:]))
                    or sum(s.s1_adc+s.s2_adc+(s.s3_adc or 0)+(s.s4_adc or 0) for s in w)!=value.sum_adc):
                    self.issue('display_raw_window_mismatch',last_seq=value.last_seq)
                if self.display_last and value.zero_epoch<self.display_last.zero_epoch:
                    self.issue('display_zero_epoch_reversed')
                if self.display_last and value.zero_epoch==self.display_last.zero_epoch and value.last_seq-self.display_last.last_seq!=100:
                    self.issue('display_window_gap',last_seq=value.last_seq)
                if self.display_writer is None:
                    f=(self.path/'display.csv').open('x',encoding='utf-8',newline='')
                    self.files.append(f)
                    self.display_writer=csv.DictWriter(f,fieldnames=['session_id',*asdict(value),'host_utc_ns','host_monotonic_ns'])
                    self.display_writer.writeheader()
                self.display_writer.writerow(dict(session_id=self.metadata['session_id'],**asdict(value),host_utc_ns=utc_ns,host_monotonic_ns=monotonic_ns))
                self.display_last=value;self.display_count+=1
            elif kind == "D":
                if self.fatal or self.end is not None:
                    self.issue("sample_after_fatal_or_end"); continue
                if not self.metadata:
                    self.issue("sample_without_metadata"); continue
                if value.channel_count != self.metadata.get("channel_count",2):
                    self.issue("sample_channel_count_mismatch"); continue
                if value.t_us != value.seq*self.metadata["period_us"]:
                    self.issue("timebase_mismatch", seq=value.seq); continue
                expected = self.last.seq+1 if self.last else 0
                if value.seq != expected:
                    self.issue("sequence_gap" if value.seq > expected else "duplicate_or_reordered",
                               expected=expected, received=value.seq)
                    if value.seq < expected: continue
                if value.dma_phase_us < 21*value.channel_count-2 or value.dma_phase_us > 500:
                    self.issue("dma_phase_outside_guard", seq=value.seq)
                old_drop = self.last.dropped if self.last else 0
                old_tx = self.last.tx_errors if self.last else 0
                old_flags = self.last.flags if self.last else 0
                if value.dropped != old_drop or value.tx_errors != old_tx or value.flags != old_flags:
                    self.issue("device_counters_or_flags", seq=value.seq, dropped=value.dropped,
                               tx_errors=value.tx_errors, flags=value.flags)
                self.writer.writerow(dict(session_id=self.metadata["session_id"], **{k:v for k,v in asdict(value).items() if v is not None},
                                          host_utc_ns=utc_ns, host_monotonic_ns=monotonic_ns))
                self.last=value; self.count+=1
                self.monitor_call('observe',value,utc_ns,self.metadata['period_us'])
                if self.metadata.get('display_stream')==1:self.display_window.append(value)
            elif kind == "E":
                self.end=value
                generated, dropped, txerr, rxerr, fatal = value
                if generated != self.count or dropped or txerr or rxerr or fatal:
                    self.issue("end_counters", generated=generated, received=self.count,
                               dropped=dropped, tx_errors=txerr, rx_errors=rxerr, fatal=fatal)
            elif kind == "F":
                self.issue("device_acquisition_fault", next_seq=value[0], fatal_bits=value[1]); self.fatal=True
            elif kind == "X":
                if value == "command_corrupt" and self.metadata is None and not self.fatal and self.end is None:
                    # Retry rejected startup commands within the existing handshake deadline.
                    # Retain the issue: a recovered session is never marked clean.
                    self.issue("startup_command_rejected", message=value, phase="before_metadata")
                else:
                    self.issue("device_command_error", message=value); self.fatal=True
            elif kind == "B" and self.metadata:
                self.issue("device_reset"); self.fatal=True

    def mark(self, text):
        event = event_from_text(text)
        if event is None: return
        if event["kind"] == "tare":
            supplied=sum(event[f"tare_s{i}_adc"] is not None for i in range(1,5))
            if supplied and (self.metadata is None or supplied != self.metadata.get("channel_count",2)):
                raise ValueError("Tare count must match validated metadata; no missing channel references")
        event.update(capture_id=self.capture_id,
                     session_id=self.metadata["session_id"] if self.metadata else None,
                     host_utc_ns=time.time_ns(), host_monotonic_ns=time.monotonic_ns(),
                     latest_received_seq=self.last.seq if self.last else None,
                     latest_received_t_us=self.last.t_us if self.last else None)
        self.events.write(json.dumps(event, allow_nan=False)+"\n"); self.events.flush()

    def flush(self):
        for f in self.files: f.flush()

    def close(self, status):
        partial = self.decoder.finish()
        if partial: self.issue(partial[1])
        if self.end is None: self.issue("missing_end_record")
        if self.metadata is None: self.issue("missing_metadata")
        if self.metadata and self.metadata.get("temperature_stream")==1:
            if not self.temperature_metadata:self.issue("missing_temperature_metadata")
            if set(self.temperature_last)!={0,1}:self.issue("missing_temperature_records")
        if self.metadata and self.metadata.get('display_stream')==1 and self.count>=100 and not self.display_count:
            self.issue('missing_display_records')
        self.flush()
        self.state["files_sha256"]={name:hashlib.sha256((self.path/name).read_bytes()).hexdigest()
                                    for name in ("serial.raw","samples.csv","temperatures.csv","events.jsonl","issues.jsonl","transport.jsonl")}
        if (self.path/'display.csv').exists():
            self.state['files_sha256']['display.csv']=hashlib.sha256((self.path/'display.csv').read_bytes()).hexdigest()
        self.state.update(status=status if not self.issue_count else status+"_with_issues", closed_utc_ns=time.time_ns())
        self._save()
        for f in self.files: f.close()

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    src=ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--port")
    src.add_argument("--replay", type=Path, help="Replay byte stream; does not contact hardware")
    ap.add_argument("--out",type=Path,default=ROOT/"recordings")
    ap.add_argument("--baud",type=int,default=230400)
    ap.add_argument("--duration",type=float,default=30,help="Host recording duration in seconds; 0 until quit")
    ap.add_argument("--idle-timeout",type=float,default=3)
    ap.add_argument("--hardware-id")
    ap.add_argument("--head-id")
    ap.add_argument("--spring-id")
    ap.add_argument("--mechanical-revision")
    ap.add_argument("--data-role", choices=["pilot","calibration","development_validation","final_evaluation"])
    ap.add_argument("--expected-channels", type=int, choices=[2,4])
    ap.add_argument("--device-probe-rom",help="16 lowercase hex characters; probe attached to fixed Hall tower")
    ap.add_argument("--ambient-probe-rom",help="16 lowercase hex characters; local air probe")
    ap.add_argument("--no-input", action="store_true")
    ap.add_argument("--load-state", choices=["unknown","loaded","unloaded","transition"], default="unknown")
    ap.add_argument("--mass-g", type=float, help="Weighed total object/container mass; not nominal bottle volume")
    ap.add_argument("--object-id")
    ap.add_argument("--position")
    ap.add_argument("--repetition", type=int)
    ap.add_argument("--cycle", type=int)
    ap.add_argument("--experiment-id", help="One shared ID for the physical experiment, even across capture files")
    ap.add_argument("--physical-loading-id", help="Reuse while the same placement remains; change after a new placement")
    ap.add_argument("--record-note")
    ap.add_argument("--live-temperature", action="store_true", help="Opt-in console temperature output; CSV always records it")
    ap.add_argument("--live-noise", action="store_true", help="10 s raw and detrended SD screening; separate derivative, never controls power")
    ap.add_argument("--live-noise-out",type=Path,default=ROOT/'recordings/live_noise')
    args=ap.parse_args(argv)
    for rom in (args.device_probe_rom,args.ambient_probe_rom):
        if rom and not valid_rom(rom):ap.error("Invalid DS18B20 ROM/family/CRC")
    if args.device_probe_rom and args.device_probe_rom==args.ambient_probe_rom:
        ap.error("Device and ambient probes must have different ROMs")
    if not math.isfinite(args.duration) or not math.isfinite(args.idle_timeout) or args.duration < 0 or args.idle_timeout <= 0:
        ap.error("Invalid duration/timeout")
    try: initial_label(vars(args), "validation")
    except ValueError as e: ap.error(str(e))
    if args.data_role in {"calibration","development_validation","final_evaluation"} and not args.experiment_id:
        ap.error("A physical --experiment-id is required for model datasets")
    for number in (args.repetition, args.cycle):
        if number is not None and number < 1: ap.error("Repetition/cycle must be positive")
    capture_id=uuid.uuid4().hex
    s=Session(args.out,capture_id,expected_session=None if args.replay else capture_id,
              origin="replay" if args.replay else "serial",context=vars(args) | {"out":str(args.out), "replay":str(args.replay) if args.replay else None,"live_noise_out":str(args.live_noise_out)})
    status="incomplete"
    serial_port=None
    print(f"Recording to {s.path}",flush=True)
    try:
        if args.live_noise:
            from .live_noise import LiveNoiseMonitor
            s.live_monitor=LiveNoiseMonitor(s.path,args.live_noise_out,callback=lambda text:print(text,flush=True))
        if args.replay:
            with args.replay.open("rb") as f:
                while chunk := f.read(37): s.ingest(chunk)
            if s.metadata and args.expected_channels and s.metadata.get("channel_count",2) != args.expected_channels:
                raise RuntimeError("Unexpected replay channel count")
            status="replay_finished"
        else:
            try: import serial
            except ImportError as e: raise RuntimeError("Install pyserial: python -m pip install -r pilot/requirements.txt") from e
            # Opening some adapters can reset the board; START is idempotent for this UUID.
            serial_port=serial.Serial(args.port,args.baud,timeout=0.1,write_timeout=1,
                                      bytesize=8,parity="N",stopbits=1,rtscts=False,dsrdtr=False)
            commands=queue.Queue()
            if not args.no_input:
                def read_input():
                    for text in sys.stdin: commands.put(text.strip())
                threading.Thread(target=read_input,daemon=True).start()
                print("Events: load [VALUE N|g|kg [POSITION [REPEAT [CYCLE]]]], unload, tare [S1 S2 [S3 S4]], temp C, note TEXT; quit")
                print("tare records an event only; raw ADC values are not changed.")
            started=time.monotonic(); last_data=started; last_start=started-2; stopping=None; flushed=started
            recording_started=None
            temperature_printed=0
            last_hall_count=0;last_hall_time=started
            while True:
                now=time.monotonic()
                if not s.metadata and not s.fatal and s.end is None and stopping is None and now-last_start >= 1:
                    serial_port.write(f"START {capture_id}\n".encode()); last_start=now
                chunk=serial_port.read(min(serial_port.in_waiting or 1,4096))
                now=time.monotonic()
                if chunk: s.ingest(chunk); last_data=now
                if s.count!=last_hall_count:last_hall_count=s.count;last_hall_time=now
                if s.metadata and stopping is None:s.monitor_call('stale',now-last_hall_time)
                if args.live_temperature and s.temperature_count!=temperature_printed:
                    temperature_printed=s.temperature_count
                    for slot,reading in sorted(s.temperature_last.items()):
                        print(f"T{slot+1} [{reading.rom}] {reading.temperature_c if reading.status==0 else 'ERROR '+str(reading.status)} C",flush=True)
                if s.metadata and args.expected_channels and s.metadata.get("channel_count",2) != args.expected_channels:
                    raise RuntimeError("Unexpected physical channel count")
                if s.metadata and recording_started is None: recording_started=now
                if not s.metadata and now-started > 6: raise RuntimeError("No valid metadata handshake")
                if s.metadata and s.metadata["baud"] != args.baud: raise RuntimeError("Metadata baud mismatch")
                while not commands.empty():
                    text=commands.get_nowait()
                    if text=="quit":
                        if stopping is None: serial_port.write(b"STOP\n"); stopping=now
                    else:
                        try: s.mark(text)
                        except ValueError as e: print(f"Event not recorded: {e}",file=sys.stderr)
                if stopping is None and (s.fatal or (args.duration and recording_started is not None and now-recording_started>=args.duration)):
                    serial_port.write(b"STOP\n"); stopping=now
                if s.end is not None: status="finished"; break
                if stopping is not None and now-stopping>3: raise RuntimeError("STOP received no end record")
                if s.metadata and now-last_data>args.idle_timeout: raise RuntimeError("Stream silent/disconnected")
                if now-flushed>=1: s.flush(); flushed=now
    except KeyboardInterrupt:
        s.state["stop_reason"]="keyboard_interrupt"
        if serial_port is not None:
            try:
                serial_port.write(b"STOP\n")
                deadline=time.monotonic()+3
                while s.end is None and time.monotonic()<deadline:
                    chunk=serial_port.read(min(serial_port.in_waiting or 1,4096))
                    if chunk:s.ingest(chunk)
                if s.end is not None:status="finished"
                else:s.issue("interrupt_stop_missing_end")
            except Exception as e:s.issue("interrupt_stop_error",message=str(e))
    except Exception as e:
        s.issue("capture_error", exception=type(e).__name__, message=str(e))
        print(str(e),file=sys.stderr)
    finally:
        if serial_port is not None:
            if s.end is None:
                try: serial_port.write(b"STOP\n")
                except Exception: pass
            serial_port.close()
        s.close(status)
        if s.live_monitor is not None:
            try:s.live_monitor.close(s.state['files_sha256'],s.state['status'])
            except Exception as exc:print('LIVE_MONITOR_ERROR Final report: '+str(exc),flush=True)
    export_failed=False
    try:
        derived=export_capture(s.path,s.path/"labeled_samples.csv")
        (s.path/"labels_manifest.json").write_text(json.dumps(derived,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print("Labelled CSV: "+str(s.path/"labeled_samples.csv"),flush=True)
    except Exception as e:
        export_failed=True
        print("Raw acquisition saved; labelled export failed: "+str(e),file=sys.stderr)
    print(f"{s.count} valid records; {s.issue_count} issues; status={s.state['status']}")
    if s.metadata and s.metadata.get('display_stream')==1:
        try:
            from .display_mass import review as review_display
            result=review_display(s.path)
            report_path=ROOT/'recordings/display_review'/s.capture_id/'review.json'
            report_path.parent.mkdir(parents=True,exist_ok=True)
            report_path.write_text(json.dumps(result,indent=2),encoding='utf-8')
            print('NEXTION / PC KONTROLU: '+str(result['display_frames'])+' pencere; '+str(len(result['pc_conversion_mismatches']))+' hesap uyusmazligi.',flush=True)
            print('Ekran durumlari: '+json.dumps(result['states'])+'\nEkran raporu: '+str(report_path),flush=True)
            if result['pc_conversion_mismatches']:export_failed=True
        except Exception as e:
            export_failed=True
            print('Nextion hesabi incelenemedi: '+str(e),file=sys.stderr)
    return 1 if s.issue_count or export_failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
