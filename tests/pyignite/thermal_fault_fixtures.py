"""Trusted providers imported in disposable test children, not parent callbacks."""
import os
import threading
from unittest.mock import patch
from thermal import CheckpointStore


def healthy(celsius=70., critical_alarm=False):
    return [{'source': 'simulated-cpu', 'celsius': celsius, 'critical_alarm': critical_alarm}]


def hang():
    threading.Event().wait()


def invalid():
    return []


class FsyncHangStore(CheckpointStore):
    def commit(self, payload):
        with patch('thermal.os.fsync', side_effect=lambda fd: threading.Event().wait()):
            return super().commit(payload)


class FsyncErrorStore(CheckpointStore):
    def commit(self, payload):
        with patch('thermal.os.fsync', side_effect=OSError('injected fsync error')):
            return super().commit(payload)


class ReplaceInterruptedStore(CheckpointStore):
    def commit(self, payload):
        with patch('thermal.os.replace', side_effect=lambda *args: os._exit(73)):
            return super().commit(payload)


class ExistsHangStore(CheckpointStore):
    def exists(self):
        threading.Event().wait()


class DirectoryFsyncErrorStore(CheckpointStore):
    def commit(self, payload):
        original = os.fsync
        count = [0]
        def fail_directory(fd):
            count[0] += 1
            if count[0] == 2:
                raise OSError('injected directory fsync failure after replace')
            return original(fd)
        with patch('thermal.os.fsync', side_effect=fail_directory):
            return super().commit(payload)
