"""Regression cases for paused time and explicit human command boundaries."""
from dataclasses import replace
import unittest
from motionbricks.crew_countdown import CrewCountdown, CrewVote, Snapshot, Phase


class HoldRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.c = CrewCountdown(('pilot', 'commander'), duration_s=1,
                               max_gap_s=1, max_age_s=.5, window_end_s=10)
        self.seq = 0

    def snap(self, t, **changes):
        self.seq += 1
        return replace(Snapshot(self.seq, t, True, True, tuple(
            CrewVote(c, 'GO', self.c.epoch, t) for c in ('pilot', 'commander'))), **changes)

    def resume(self, t):
        return self.c.step(t, self.snap(t), command='resume', crew_actor='pilot')

    def pause(self):
        self.resume(0)
        self.c.step(.1, command='hold')

    def test_long_hold_resumes_without_consuming_paused_time(self):
        self.pause()
        d = self.resume(2)
        self.assertEqual(d.phase, Phase.COUNTING)
        self.assertEqual(d.remaining_s, 1)
        self.assertAlmostEqual(self.c.step(2.25, self.snap(2.25)).remaining_s, .75)

    def test_counting_gap_still_holds_and_requires_fresh_manual_resume(self):
        self.resume(0)
        d = self.c.step(2, self.snap(2))
        self.assertEqual(d.reason, 'missed monitoring deadline')
        self.assertEqual(d.remaining_s, 1)
        self.assertEqual(d.epoch, 1)
        self.assertEqual(self.c.step(4, self.snap(4)).phase, Phase.HOLD)
        self.assertEqual(self.resume(6).phase, Phase.COUNTING)

    def test_held_ticks_do_not_automatically_resume(self):
        self.pause()
        for t in (2, 4, 6):
            d = self.c.step(t, self.snap(t))
            self.assertEqual(d.phase, Phase.HOLD)
            self.assertEqual(d.remaining_s, 1)
        self.assertEqual(self.resume(8).phase, Phase.COUNTING)

    def test_window_expires_during_hold(self):
        for command in ('resume', 'tick', 'hold', 'confirm'):
            with self.subTest(command=command):
                self.setUp(); self.pause()
                d = self.c.step(10, self.snap(10), command=command, crew_actor='pilot')
                self.assertEqual(d.phase, Phase.ABORTED)
                self.assertEqual(self.resume(11).phase, Phase.ABORTED)

    def test_hold_preserves_clock_high_water_mark(self):
        for t in (0, .05, .1, float('nan'), float('inf'), -1):
            with self.subTest(t=t):
                self.setUp(); self.pause()
                self.assertEqual(self.resume(t).phase, Phase.HOLD)
                self.assertEqual(self.resume(2).phase, Phase.COUNTING)

    def test_clockless_hold_remains_available(self):
        self.resume(1)
        self.assertEqual(self.c.step(None, command='hold').phase, Phase.HOLD)
        self.assertEqual(self.resume(.5).phase, Phase.HOLD)
        self.assertEqual(self.resume(3).phase, Phase.COUNTING)

    def test_old_epoch_and_expired_votes_cannot_resume(self):
        for kind in ('epoch', 'expired', 'replay', 'future'):
            with self.subTest(kind=kind):
                self.setUp(); self.pause()
                s = self.snap(2)
                if kind == 'epoch': s = replace(s, votes=tuple(replace(v, epoch=0) for v in s.votes))
                if kind == 'expired': s = replace(s, votes=tuple(replace(v, timestamp_s=.1) for v in s.votes))
                if kind == 'replay': s = replace(s, sequence=1)
                if kind == 'future': s = replace(s, timestamp_s=3)
                self.assertEqual(self.c.step(2, s, command='resume', crew_actor='pilot').phase, Phase.HOLD)
                self.assertEqual(self.resume(4).phase, Phase.COUNTING)

    def test_veto_and_interlocks_after_long_hold(self):
        for kind in ('HOLD', 'ABORT', 'ground', 'vehicle'):
            with self.subTest(kind=kind):
                self.setUp(); self.pause(); s = self.snap(2)
                if kind in ('HOLD', 'ABORT'):
                    s = replace(s, votes=(replace(s.votes[0], decision=kind), s.votes[1]))
                else: s = replace(s, **{kind + '_go': False})
                d = self.c.step(2, s, command='resume', crew_actor='commander')
                self.assertEqual(d.phase, Phase.ABORTED if kind == 'ABORT' else Phase.HOLD)
                self.assertFalse(d.request_review)

    def test_repeated_resume_is_rejected_without_advancing_countdown(self):
        self.resume(0)
        d = self.resume(.25)
        self.assertEqual(d.phase, Phase.HOLD)
        self.assertEqual(d.remaining_s, 1)
        self.assertFalse(d.request_review)
        self.assertEqual(self.resume(2).phase, Phase.COUNTING)

    def test_restoring_review_requires_resume_then_new_manual_confirmation(self):
        self.resume(0)
        self.c.step(1, self.snap(1))
        self.assertTrue(self.c.step(1.1, self.snap(1.1), command='confirm', crew_actor='pilot').request_review)
        self.c.step(1.2, command='hold')
        self.assertFalse(self.c.step(3, self.snap(3), command='confirm', crew_actor='pilot').request_review)
        d = self.resume(5)
        self.assertEqual(d.phase, Phase.AWAITING_CONFIRMATION)
        self.assertFalse(d.request_review)
        s = self.snap(5.1)
        s = replace(s, votes=tuple(replace(v, timestamp_s=5) for v in s.votes))
        self.assertFalse(self.c.step(5.1, s, command='confirm', crew_actor='pilot').request_review)
        self.assertFalse(self.c.step(5.2, self.snap(5.2)).request_review)
        self.assertTrue(self.c.step(5.3, self.snap(5.3), command='confirm', crew_actor='pilot').request_review)
        self.assertFalse(self.c.step(5.4, self.snap(5.4), command='confirm', crew_actor='pilot').request_review)

    def test_missing_or_noncrew_actor_cannot_resume(self):
        for actor in (None, 'ground'):
            self.setUp(); self.pause()
            self.assertEqual(self.c.step(2, self.snap(2), command='resume', crew_actor=actor).phase, Phase.HOLD)

    def test_confirmation_monitoring_gap_still_withdraws(self):
        self.resume(0); self.c.step(1, self.snap(1))
        d = self.c.step(3, self.snap(3), command='confirm', crew_actor='pilot')
        self.assertEqual(d.reason, 'missed monitoring deadline')
        self.assertFalse(d.request_review)

    def test_repeat_resume_at_zero_never_restores_review(self):
        for reviewed in (False, True):
            with self.subTest(reviewed=reviewed):
                self.setUp(); self.resume(0); self.c.step(1, self.snap(1))
                if reviewed:
                    self.c.step(1.1, self.snap(1.1), command='confirm', crew_actor='pilot')
                d = self.resume(1.2)
                self.assertEqual(d.phase, Phase.HOLD)
                self.assertEqual(d.epoch, 1)
                self.assertFalse(d.request_review)

    def test_review_monitoring_uses_latest_tick_without_duplicate_events(self):
        self.resume(0); self.c.step(1, self.snap(1))
        self.c.step(1.1, self.snap(1.1), command='confirm', crew_actor='pilot')
        for t in (2, 2.9, 3.8):
            d = self.c.step(t, self.snap(t))
            self.assertEqual(d.phase, Phase.REVIEW_REQUESTED)
            self.assertFalse(d.request_review)
        self.assertEqual(self.c.step(5, self.snap(5)).reason, 'missed monitoring deadline')
