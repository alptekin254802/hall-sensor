"""Live 10 s screening of decoded Hall samples; no serial access or raw edits."""
import hashlib
import json
import math
from pathlib import Path
import statistics
import time

VERSION = '1.0.0'
WINDOW_US = 10_000_000
CHANNELS = ('s1_adc', 's2_adc', 's3_adc', 's4_adc')


class NoiseWindows:
    def __init__(self, threshold=15.0):
        self.threshold = threshold
        self.index = None
        self.rows = []
        self.previous = None
        self.period_us = None

    def feed(self, sample, host_utc_ns, period_us):
        if period_us <= 0 or WINDOW_US % period_us:
            raise ValueError('Unsupported sample period')
        if self.period_us not in (None, period_us):
            raise ValueError('Sample period changed')
        self.period_us = period_us
        index = sample.t_us // WINDOW_US
        reports = []
        if self.index is not None and index != self.index:
            reports.append(self._finish(True))
        if self.index is None:
            self.index = index
        gap = (sample.seq != 0) if self.previous is None else (
            sample.seq != self.previous.seq + 1 or sample.t_us - self.previous.t_us != period_us)
        if self.previous and sample.t_us <= self.previous.t_us:
            raise ValueError('Time moved backwards; new acquisition requires a new monitor')
        values = [getattr(sample, name) for name in CHANNELS]
        if any(v is None or not 0 <= v <= 4095 for v in values):
            raise ValueError('Four valid 12-bit channels required')
        self.rows.append((sample.t_us, values, host_utc_ns, gap,
                          bool(sample.flags or sample.dropped or sample.tx_errors)))
        self.previous = sample
        if sample.t_us + period_us >= (index + 1) * WINDOW_US:
            reports.append(self._finish(True))
        return reports

    def finish(self):
        return self._finish(False) if self.rows else None

    def _finish(self, closed):
        rows, index = self.rows, self.index
        self.rows, self.index = [], None
        count = len(rows)
        expected = WINDOW_US // self.period_us
        coverage = count == expected and not any(row[3] for row in rows)
        raw_sd, residual_sd, delta, rails = [], [], [], []
        times = [row[0] / 1e6 for row in rows]
        tx = statistics.fmean(times) if times else 0
        xx = sum((t-tx)**2 for t in times)
        for ch in range(4):
            values = [row[1][ch] for row in rows]
            mean = statistics.fmean(values) if values else None
            slope = sum((t-tx)*(v-mean) for t,v in zip(times, values))/xx if xx else 0
            raw_sd.append(statistics.stdev(values) if count > 1 else None)
            residual_sd.append(math.sqrt(sum((v-mean-slope*(t-tx))**2 for t,v in zip(times, values))/(count-1)) if count > 1 else None)
            delta.append(slope*10 if count else None)
            rails.append(any(v in (0,4095) for v in values))
        high_raw = any(sd is not None and sd > self.threshold for sd in raw_sd)
        noise = any(sd is not None and sd > self.threshold for sd in residual_sd)
        fault = any(rails) or any(row[4] for row in rows) or (closed and not coverage)
        status = ('partial_window' if not closed else 'acquisition_alert' if fault
                  else 'noise_alert' if noise else 'level_change_review' if high_raw else 'quiet_window')
        return dict(window_index=index, start_s=index*10, end_s=(index+1)*10,
            sample_count=count, expected_samples=expected, complete=bool(closed and coverage),
            first_host_utc_ns=rows[0][2] if rows else None,
            last_host_utc_ns=rows[-1][2] if rows else None,
            raw_sd_adc=raw_sd, detrended_sd_adc=residual_sd, fitted_change_adc_per_10s=delta,
            raw_sd_threshold_exceeded=high_raw, rapid_variation_alert=noise,
            sequence_or_time_gap=any(row[3] for row in rows), adc_rail=rails,
            device_flag_or_counter=any(row[4] for row in rows), status=status,
            analysis_disposition=('exclude_from_stationary_thermal_summary' if status in ('noise_alert','acquisition_alert','partial_window')
                                  else 'review_level_change' if high_raw else 'screen_only'),
            interpretation='Operational signal screening, not a force-error or causal electrical-noise diagnosis.')


class LiveNoiseMonitor:
    def __init__(self, capture, output_root, callback=print):
        self.capture = Path(capture).resolve()
        self.folder = (Path(output_root)/self.capture.name).resolve()
        if self.folder == self.capture or self.capture in self.folder.parents:
            raise ValueError('Live reports must be outside raw capture')
        self.folder.mkdir(parents=True, exist_ok=True)
        self.stream = (self.folder/'windows.jsonl').open('x', encoding='utf-8')
        try:self.events = (self.folder/'events.jsonl').open('x', encoding='utf-8')
        except Exception:
            self.stream.close()
            raise
        self.estimator = NoiseWindows()
        self.callback = callback
        self.total = self.flagged = self.raw_high = self.streak = self.issue_count = 0
        self.last_stale_notice = 0

    def observe(self, sample, utc_ns, period_us):
        for report in self.estimator.feed(sample, utc_ns, period_us):self._report(report)

    def _report(self, report):
        alert = report['status'] in ('noise_alert','acquisition_alert')
        self.total += 1
        self.flagged += int(alert)
        self.raw_high += int(report['raw_sd_threshold_exceeded'])
        self.streak = self.streak+1 if alert else 0
        report.update(capture_id=self.capture.name, total_windows=self.total,
                      flagged_windows=self.flagged, raw_high_windows=self.raw_high,
                      consecutive_alerts=self.streak, threshold_adc=15.0)
        self.stream.write(json.dumps(report, allow_nan=False)+'\n');self.stream.flush()
        self.callback('LIVE_NOISE '+json.dumps(report, allow_nan=False))

    def issue(self, code, **details):
        self.issue_count += 1
        self.events.write(json.dumps(dict(kind='acquisition_issue', code=code, host_utc_ns=time.time_ns(), details=details))+'\n')
        self.events.flush()
        self.callback('LIVE_ACQ '+code)

    def stale(self, seconds):
        if seconds >= 2 and time.monotonic()-self.last_stale_notice > 5:
            self.last_stale_notice = time.monotonic()
            self.issue('hall_stream_stale', age_s=seconds)

    def close(self, source_hashes, status):
        partial = self.estimator.finish()
        if partial:self._report(partial)
        self.stream.close();self.events.close()
        report = dict(version=VERSION, capture_id=self.capture.name, source_sha256=source_hashes,
            capture_status=status, windows=self.total, flagged_windows=self.flagged,
            raw_sd_exceeded_windows=self.raw_high, acquisition_issues=self.issue_count,
            raw_modified=False, auto_power_cycle=False,
            analyzer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            exclusion_policy='Keep all raw data. Flagged windows are excluded from stationary thermal summaries with this manifest; level-change windows require review. Power-separated captures require separate references.')
        (self.folder/'review.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
