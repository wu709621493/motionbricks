"""Opt-in CPU sleep supervisor. Requires an independent balance controller.

No actuator commands, physics guarantees, OS suspend, or backend assumptions.
All timestamps use the same monotonic clock, in seconds.
"""
from dataclasses import dataclass
from enum import Enum
import math
from typing import Callable


class Mode(str, Enum):
    ACTIVE = "active"
    SETTLING = "settling"
    SLEEP = "sleep"
    RECOVERY = "recovery"
    FAULT = "fault"


@dataclass(frozen=True)
class SleepConfig:
    settle_s: float = 2.0
    max_sample_age_s: float = 0.05
    max_tick_gap_s: float = 0.05
    enter_tilt_rad: float = 0.03
    exit_tilt_rad: float = 0.08
    enter_speed_m_s: float = 0.01
    exit_speed_m_s: float = 0.05
    enter_margin_m: float = 0.04
    exit_margin_m: float = 0.02

    def __post_init__(self):
        if any(not math.isfinite(v) or v <= 0 for v in vars(self).values()):
            raise ValueError("Configuration values must be finite and positive")
        if not (self.enter_tilt_rad < self.exit_tilt_rad
                and self.enter_speed_m_s < self.exit_speed_m_s
                and self.enter_margin_m > self.exit_margin_m):
            raise ValueError("Entry thresholds must be stricter than exit thresholds")


@dataclass(frozen=True)
class BalanceSample:
    timestamp_s: float
    tilt_rad: float  # magnitude, not signed roll/pitch
    speed_m_s: float  # magnitude
    support_margin_m: float  # signed distance to support boundary
    support_confirmed: bool
    controller_ready: bool


@dataclass(frozen=True)
class Decision:
    mode: Mode
    reason: str
    generate_motion: bool
    balance_required: bool = True


class SleepSupervisor:
    """Single-owner state machine; call at every balance tick, including sleep.

    A fault latches until reset_fault=True with healthy telemetry. Recovery
    requires recovery_complete=True from the independent controller. Neither
    flag bypasses telemetry checks. Sleep requests must be maintained by caller.
    """

    def __init__(self, config: SleepConfig = SleepConfig()):
        self.config = config
        self.mode = Mode.ACTIVE
        self._last_tick = None
        self._stable_since = None

    def _decision(self, mode, reason):
        self.mode = mode
        if mode != Mode.SETTLING:
            self._stable_since = None
        return Decision(mode, reason, mode in (Mode.ACTIVE, Mode.SETTLING))

    def tick(self, sample: BalanceSample, now_s: float, *,
             sleep_requested: bool = False, wake: bool = False,
             recovery_complete: bool = False, reset_fault: bool = False) -> Decision:
        c = self.config
        numeric = (now_s, sample.timestamp_s, sample.tilt_rad,
                   sample.speed_m_s, sample.support_margin_m)
        valid = (all(math.isfinite(v) for v in numeric)
                 and sample.tilt_rad >= 0 and sample.speed_m_s >= 0
                 and type(sample.support_confirmed) is bool
                 and sample.controller_ready is True
                 and 0 <= now_s - sample.timestamp_s <= c.max_sample_age_s)
        timing_ok = (math.isfinite(now_s) and (self._last_tick is None
                     or 0 < now_s - self._last_tick <= c.max_tick_gap_s))
        # Preserve clock high-water mark on invalid/backward timestamps.
        if math.isfinite(now_s) and (self._last_tick is None or now_s > self._last_tick):
            self._last_tick = now_s
        if not valid or not timing_ok:
            return self._decision(Mode.FAULT, "invalid telemetry or missed deadline")
        if self.mode == Mode.FAULT:
            if not reset_fault:
                return self._decision(Mode.FAULT, "fault latched")
            return self._decision(Mode.RECOVERY, "fault reset; recovery required")
        safe = (sample.support_confirmed and sample.tilt_rad < c.exit_tilt_rad
                and sample.speed_m_s < c.exit_speed_m_s
                and sample.support_margin_m > c.exit_margin_m)
        if not safe:
            return self._decision(Mode.RECOVERY, "balance envelope exceeded")
        if self.mode == Mode.RECOVERY:
            if not recovery_complete:
                return self._decision(Mode.RECOVERY, "awaiting balance recovery")
            return self._decision(Mode.ACTIVE, "recovery acknowledged")
        if wake or not sleep_requested:
            return self._decision(Mode.ACTIVE, "wake or sleep request cleared")
        if self.mode == Mode.SLEEP:
            return self._decision(Mode.SLEEP, "stable hold")
        entry = (sample.tilt_rad <= c.enter_tilt_rad
                 and sample.speed_m_s <= c.enter_speed_m_s
                 and sample.support_margin_m >= c.enter_margin_m)
        if not entry:
            return self._decision(Mode.ACTIVE, "not ready to settle")
        if self._stable_since is None:
            self._stable_since = now_s
        if now_s - self._stable_since >= c.settle_s:
            return self._decision(Mode.SLEEP, "stable dwell complete")
        return self._decision(Mode.SETTLING, "waiting for stable dwell")


class SleepRuntime:
    """Callback adapter; keeps balance running while gating expensive generation.

    balance_step(sample, decision) must handle hold/recovery/fault without the
    motion generator. It returns True only when its tick completed successfully.
    A failed callback latches FAULT and invokes on_fault; generator exceptions
    also latch FAULT. Exceptions propagate. on_fault must be independently safe.
    Hard real-time users must run balance/watchdog in a separate execution domain.
    """

    def __init__(self, supervisor: SleepSupervisor, *, balance_step: Callable,
                 generate_step: Callable, on_fault: Callable):
        self.supervisor = supervisor
        self.balance_step = balance_step
        self.generate_step = generate_step
        self.on_fault = on_fault

    def step(self, sample, now_s, **requests):
        decision = self.supervisor.tick(sample, now_s, **requests)
        try:
            if self.balance_step(sample, decision) is not True:
                raise RuntimeError("Balance controller did not acknowledge tick")
            if decision.generate_motion:
                self.generate_step()
        except Exception:
            self.supervisor._decision(Mode.FAULT, "callback failed")
            self.on_fault()
            raise
        return decision
