"""CRC-framed ASCII protocol. ADC counts are unsigned; no calibration here."""
from dataclasses import dataclass
import binascii
import json
import re

class ProtocolError(ValueError):
    pass

@dataclass(frozen=True)
class Display:
    last_seq: int
    first_seq: int
    count: int
    sum_adc: int
    zero_sum_adc: int
    zero_epoch: int
    status: int
    mass_mg: int | None

def valid_rom(text):
    if not isinstance(text,str) or not re.fullmatch(r"28[0-9a-f]{14}",text): return False
    crc=0
    for byte in bytes.fromhex(text):
        for bit in range(8):
            mix=(crc^(byte>>bit))&1;crc>>=1
            if mix: crc^=0x8c
    return crc==0

@dataclass(frozen=True)
class Temperature:
    cycle: int
    slot: int
    rom: str
    start_us: int
    ready_us: int
    read_us: int
    raw16: int | None
    status: int

    @property
    def temperature_c(self):
        return self.raw16/16 if self.raw16 is not None else None

def encode(body):
    data = body.encode("ascii")
    return data + f"*{binascii.crc_hqx(data, 0xffff):04X}\n".encode("ascii")

@dataclass(frozen=True)
class Sample:
    seq: int
    t_us: int
    s1_adc: int
    s2_adc: int
    flags: int
    dropped: int
    tx_errors: int
    dma_phase_us: int
    s3_adc: int | None = None
    s4_adc: int | None = None

    @property
    def channel_count(self):
        return 4 if self.s3_adc is not None else 2

class LineDecoder:
    def __init__(self, limit=4096):
        self.buffer = bytearray()
        self.limit = limit
        self.discarding = False

    def feed(self, chunk):
        """Yield (line, error); preserve arbitrary transport chunk boundaries."""
        for byte in chunk:
            if self.discarding:
                if byte == 10:
                    self.discarding = False
                continue
            self.buffer.append(byte)
            if byte == 10:
                yield bytes(self.buffer), None
                self.buffer.clear()
            elif len(self.buffer) > self.limit:
                yield bytes(self.buffer), "line_too_long"
                self.buffer.clear()
                self.discarding = True

    def finish(self):
        if self.buffer or self.discarding:
            return bytes(self.buffer), "truncated_line"
        return None

