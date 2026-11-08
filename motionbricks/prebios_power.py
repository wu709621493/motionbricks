"""Offline, voltage/current-specific pre-BIOS contract. Standard library only.

No hardware access or actuation. Declared limits and telemetry are unverified
inputs, never manufacturer approval. A healthy sample is not permission to flash,
raise voltage, enable a rail, or claim memory stability/lifetime.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path


def _number(value, name, minimum=0.0, *, positive=False):
    if type(value) not in (int, float):
        raise ValueError(f"{name}: finite SI number required")
    try:
        valid = math.isfinite(value) and value >= minimum
    except OverflowError:
        valid = False
    if not valid or (positive and value <= 0):
        raise ValueError(f"{name}: invalid range or nonfinite value")
    return value


def _text(value, name):
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name}: nonempty text required")


def _rate(value):
    if type(value) is not int or not 1 <= value <= 7200:
        raise ValueError("rate_mts must be an integer in the project range 1..7200")


def _finite_result(value):
    return _number(value, "computed result")


def dc_power_w(voltage_v, current_a):
    """DC / simultaneous V-I estimate. Not mean(V)*mean(I) for varying signals."""
    _number(voltage_v, "voltage_v")
    _number(current_a, "current_a")
    return _finite_result(voltage_v * current_a)


def resistive_loss_w(current_a, resistance_ohm):
    """DC I²R; varying-current heating requires RMS current, not mean current."""
    _number(current_a, "current_a")
    _number(resistance_ohm, "resistance_ohm")
    return _finite_result(current_a * current_a * resistance_ohm)


def compare_supply_paths(*, load_power_w, bus_voltages_v,
                         path_resistance_ohm, converter_efficiency):
    """Explicit lumped approximation, with a converter-input reference plane.

    For each row the listed bus voltage is the converter INPUT terminal voltage.
    I = P_load / (eta * V_input); source terminal V = V_input + I*R.
    Source power includes conversion loss and upstream wire loss. This is not a
    fixed-source-voltage circuit solution or a design recommendation. Efficiency
    is assumed constant across rows, and no switching/thermal model is inferred.
    """
    _number(load_power_w, "load_power_w")
    _number(path_resistance_ohm, "path_resistance_ohm")
    _number(converter_efficiency, "converter_efficiency", positive=True)
    if converter_efficiency > 1:
        raise ValueError("converter_efficiency must be <= 1")
    if type(bus_voltages_v) not in (tuple, list) or not bus_voltages_v:
        raise ValueError("bus_voltages_v must be a nonempty sequence")
    converter_input_w = _finite_result(load_power_w / converter_efficiency)
    conversion_loss_w = _finite_result(converter_input_w - load_power_w)
    rows = []
    for voltage in bus_voltages_v:
        _number(voltage, "converter input voltage", positive=True)
        current = _finite_result(converter_input_w / voltage)
        wire_loss = resistive_loss_w(current, path_resistance_ohm)
        rows.append({
            "converter_input_v": voltage,
            "input_current_a": current,
            "source_terminal_v": _finite_result(voltage + current * path_resistance_ohm),
            "wire_loss_w": wire_loss,
            "conversion_loss_w": conversion_loss_w,
            "source_power_w": _finite_result(converter_input_w + wire_loss),
            "hardware_setting_recommended": False,
        })
    return rows


@dataclass(frozen=True)
class RailLimits:
    rail_id: str
    accounting: str  # input or load; never sum these groups together
    min_voltage_v: float
    max_voltage_v: float
    max_current_a: float
    max_power_w: float
    min_temp_c: float
    stop_temp_c: float
    path_resistance_ohm: float | None  # unknown is None, not zero

    def __post_init__(self):
        _text(self.rail_id, "rail_id")
        if self.accounting not in ("input", "load"):
            raise ValueError("accounting must be input or load")
        for name in ("min_voltage_v", "max_voltage_v", "max_current_a", "max_power_w"):
            _number(getattr(self, name), name, positive=True)
        if self.min_voltage_v >= self.max_voltage_v:
            raise ValueError("voltage interval must have positive width")
        _number(self.min_temp_c, "min_temp_c", -273.15)
        _number(self.stop_temp_c, "stop_temp_c", -273.15)
        if self.min_temp_c >= self.stop_temp_c:
            raise ValueError("temperature interval must have positive width")
        if self.path_resistance_ohm is not None:
            _number(self.path_resistance_ohm, "path_resistance_ohm")


@dataclass(frozen=True)
class PowerProfile:
    platform_id: str
    profile_id: str
    generation: str
    rate_mts: int
    evidence_kind: str
    evidence_ref: str
    rails: tuple[RailLimits, ...]
    max_total_load_power_w: float
    max_sample_age_s: float
    max_sample_gap_s: float

    def __post_init__(self):
        for name in ("platform_id", "profile_id", "evidence_ref"):
            _text(getattr(self, name), name)
        if self.generation not in ("DDR4", "DDR5"):
            raise ValueError("generation must be DDR4 or DDR5")
        _rate(self.rate_mts)
        if self.evidence_kind not in ("synthetic", "hardware_trace_unverified"):
            raise ValueError("unsupported evidence_kind")
        if type(self.rails) is not tuple or not self.rails:
            raise ValueError("rails must be a nonempty immutable tuple")
        if any(type(rail) is not RailLimits for rail in self.rails):
            raise ValueError("every rail must have RailLimits")
        if len({rail.rail_id for rail in self.rails}) != len(self.rails):
            raise ValueError("duplicate rail limit")
        if not any(rail.accounting == "load" for rail in self.rails):
            raise ValueError("at least one load rail required")
        for name in ("max_total_load_power_w", "max_sample_age_s", "max_sample_gap_s"):
            _number(getattr(self, name), name, positive=True)


@dataclass(frozen=True)
class RailReading:
    rail_id: str
    voltage_v: float
    current_a: float
    temp_c: float
    voltage_error_v: float
    current_error_a: float
    temp_error_c: float


@dataclass(frozen=True)
class PowerFrame:
    timestamp_s: float
    boot_id: str
    platform_id: str
    profile_id: str
    generation: str
    rate_mts: int
    rails: tuple[RailReading, ...]


class PowerGuard:
    """Offline sampled envelope checker with an irreversible per-instance trip.

    Single owner, monotonic timestamps. Restarting the Python object starts a new
    log-review session; it does not acknowledge a physical fault or reset a PMIC.
    Timing and uncertainty checks cannot replace hardware transient protection.
    """
    def __init__(self, profile: PowerProfile):
        if type(profile) is not PowerProfile:
            raise ValueError("PowerProfile required")
        self.profile = profile
        self._previous = None
        self._last_now_s = None
        self._fault = None

    def _report(self, status, reasons, metrics=None):
        return {
            "schema_version": 1,
            "status": status,
            "reasons": list(reasons),
            "metrics": metrics,
            "evidence_kind": self.profile.evidence_kind,
            "hardware_applied": False,
            "hardware_authorized": False,
            "memory_stability_validated": False,
            "lifetime_proven": False,
        }

    def _trip(self, *reasons):
        self._fault = tuple(reasons)
        return self._report("TRIPPED", self._fault)

    def observe(self, frame: PowerFrame, *, now_s: float):
        if self._fault is not None:
            return self._report("TRIPPED", self._fault)
        try:
            return self._observe(frame, now_s)
        except (ValueError, TypeError, AttributeError, OverflowError):
            return self._trip("INVALID_TELEMETRY")

    def _observe(self, frame, now_s):
        p = self.profile
        if type(frame) is not PowerFrame or type(frame.rails) is not tuple:
            return self._trip("INVALID_TELEMETRY")
        _number(now_s, "now_s")
        _number(frame.timestamp_s, "timestamp_s")
        _text(frame.boot_id, "boot_id")
        _rate(frame.rate_mts)
        if (frame.platform_id, frame.profile_id, frame.generation, frame.rate_mts) != (
                p.platform_id, p.profile_id, p.generation, p.rate_mts):
            return self._trip("PLATFORM_OR_PROFILE_MISMATCH")
        if not 0 <= now_s - frame.timestamp_s <= p.max_sample_age_s:
            return self._trip("STALE_OR_FUTURE_SAMPLE")
        if self._previous is not None:
            if frame.boot_id != self._previous.boot_id:
                return self._trip("BOOT_CHANGED")
            if not 0 < frame.timestamp_s - self._previous.timestamp_s <= p.max_sample_gap_s:
                return self._trip("SAMPLE_CLOCK_OR_GAP")
            if not 0 < now_s - self._last_now_s <= p.max_sample_gap_s:
                return self._trip("OBSERVER_CLOCK_OR_GAP")
        if any(type(rail) is not RailReading for rail in frame.rails):
            return self._trip("INVALID_TELEMETRY")
        limits = {rail.rail_id: rail for rail in p.rails}
        ids = [rail.rail_id for rail in frame.rails]
        if len(ids) != len(set(ids)) or set(ids) != set(limits):
            return self._trip("MISSING_EXTRA_OR_DUPLICATE_RAIL")
        reasons, metrics = [], {}
        load_w, load_upper_w, input_w = 0.0, 0.0, 0.0
        for reading in frame.rails:
            limit = limits[reading.rail_id]
            for name in ("voltage_v", "current_a", "voltage_error_v", "current_error_a", "temp_error_c"):
                _number(getattr(reading, name), name)
            _number(reading.temp_c, "temp_c", -273.15)
            v_lo = _finite_result(max(0.0, reading.voltage_v - reading.voltage_error_v))
            v_hi = _finite_result(reading.voltage_v + reading.voltage_error_v)
            i_hi = _finite_result(reading.current_a + reading.current_error_a)
            nominal_w = dc_power_w(reading.voltage_v, reading.current_a)
            upper_w = dc_power_w(v_hi, i_hi)
            if not (limit.min_voltage_v <= v_lo and v_hi <= limit.max_voltage_v):
                reasons.append(f"{reading.rail_id}:VOLTAGE_LIMIT")
            if i_hi > limit.max_current_a:
                reasons.append(f"{reading.rail_id}:CURRENT_LIMIT")
            if upper_w > limit.max_power_w:
                reasons.append(f"{reading.rail_id}:POWER_LIMIT")
            if not (limit.min_temp_c <= reading.temp_c - reading.temp_error_c
                    and reading.temp_c + reading.temp_error_c < limit.stop_temp_c):
                reasons.append(f"{reading.rail_id}:TEMPERATURE_LIMIT")
            metrics[reading.rail_id] = {
                "accounting": limit.accounting,
                "dc_power_w": nominal_w,
                "dc_power_upper_w": upper_w,
                "modeled_dc_wire_loss_w": None if limit.path_resistance_ohm is None else
                    resistive_loss_w(reading.current_a, limit.path_resistance_ohm),
            }
            if limit.accounting == "load":
                load_w = _finite_result(load_w + nominal_w)
                load_upper_w = _finite_result(load_upper_w + upper_w)
            else:
                input_w = _finite_result(input_w + nominal_w)
        if load_upper_w > p.max_total_load_power_w:
            reasons.append("TOTAL_LOAD_POWER_LIMIT")
        if reasons:
            return self._trip(*reasons)
        self._previous, self._last_now_s = frame, now_s
        return self._report("WITHIN_DECLARED_ENVELOPE", [], {
            "rails": metrics,
            "total_load_dc_power_w": load_w,
            "total_load_dc_power_upper_w": load_upper_w,
            "total_input_dc_power_w": input_w if any(r.accounting == "input" for r in p.rails) else None,
        })


def profile_from_dict(data):
    data = dict(data)
    data["rails"] = tuple(RailLimits(**item) for item in data["rails"])
    return PowerProfile(**data)


def frame_from_dict(data):
    data = dict(data)
    data["rails"] = tuple(RailReading(**item) for item in data["rails"])
    return PowerFrame(**data)


def review_trace(payload):
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    if set(payload) != {"schema_version", "profile", "observations"}:
        raise ValueError("unexpected or missing trace fields")
    observations = payload["observations"]
    if type(observations) is not list or not observations:
        raise ValueError("observations must be a nonempty list")
    guard = PowerGuard(profile_from_dict(payload["profile"]))
    for count, observation in enumerate(observations, start=1):
        if set(observation) != {"now_s", "frame"}:
            raise ValueError("observation requires now_s and frame")
        report = guard.observe(frame_from_dict(observation["frame"]), now_s=observation["now_s"])
        if report["status"] == "TRIPPED":
            break
    return {"observations_checked": count, "observations_supplied": len(observations), **report}


def synthetic_trace():
    """Invented thresholds; not DDR5 settings or a platform qualification."""
    rails = (
        RailLimits("VIN", "input", 4.8, 5.2, 2, 9, 0, 70, 0.02),
        RailLimits("VDD", "load", 1.4, 1.5, 4, 5, 0, 70, 0.005),
        RailLimits("VDDQ", "load", 1.4, 1.5, 2, 3, 0, 70, None),
        RailLimits("VPP", "load", 1.7, 1.9, 0.3, 0.6, 0, 70, None),
    )
    p = PowerProfile("SIM-BOARD-CPU-DIMM", "SIM-DDR5-7200", "DDR5", 7200,
                     "synthetic", "SIMULATION-NOT-APPROVAL", rails, 7, 0.1, 1)
    readings = (
        RailReading("VIN", 5, 1.1, 45, 0.01, 0.01, 1),
        RailReading("VDD", 1.45, 2, 55, 0.01, 0.01, 1),
        RailReading("VDDQ", 1.45, 1, 54, 0.01, 0.01, 1),
        RailReading("VPP", 1.8, 0.1, 50, 0.01, 0.005, 1),
    )
    observations = []
    for t in (0.0, 0.5, 1.0):
        frame = PowerFrame(t, "SIM-BOOT", p.platform_id, p.profile_id, p.generation, p.rate_mts, readings)
        observations.append({"now_s": t, "frame": asdict(frame)})
    return {"schema_version": 1, "profile": asdict(p), "observations": observations}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--trace", type=Path)
    args = parser.parse_args(argv)
    try:
        payload = synthetic_trace() if args.demo else json.loads(args.trace.read_text(encoding="utf-8"))
        result = review_trace(payload)
        if args.demo:
            result["supply_comparison"] = compare_supply_paths(
                load_power_w=10, bus_voltages_v=[5, 10],
                path_resistance_ohm=0.02, converter_efficiency=0.9)
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, TypeError, KeyError, AttributeError, OSError, OverflowError) as exc:
        print(json.dumps({"status": "INVALID_INPUT", "error": str(exc),
                          "hardware_applied": False, "hardware_authorized": False}))
        return 2
    return 1 if result["status"] == "TRIPPED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
