"""One-shot sleep admission, cancellation and retained balance regression tests."""
from dataclasses import replace
import unittest

from motionbricks.sleep_mode import (
    BalanceSample, Mode, SleepConfig, SleepRuntime, SleepSupervisor,
)


class OyasumiTests(unittest.TestCase):
    def setUp(self):
        self.supervisor = SleepSupervisor(SleepConfig(settle_s=0.1))
        self.index = 0

    def tick(self, *, sample_changes=None, **requests):
        now = self.index / 100
        self.index += 1
        sample = BalanceSample(now, 0.0, 0.0, 0.1, True, True)
        return self.supervisor.tick(
            replace(sample, **(sample_changes or {})), now, **requests)

    def enter_sleep(self):
        self.assertEqual(self.tick(oyasumi=True).mode, Mode.SETTLING)
        for _ in range(12):
            decision = self.tick()
        self.assertEqual(decision.mode, Mode.SLEEP)

    def assert_stays_awake(self):
        # Longer than a full dwell: detect a forgotten pending request.
        for _ in range(15):
            self.assertEqual(self.tick().mode, Mode.ACTIVE)

    def test_one_shot_runtime_retains_balance_and_valid_zeros(self):
        self.check_one_shot_runtime({"oyasumi": True})

    def test_text_commands_follow_the_same_runtime_trace(self):
        for command in ("训觉", "訓覺", "瞓觉", "瞓覺", "oyasumi", "おやすみ"):
            with self.subTest(command=command):
                self.check_one_shot_runtime({"sleep_command": command})

    def check_one_shot_runtime(self, first_request):
        calls = {"balance": 0, "generation": 0}

        def balance(sample, decision):
            self.assertTrue(decision.balance_required)
            calls["balance"] += 1
            return True

        def generate():
            calls["generation"] += 1

        runtime = SleepRuntime(SleepSupervisor(SleepConfig(settle_s=0.1)),
                               balance_step=balance,
                               generate_step=generate,
                               on_fault=lambda: self.fail("Unexpected fault"))
        for i in range(100):
            now = i / 100
            request = first_request if i == 0 else {}
            decision = runtime.step(BalanceSample(now, 0, 0, 0.1, True, True),
                                    now, **request)
            self.assertEqual(decision.mode, Mode.SETTLING if i < 10 else Mode.SLEEP)
        self.assertEqual(calls, {"balance": 100, "generation": 10})

    def test_text_and_boolean_requests_share_dwell_and_wake(self):
        self.assertEqual(self.tick(sleep_command="训觉",
            sample_changes={"speed_m_s": 0.02}).mode, Mode.ACTIVE)
        for _ in range(10):
            self.assertEqual(self.tick(sleep_command=None).mode, Mode.SETTLING)
        self.assertEqual(self.tick(oyasumi=True, sleep_command="训觉").mode, Mode.SLEEP)
        self.assertEqual(self.tick(wake=True, sleep_command="训觉").mode, Mode.ACTIVE)
        self.assert_stays_awake()

    def test_text_request_is_discarded_during_fault_and_recovery(self):
        self.tick(sleep_command="训觉")
        self.assertEqual(self.tick(sleep_command="训觉",
            sample_changes={"controller_ready": False}).mode, Mode.FAULT)
        self.assertEqual(self.tick(sleep_command="训觉", reset_fault=True).mode, Mode.RECOVERY)
        self.assertEqual(self.tick(sleep_command="训觉", recovery_complete=True).mode, Mode.ACTIVE)
        self.assert_stays_awake()

    def test_invalid_text_faults_even_with_valid_boolean_request(self):
        for invalid in ("", "唔好训觉", "训觉！", " 训觉", True, ["训觉"]):
            with self.subTest(invalid=invalid):
                self.tick(sleep_command="训觉")
                decision = self.tick(oyasumi=True, sleep_command=invalid)
                self.assertEqual((decision.mode, decision.reason),
                                 (Mode.FAULT, "invalid sleep command"))
                self.tick(reset_fault=True)
                self.tick(recovery_complete=True)
                self.assert_stays_awake()

    def test_request_waits_for_entry_and_restarts_interrupted_dwell(self):
        self.assertEqual(self.tick(oyasumi=True,
            sample_changes={"speed_m_s": 0.02}).mode, Mode.ACTIVE)
        for _ in range(8):
            self.assertEqual(self.tick().mode, Mode.SETTLING)
        self.assertEqual(self.tick(
            sample_changes={"speed_m_s": 0.02}).mode, Mode.ACTIVE)
        for _ in range(10):
            self.assertEqual(self.tick().mode, Mode.SETTLING)
        for _ in range(3):
            decision = self.tick()
        self.assertEqual(decision.mode, Mode.SLEEP)

    def test_repeated_request_does_not_restart_dwell(self):
        for _ in range(13):
            decision = self.tick(oyasumi=True)
        self.assertEqual(decision.mode, Mode.SLEEP)

    def test_wake_cancels_in_each_phase_and_wins_over_new_request(self):
        for phase in ("waiting", "settling", "sleep"):
            for simultaneous in (False, True):
                with self.subTest(phase=phase, simultaneous=simultaneous):
                    self.setUp()
                    if phase == "sleep":
                        self.enter_sleep()
                    else:
                        changes = {"speed_m_s": 0.02} if phase == "waiting" else {}
                        self.tick(oyasumi=True, sample_changes=changes)
                    self.assertEqual(self.tick(wake=True, oyasumi=simultaneous).mode,
                                     Mode.ACTIVE)
                    self.assert_stays_awake()
                    self.enter_sleep()  # A fresh command still works.

    def test_disturbance_cancels_request_and_preserves_recovery_gate(self):
        disturbances = ({"tilt_rad": 0.08}, {"speed_m_s": 0.05},
                        {"support_margin_m": 0.02}, {"support_confirmed": False})
        for changes in disturbances:
            with self.subTest(changes=changes):
                self.setUp()
                self.enter_sleep()
                decision = self.tick(sample_changes=changes, oyasumi=True,
                                     wake=True, recovery_complete=True)
                self.assertEqual(decision.mode, Mode.RECOVERY)
                self.assertFalse(decision.generate_motion)
                self.assertEqual(self.tick(oyasumi=True).mode, Mode.RECOVERY)
                self.assertEqual(self.tick(oyasumi=True, recovery_complete=True).mode,
                                 Mode.ACTIVE)
                self.assert_stays_awake()
                self.enter_sleep()

    def test_request_on_unsafe_tick_is_not_queued(self):
        self.assertEqual(self.tick(oyasumi=True,
            sample_changes={"support_confirmed": False}).mode, Mode.RECOVERY)
        self.assertEqual(self.tick(recovery_complete=True).mode, Mode.ACTIVE)
        self.assert_stays_awake()

    def test_fault_cancels_and_reset_cannot_queue_sleep(self):
        invalid = ({"timestamp_s": -1}, {"timestamp_s": 100},
                   {"tilt_rad": float("nan")}, {"speed_m_s": -1},
                   {"support_margin_m": float("inf")}, {"controller_ready": False})
        for changes in invalid:
            with self.subTest(changes=changes):
                self.setUp()
                self.enter_sleep()
                self.assertEqual(self.tick(sample_changes=changes,
                    oyasumi=True, wake=True, reset_fault=True).mode, Mode.FAULT)
                self.assertEqual(self.tick(oyasumi=True, wake=True).mode, Mode.FAULT)
                self.assertEqual(self.tick(oyasumi=True, reset_fault=True).mode,
                                 Mode.RECOVERY)
                self.assertEqual(self.tick(oyasumi=True, recovery_complete=True).mode,
                                 Mode.ACTIVE)
                self.assert_stays_awake()

    def test_missed_deadline_discards_request(self):
        self.enter_sleep()
        self.index += 10
        self.assertEqual(self.tick(oyasumi=True).mode, Mode.FAULT)
        self.assertEqual(self.tick(reset_fault=True).mode, Mode.RECOVERY)
        self.assertEqual(self.tick(recovery_complete=True).mode, Mode.ACTIVE)
        self.assert_stays_awake()

    def test_callback_failure_discards_pending_or_sleeping_request(self):
        for failure in ("generation", "balance"):
            with self.subTest(failure=failure):
                self.setUp()
                if failure == "balance":
                    self.enter_sleep()
                faults = []

                def generate():
                    raise RuntimeError("generator failure")

                runtime = SleepRuntime(self.supervisor,
                    balance_step=lambda *args: failure != "balance",
                    generate_step=generate, on_fault=lambda: faults.append(True))
                now = self.index / 100
                self.index += 1
                with self.assertRaises(RuntimeError):
                    runtime.step(BalanceSample(now, 0, 0, 0.1, True, True),
                                 now, oyasumi=True)
                self.assertEqual(faults, [True])
                self.assertEqual(self.supervisor.mode, Mode.FAULT)
                self.tick(reset_fault=True)
                self.tick(recovery_complete=True)
                self.assert_stays_awake()

    def test_legacy_level_request_still_requires_maintenance(self):
        self.assertEqual(self.tick(sleep_requested=True).mode, Mode.SETTLING)
        self.assert_stays_awake()
        for _ in range(13):
            decision = self.tick(sleep_requested=True)
        self.assertEqual(decision.mode, Mode.SLEEP)
        self.assert_stays_awake()

    def test_wake_does_not_disable_caller_owned_level_request(self):
        self.enter_sleep()
        self.assertEqual(self.tick(wake=True, sleep_requested=True).mode, Mode.ACTIVE)
        self.assertEqual(self.tick(sleep_requested=True).mode, Mode.SETTLING)
        self.assert_stays_awake()

    def test_request_is_per_supervisor(self):
        self.enter_sleep()
        other = SleepSupervisor(SleepConfig(settle_s=0.1))
        for i in range(15):
            now = i / 100
            self.assertEqual(other.tick(
                BalanceSample(now, 0, 0, 0.1, True, True), now).mode, Mode.ACTIVE)

    def test_invalid_command_faults_and_clears_pending_request(self):
        for invalid in ("yes", "训觉", 1, None):
            with self.subTest(invalid=invalid):
                self.setUp()
                self.tick(oyasumi=True)
                self.assertEqual(self.tick(oyasumi=invalid).mode, Mode.FAULT)
                self.tick(reset_fault=True)
                self.tick(recovery_complete=True)
                self.assert_stays_awake()


if __name__ == "__main__":
    unittest.main()
