"""Emit a deterministic CPU demonstration, with no hardware or network calls."""
from dataclasses import asdict
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from motionbricks.crew_countdown import CrewCountdown, CrewVote, Snapshot


def run():
    c = CrewCountdown(('commander', 'pilot'), duration_s=2, max_gap_s=1,
                      max_age_s=0.5, window_end_s=20)
    trace = []
    for seq, (t, command, pilot) in enumerate([
        (0, 'resume', 'GO'), (1, 'tick', 'GO'), (2, 'tick', 'HOLD'),
        (3, 'tick', 'GO'), (4, 'resume', 'GO'), (5, 'tick', 'GO'),
        (6, 'tick', 'GO'), (7, 'confirm', 'GO'), (8, 'confirm', 'GO'),
        (9, 'abort', 'GO'),
    ]):
        s = Snapshot(seq, t, True, True, (
            CrewVote('commander', 'GO', c.epoch, t),
            CrewVote('pilot', pilot, c.epoch, t)))
        d = c.step(t, s, command=command, crew_actor='commander')
        trace.append({'time_s': t, 'command': command, 'snapshot': asdict(s),
                      'decision': asdict(d), 'progress': asdict(c.progress())})
    return {'evidence': 'CPU_SIMULATION_ONLY', 'launch_commands_sent': 0,
            'trace': trace}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2, allow_nan=False))
