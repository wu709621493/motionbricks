import unittest
from dataclasses import replace
from motionbricks.sleep_mode import (
    BalanceSample, Mode, SleepConfig, SleepRuntime, SleepSupervisor,
)


class SleepTests(unittest.TestCase):
    def setUp(self):
        self.s = SleepSupervisor(SleepConfig(settle_s=0.1))
        self.t = -0.01

    def tick(self, **changes):
        self.t += 0.01
        sample = BalanceSample(self.t, 0.0, 0.0, 0.1, True, True)
        requests = {k: changes.pop(k) for k in list(changes)
                    if k in ('wake', 'reset_fault', 'recovery_complete', 'sleep_requested')}
        requests.setdefault('sleep_requested', True)
        return self.s.tick(replace(sample, **changes), self.t, **requests)

    def sleep(self):
        for _ in range(13):
            self.tick()
        self.assertEqual(self.s.mode, Mode.SLEEP)

    def test_dwell_and_wake(self):
        self.assertEqual(self.tick().mode, Mode.SETTLING)
        self.sleep()
        self.assertEqual(self.tick(wake=True).mode, Mode.ACTIVE)
        self.assertEqual(self.tick().mode, Mode.SETTLING)

    def test_dwell_resets_after_motion(self):
        for _ in range(8): self.tick()
        self.tick(speed_m_s=0.02)
        for _ in range(8): self.assertNotEqual(self.tick().mode, Mode.SLEEP)

    def test_hysteresis(self):
        self.sleep()
        self.assertEqual(self.tick(tilt_rad=0.05).mode, Mode.SLEEP)
        self.assertEqual(self.tick(tilt_rad=0.08).mode, Mode.RECOVERY)
        self.assertEqual(self.tick(wake=True).mode, Mode.RECOVERY)
        self.assertEqual(self.tick(recovery_complete=True).mode, Mode.ACTIVE)
        self.assertEqual(self.tick().mode, Mode.SETTLING)

    def test_support_loss_and_margin(self):
        for changes in ({'support_confirmed': False}, {'support_margin_m': 0.02},
                        {'speed_m_s': 0.05}):
            with self.subTest(changes=changes):
                self.setUp(); self.sleep()
                self.assertEqual(self.tick(**changes).mode, Mode.RECOVERY)

    def test_bad_telemetry_latches(self):
        for changes in ({'tilt_rad': float('nan')}, {'speed_m_s': -1},
                        {'support_margin_m': float('inf')}, {'timestamp_s': -1},
                        {'timestamp_s': 20}, {'controller_ready': False},
                        {'support_confirmed': 'yes'}):
            with self.subTest(changes=changes):
                self.setUp()
                self.assertEqual(self.tick(**changes).mode, Mode.FAULT)
                self.assertEqual(self.tick(wake=True).mode, Mode.FAULT)
                self.assertEqual(self.tick(reset_fault=True).mode, Mode.RECOVERY)

    def test_deadline_and_backward_clock(self):
        self.tick(); self.t += 0.1
        self.assertEqual(self.tick().mode, Mode.FAULT)
        sample = BalanceSample(0, 0, 0, 0.1, True, True)
        self.assertEqual(self.s.tick(sample, 0, reset_fault=True).mode, Mode.FAULT)

    def test_callback_budget_and_balance_retained(self):
        calls = {'balance': 0, 'generation': 0}
        def balance(*args):
            calls['balance'] += 1
            return True
        def generation(): calls['generation'] += 1
        runtime = SleepRuntime(self.s, balance_step=balance,
                               generate_step=generation, on_fault=lambda: None)
        for i in range(100):
            t = i / 100
            runtime.step(BalanceSample(t, 0, 0, 0.1, True, True), t,
                         sleep_requested=True)
        self.assertEqual(calls['balance'], 100)
        self.assertEqual(calls['generation'], 10)

    def test_callback_failure_latches(self):
        for failure in ('balance', 'generation'):
            with self.subTest(failure=failure):
                self.setUp(); faults = []; generations = []
                def generation():
                    generations.append(1)
                    raise RuntimeError('generator failure')
                runtime = SleepRuntime(self.s,
                    balance_step=lambda *args: failure != 'balance',
                    generate_step=generation, on_fault=lambda: faults.append(1))
                with self.assertRaises(RuntimeError):
                    runtime.step(BalanceSample(0, 0, 0, 0.1, True, True), 0)
                self.assertEqual(self.s.mode, Mode.FAULT)
                self.assertEqual(faults, [1])
                self.assertEqual(len(generations), int(failure == 'generation'))

    def test_configuration_rejected(self):
        for changes in ({'settle_s': 0}, {'max_tick_gap_s': float('nan')},
                        {'enter_tilt_rad': 0.1}, {'enter_margin_m': 0.01}):
            with self.assertRaises(ValueError): SleepConfig(**changes)


if __name__ == '__main__': unittest.main()
