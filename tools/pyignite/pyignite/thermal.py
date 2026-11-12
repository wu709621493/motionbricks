"""Opt-in temperature guard and atomic, checksummed last-result checkpoints.

No NumPy import. Sensor reads and fsync run while the CPU is still functioning;
this cannot promise a final write after CPU failure or sudden power loss.
"""
import base64
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time


class ThermalSafetyError(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__('temperature guard stopped execution: ' + report['state'])


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


class CheckpointStore:
    """RAM staging -> file fsync -> atomic replace -> directory fsync on POSIX."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def commit(self, payload):
        data = _encoded(payload)
        envelope = _encoded({'schema_version': 1, 'payload': payload,
                             'payload_sha256': hashlib.sha256(data).hexdigest()}) + b'\n'
        name = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix='.' + self.path.name + '.',
                                             delete=False) as stream:
                name = stream.name
                stream.write(envelope)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
            name = None
            if os.name == 'posix':
                fd = os.open(self.path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
                return 'FILE_AND_DIRECTORY_FSYNC_COMPLETED'
            return 'FILE_FSYNC_ONLY'
        finally:
            if name is not None:
                try:
                    os.unlink(name)
                except FileNotFoundError:
                    pass

    def load(self):
        record = json.loads(self.path.read_bytes())
        if record.get('schema_version') != 1 or hashlib.sha256(_encoded(record['payload'])).hexdigest() != record.get('payload_sha256'):
            raise ValueError('checkpoint checksum/schema mismatch')
        return record['payload']


def read_linux_cpu_temperatures(root='/sys/class/hwmon'):
    """Recognized CPU Celsius sensors only; never substitute GPU/SSD or AMD Tctl."""
    readings = []
    for device in sorted(Path(root).glob('hwmon*')):
        driver = (device / 'name').read_text().strip()
        if driver not in ('coretemp', 'k10temp'):
            continue
        for path in sorted(device.glob('temp*_input')):
            stem = path.name[:-6]
            label = (device / (stem + '_label')).read_text().strip()
            accepted = (driver == 'coretemp' and re.fullmatch(r'(Core \d+|Package id \d+)', label)
                        or driver == 'k10temp' and (label == 'Tdie' or re.fullmatch(r'Tccd\d+', label)))
            if not accepted:
                continue
            temperature = int(path.read_text().strip()) / 1000.0
            alarm_path = device / (stem + '_crit_alarm')
            alarm = int(alarm_path.read_text().strip()) != 0 if alarm_path.exists() else False
            readings.append({'source': str(path.resolve()), 'label': label, 'driver': driver,
                             'celsius': temperature, 'critical_alarm': alarm})
    if not readings:
        raise OSError('no recognized CPU Celsius sensor; legacy CPUs may have no supported telemetry')
    return readings


class TemperatureGuard:
    """Latched software valve. Use as a context manager before guarded inference.

    Default: one read/second, strictly >100 C for >=10 s and >=3 readings from
    the same sensor, with no gap >2.5 s. A hardware critical alarm stops at once.
    Missing/invalid sensors and persistence errors also block guarded inference.
    """
    def __init__(self, checkpoint, *, reader=read_linux_cpu_temperatures,
                 threshold_c=100.0, hold_seconds=10.0, min_samples=3,
                 interval_seconds=1.0, max_gap_seconds=2.5,
                 max_result_bytes=1024 * 1024, clock=time.monotonic,
                 resume_after_inspection=False):
        for value in (threshold_c, hold_seconds, interval_seconds, max_gap_seconds):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError('temperature and timing settings must be finite and positive')
        if threshold_c > 100:
            raise ValueError('the requested 100 C ceiling cannot be raised')
        if (isinstance(min_samples, bool) or not isinstance(min_samples, int) or min_samples < 3
                or isinstance(max_result_bytes, bool) or not isinstance(max_result_bytes, int) or max_result_bytes <= 0):
            raise ValueError('need >=3 samples and a positive integer result byte limit')
        if max_gap_seconds < interval_seconds:
            raise ValueError('max gap must cover the polling interval')
        self.store, self.reader, self.clock = CheckpointStore(checkpoint), reader, clock
        self.threshold, self.hold, self.minimum = threshold_c, hold_seconds, min_samples
        self.interval, self.max_gap, self.max_result_bytes = interval_seconds, max_gap_seconds, max_result_bytes
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._state, self._reason, self._durability = 'NOT_STARTED', None, 'NOT_WRITTEN'
        self._last_time = None
        self._history, self._hot = deque(maxlen=16), {}
        self._last_result = None
        self._sequence = 0
        self._previous_temperature = None
        if self.store.path.exists():
            if not resume_after_inspection:
                raise FileExistsError('checkpoint exists; recover it and inspect hardware before explicit resume')
            recovered = self.store.load()  # never overwrite a corrupt checkpoint
            self._last_result = recovered['last_completed_result']
            self._sequence = recovered['sequence']
            history = recovered['temperature_history']
            self._previous_temperature = history[-1] if history else recovered.get('previous_session_last_temperature')

    def _report(self):
        return {'state': self._state, 'reason': self._reason, 'durability': self._durability,
                'checkpoint': str(self.store.path), 'last_temperature': self._history[-1] if self._history else None,
                'last_result_sequence': self._last_result['sequence'] if self._last_result else None}

    def _persist(self):
        self._sequence += 1
        payload = {'sequence': self._sequence, 'state': self._state, 'reason': self._reason,
                   'policy': {'threshold_c': self.threshold, 'hold_seconds': self.hold,
                              'min_samples': self.minimum, 'max_gap_seconds': self.max_gap},
                   'temperature_history': list(self._history), 'last_completed_result': self._last_result}
        payload['previous_session_last_temperature'] = self._previous_temperature
        try:
            self._durability = self.store.commit(payload)
        except (OSError, ValueError) as exc:
            self._state, self._reason, self._durability = 'CHECKPOINT_FAILED', str(exc), 'NOT_CONFIRMED'
            self._stop.set()
            raise ThermalSafetyError(self._report()) from exc

    def _fail(self, state, reason):
        self._state, self._reason = state, reason
        self._stop.set()
        self._persist()
        raise ThermalSafetyError(self._report())

    def poll(self):
        """One actual reader call. Public for deterministic tests and external loops."""
        with self._lock:
            if self._state not in ('NOT_STARTED', 'MONITORING', 'HOT_PENDING'):
                raise ThermalSafetyError(self._report())
            now = self.clock()
            try:
                samples = self.reader()
                if not math.isfinite(now) or self._last_time is not None and now < self._last_time:
                    raise ValueError('invalid or reversed monotonic clock')
                sources = set()
                for sample in samples:
                    value, source = sample['celsius'], sample['source']
                    if (isinstance(value, bool) or not isinstance(value, (int, float))
                            or not math.isfinite(value) or not -273.15 < value < 250
                            or not isinstance(source, str) or not source or source in sources
                            or not isinstance(sample.get('critical_alarm', False), bool)):
                        raise ValueError('invalid or duplicate CPU reading')
                    sources.add(source)
                if not sources:
                    raise ValueError('empty temperature sample')
                if self._history and sources != {s['source'] for s in self._history[-1]['sensors']}:
                    raise ValueError('CPU sensor set changed; continuity is unknown')
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self._fail('SENSOR_UNAVAILABLE', str(exc))
            record = {'monotonic_seconds': now, 'utc': datetime.now(timezone.utc).isoformat(),
                      'sensors': json.loads(_encoded(samples))}
            self._history.append(record)
            # Keep this last valid reading, but never treat an unobserved gap
            # as evidence of continuous overheating or continued health.
            if self._last_time is not None and now - self._last_time > self.max_gap:
                self._fail('SENSOR_STALE', 'sampling gap exceeded the configured bound')
            tripped = None
            for sample in samples:
                source = sample['source']
                if sample.get('critical_alarm', False):
                    tripped = 'hardware critical alarm: ' + source
                if sample['celsius'] > self.threshold:
                    first, count, previous = self._hot.get(source, (now, 0, None))
                    count += int(previous is None or now > previous)
                    self._hot[source] = (first, count, now)
                    if now - first >= self.hold and count >= self.minimum:
                        tripped = 'sustained temperature above threshold: ' + source
                else:
                    self._hot.pop(source, None)
            self._last_time = now
            self._state = 'HOT_PENDING' if self._hot else 'MONITORING'
            if tripped:
                self._state, self._reason = 'THERMAL_TRIP', tripped
                self._stop.set()
            self._persist()
            if tripped:
                raise ThermalSafetyError(self._report())
            return self._report()

    def check(self):
        with self._lock:
            if self._state not in ('MONITORING', 'HOT_PENDING'):
                raise ThermalSafetyError(self._report())
            age = self.clock() - self._last_time
            if age < 0 or age > self.max_gap or not math.isfinite(age):
                self._fail('SENSOR_STALE', 'no fresh temperature sample')

    def check_result_size(self, size):
        if size > self.max_result_bytes:
            raise ValueError('result exceeds configured durable checkpoint limit')

    def save_result(self, data, *, shape, dtype):
        """Save a completed result, never a partial chunk or a post-trip result."""
        self.check_result_size(len(data))
        owned = bytes(data)
        with self._lock:
            self.check()
            self._last_result = {'sequence': self._sequence + 1, 'shape': list(shape), 'dtype': dtype,
                                 'encoding': 'base64', 'data': base64.b64encode(owned).decode('ascii'),
                                 'sha256': hashlib.sha256(owned).hexdigest(), 'bytes': len(owned)}
            self._persist()

    def _monitor(self):
        while not self._stop.wait(self.interval):
            try:
                self.poll()
            except ThermalSafetyError:
                return

    def __enter__(self):
        if self._thread is not None or self._state != 'NOT_STARTED':
            raise RuntimeError('a guard is single-use; create a new guard after inspection')
        self.poll()
        self._thread = threading.Thread(target=self._monitor, name='pyignite-temperature', daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.max_gap)
        with self._lock:
            if self._state in ('MONITORING', 'HOT_PENDING'):
                self._state = 'CLOSED'
        return False