def parse_line(line):
    try:
        body, crc = line.rstrip(b"\r\n").rsplit(b"*", 1)
        if len(crc) != 4 or int(crc, 16) != binascii.crc_hqx(body, 0xffff):
            raise ProtocolError("crc_mismatch")
        text = body.decode("ascii")
        kind, payload = text.split(",", 1)
        if kind == "M":
            m = json.loads(payload)
            required = {"protocol", "session_id", "firmware", "build_id", "rate_hz", "period_us",
                        "baud", "s1", "s2", "time_basis"}
            if not isinstance(m, dict) or not required <= m.keys():
                raise ProtocolError("metadata_missing_fields")
            if type(m["protocol"]) is not int or m["protocol"] not in {1,2} or not re.fullmatch(r"[0-9a-f]{32}", m["session_id"]):
                raise ProtocolError("metadata_protocol_or_session")
            if not re.fullmatch(r"[0-9a-f]{16}", m["build_id"]):
                raise ProtocolError("unidentified_build")
            if (type(m["rate_hz"]) is not int or not 20<=m["rate_hz"]<=1000 or
                type(m["period_us"]) is not int or not 1000<=m["period_us"]<=50000 or
                m["rate_hz"]*m["period_us"] != 1000000):
                raise ProtocolError("metadata_timebase")
            if m["time_basis"] != "nominal_TIM3_trigger_seq0_epoch":
                raise ProtocolError("unsupported_timebase")
            if (m["s1"], m["s2"]) != ("ADC1_IN0_PA0_rank1", "ADC1_IN1_PA1_rank2"):
                raise ProtocolError("channel_mapping")
            count = 4 if m["protocol"] == 2 else 2
            if m.get("channel_count", 2) != count:
                raise ProtocolError("channel_count")
            if count == 4 and (m.get("s3"),m.get("s4")) != ("ADC1_IN5_PA5_rank3","ADC1_IN6_PA6_rank4"):
                raise ProtocolError("channel_mapping")
            if count == 2 and any(k in m for k in ("s3","s4")):
                raise ProtocolError("unexpected_channels")
            return kind, m
        if kind == "Q":
            m=json.loads(payload)
            if (not isinstance(m,dict) or m.get("protocol")!=1 or m.get("pin")!="PB7" or
                m.get("time_basis")!="HAL_tick_relative_first_TIM3_trigger" or
                type(m.get("count")) is not int or not 0<=m["count"]<=2 or
                not isinstance(m.get("roms"),list) or len(m["roms"])!=2):
                raise ProtocolError("temperature_metadata")
            known=m["roms"][:m["count"]]
            if (any(not valid_rom(r) for r in known) or len(set(known))!=len(known) or
                any(r!="0"*16 for r in m["roms"][m["count"]:])):
                raise ProtocolError("temperature_roms")
            return kind,m
        if kind == "T":
            f=payload.split(',')
            if len(f)!=8: raise ProtocolError("temperature_fields")
            if any(not re.fullmatch(r"[0-9]+",f[i]) for i in [0,1,3,4,5,7]):
                raise ProtocolError("temperature_fields")
            cycle,slot,t0,t1,t2,status=(int(f[i]) for i in [0,1,3,4,5,7])
            if not (cycle<2**32 and slot in (0,1) and 0<=t0<=t1<=t2<2**64 and status in range(9)):
                raise ProtocolError("temperature_range")
            if not (valid_rom(f[2]) or f[2]=='0'*16):raise ProtocolError("temperature_rom")
            raw=None
            if status==0:
                if not valid_rom(f[2]) or not re.fullmatch(r"-?[0-9]+",f[6]):raise ProtocolError("temperature_value")
                raw=int(f[6])
                if not -880<=raw<=2000:raise ProtocolError("temperature_value")
            elif f[6]!='NA':raise ProtocolError("temperature_error_has_value")
            return kind,Temperature(cycle,slot,f[2],t0,t1,t2,raw,status)
        if kind == "V":
            fields=payload.split(',')
            if len(fields)!=8 or any(not re.fullmatch(r'[0-9]+',v) for v in fields[:7]):
                raise ProtocolError('display_fields')
            last,first,count,total,zero,epoch,status=map(int,fields[:7])
            if not (0<=first<=last<2**32 and count==100 and last-first==count-1
                    and 0<=total<=4095*4*count and 0<=zero<=4095*4*count
                    and epoch<2**32 and status in range(7)):
                raise ProtocolError('display_range')
            mass=None
            if status in (1,2):
                if not epoch or not re.fullmatch(r'-?[0-9]+',fields[7]):raise ProtocolError('display_mass')
                mass=int(fields[7])
                if not -50000<=mass<=5000000:raise ProtocolError('display_mass')
            elif fields[7]!='NA':raise ProtocolError('display_invalid_has_value')
            return kind,Display(last,first,count,total,zero,epoch,status,mass)
        if kind == "D":
            fields = payload.split(",")
            if len(fields) not in {8,10} or any(not re.fullmatch(r"[0-9]+", v) for v in fields):
                raise ProtocolError("sample_fields")
            vals = [int(v) for v in fields]
            count = len(fields)-6
            limits = [2**32-1, 2**64-1] + [4095]*count + [7, 2**32-1, 2**32-1, 65535]
            if any(v > limit for v, limit in zip(vals, limits)):
                raise ProtocolError("sample_range")
            if count == 2: return kind, Sample(*vals)
            return kind, Sample(*vals[:4], *vals[6:], *vals[4:6])
        if kind in {"E", "F"}:
            vals = payload.split(",")
            if len(vals) != (5 if kind == "E" else 2) or any(not v.isdigit() for v in vals):
                raise ProtocolError("status_fields")
            numbers = tuple(map(int, vals))
            if any(v >= 2**32 for v in numbers):
                raise ProtocolError("status_range")
            return kind, numbers
        if kind in {"B", "X"}:
            return kind, payload
        raise ProtocolError("unknown_message")
    except (UnicodeError, ValueError, TypeError, KeyError) as e:
        if isinstance(e, ProtocolError):
            raise
        raise ProtocolError("malformed_frame") from e
