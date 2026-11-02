from dataclasses import replace
import unittest
from motionbricks.crew_countdown import CrewCountdown, CrewVote, Snapshot, Phase


class CountdownTests(unittest.TestCase):
    def setUp(self):
        self.c = CrewCountdown(('commander', 'pilot'), duration_s=1, max_gap_s=1,
                               max_age_s=0.5, window_end_s=10)
        self.seq = 0

    def snap(self, t, **changes):
        self.seq += 1
        return replace(Snapshot(self.seq, t, True, True, tuple(
            CrewVote(c, 'GO', self.c.epoch, t) for c in ('commander', 'pilot'))), **changes)

    def ready(self):
        self.c.step(0, self.snap(0), command='resume', crew_actor='commander')
        return self.c.step(1, self.snap(1))

    def test_zero_never_triggers_review(self):
        d = self.ready()
        self.assertEqual(d.phase, Phase.AWAITING_CONFIRMATION)
        self.assertFalse(d.request_review)
        self.assertEqual(self.c.progress().value, 1)
        self.assertFalse(self.c.step(1.1, self.snap(1.1)).request_review)
        self.assertTrue(self.c.step(1.2, self.snap(1.2), command='confirm', crew_actor='commander').request_review)
        self.assertFalse(self.c.step(1.3, self.snap(1.3), command='confirm', crew_actor='commander').request_review)

    def test_confirmation_at_boundary_is_not_enough(self):
        self.c.step(0, self.snap(0), command='resume', crew_actor='commander')
        self.assertFalse(self.c.step(1, self.snap(1), command='confirm', crew_actor='commander').request_review)

    def test_hold_freezes_and_invalidates_votes(self):
        self.c.step(0, self.snap(0), command='resume', crew_actor='commander')
        old = self.snap(0.1)
        self.c.step(None, command='hold')
        self.assertEqual(self.c.remaining_s, 1)
        self.assertEqual(self.c.epoch, 1)
        self.assertEqual(self.c.step(0.1, old, command='resume', crew_actor='commander').phase, Phase.HOLD)
        self.assertEqual(self.c.step(0.2, self.snap(0.2)).phase, Phase.HOLD)
        self.assertEqual(self.c.step(0.3, self.snap(0.3), command='resume', crew_actor='commander').phase, Phase.COUNTING)
        self.assertEqual(self.c.remaining_s, 1)

    def test_any_crew_can_hold_or_abort(self):
        for who in ('commander', 'pilot'):
            for vote in ('HOLD', 'ABORT'):
                self.setUp(); self.ready()
                s = self.snap(1.1)
                s = replace(s, votes=tuple(replace(v, decision=vote) if v.crew_id == who else v for v in s.votes))
                d = self.c.step(1.1, s, command='confirm', crew_actor='commander')
                self.assertFalse(d.request_review)
                self.assertEqual(d.phase, Phase.ABORTED if vote == 'ABORT' else Phase.HOLD)

    def test_no_ground_override_or_silence_consent(self):
        for changes in ({'votes': ()}, {'ground_go': False}, {'vehicle_go': False}, {'ground_go': 1}):
            self.setUp(); self.ready()
            self.assertEqual(self.c.step(1.1, self.snap(1.1, **changes), command='confirm', crew_actor='commander').phase, Phase.HOLD)

    def test_stale_future_replay_and_duplicate_votes(self):
        for kind in ('stale', 'future', 'replay', 'duplicate', 'old_epoch', 'unknown'):
            self.setUp(); self.ready(); s = self.snap(1.1)
            if kind == 'stale': s = replace(s, timestamp_s=0)
            if kind == 'future': s = replace(s, timestamp_s=2)
            if kind == 'replay': s = replace(s, sequence=1)
            if kind == 'duplicate': s = replace(s, votes=(s.votes[0], s.votes[0]))
            if kind == 'old_epoch': s = replace(s, votes=tuple(replace(v, epoch=-1) for v in s.votes))
            if kind == 'unknown': s = replace(s, votes=(s.votes[0], replace(s.votes[1], crew_id='outsider')))
            self.assertEqual(self.c.step(1.1, s, command='confirm', crew_actor='commander').phase, Phase.HOLD)

    def test_clock_faults_do_not_skip_to_zero(self):
        for t in (0, -1, 2, float('nan'), float('inf')):
            self.setUp(); self.c.step(0, self.snap(0), command='resume', crew_actor='commander')
            self.assertEqual(self.c.step(t, self.snap(0)).phase, Phase.HOLD)
            self.assertEqual(self.c.remaining_s, 1)

    def test_abort_without_telemetry_and_latched(self):
        self.ready()
        self.assertEqual(self.c.step(None, command='abort').phase, Phase.ABORTED)
        self.assertEqual(self.c.step(1.1, self.snap(1.1), command='resume', crew_actor='commander').phase, Phase.ABORTED)

    def test_window_expiration(self):
        self.ready()
        self.assertEqual(self.c.step(10, self.snap(10), command='confirm', crew_actor='commander').phase, Phase.ABORTED)

    def test_ground_cannot_confirm_as_crew(self):
        self.ready()
        d = self.c.step(1.1, self.snap(1.1), command='confirm', crew_actor='ground')
        self.assertEqual(d.phase, Phase.HOLD)
        self.assertFalse(d.request_review)

    def test_preboundary_go_cannot_confirm(self):
        self.ready()
        s = self.snap(1.1)
        s = replace(s, votes=tuple(replace(v, timestamp_s=1) for v in s.votes))
        self.assertFalse(self.c.step(1.1, s, command='confirm', crew_actor='pilot').request_review)
        self.assertTrue(self.c.step(1.2, self.snap(1.2), command='confirm', crew_actor='pilot').request_review)

    def test_bad_configuration(self):
        for v in (0, -1, True, float('nan'), float('inf')):
            with self.assertRaises(ValueError): CrewCountdown(('pilot',), duration_s=v)
        for ids in ((), ('pilot', 'pilot'), ('',)):
            with self.assertRaises(ValueError): CrewCountdown(ids)

    def test_hold_withdraws_review_locally(self):
        self.ready(); self.c.step(1.1, self.snap(1.1), command='confirm', crew_actor='commander')
        d = self.c.step(None, command='hold')
        self.assertEqual(d.phase, Phase.HOLD)
        self.assertFalse(d.request_review)


if __name__ == '__main__': unittest.main()
