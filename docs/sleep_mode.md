# Balance-aware sleep (experimental CPU supervisor)

Sleep pauses expensive motion generation after a stable dwell while retaining
an independent balance/hold controller on every tick. It does not suspend the OS,
disable motors, alter gains, lower balance sensor rates, or freeze an animation
and call that physical balance. This opt-in adapter is not enabled in the GUI,
CPU ONNX reference, TensorRT pipeline, or experimental quantum interfaces.

## Contract

`motionbricks.sleep_mode` uses only the Python standard library. The caller
supplies measured tilt magnitude (radians), speed magnitude (m/s), signed support
margin (metres), confirmed support, controller readiness and monotonic timestamps.
An estimator must calculate these using actual geometry and contact sensing;
generated foot contacts alone are not a physical support measurement. A positive
static margin is only one admission signal, not a dynamic stability proof.

| State | Motion generation | Balance callback | Exit |
| --- | --- | --- | --- |
| ACTIVE | Allowed | Every tick | Sleep request plus strict entry conditions |
| SETTLING | Allowed | Every tick | Continuous stable dwell, otherwise restart |
| SLEEP | Paused | Every tick; hold posture | Wake/request cleared, disturbance or fault |
| RECOVERY | Paused | Independent recovery | Healthy sample plus explicit controller acknowledgement |
| FAULT | Paused | Fault handling | Healthy sample plus explicit reset, then RECOVERY |

Default illustrative thresholds: 2 s dwell, 50 ms sample age/tick-gap limit,
entry/exit tilt 0.03/0.08 rad, speed 0.01/0.05 m/s and support margin
0.04/0.02 m. These are uncalibrated software defaults, not G1 operating limits.
Hysteresis prevents small fluctuations repeatedly waking the generator. At the
exit boundary, contact loss or disturbance wins over user wake. Recovery cannot
be bypassed by maintaining a sleep request. Fault reset never resumes generation
directly. No balancing torque is computed here.

## Integration

```python
from motionbricks.sleep_mode import SleepRuntime, SleepSupervisor

runtime = SleepRuntime(
    SleepSupervisor(),
    balance_step=controller.tick,  # (sample, decision) -> exactly True on success
    generate_step=planner.generate_next,  # zero-argument adapter/closure
    on_fault=controller.request_safe_recovery,
)
# On each monotonic balance tick, using current measured telemetry:
decision = runtime.step(sample, now_s, sleep_requested=idle_request,
                        wake=user_command,
                        recovery_complete=controller.recovered)
```

The callbacks are application-provided, not existing MotionBricks robot drivers.
Wrap the chosen CPU/TensorRT planner without changing its tensor contract.
The balance callback must retain ownership of support/hold/recovery, acknowledge
a completed tick with True, and treat FAULT telemetry as potentially invalid.
Do not reuse stale planned frames after waking: regenerate from measured current
pose/history and blend through the downstream controller's validated limits.
For a real planner, use bounded queues, cancel/expire pending work on sleep,
and ensure old worker results cannot regain control after a state change.

`SleepRuntime` is a synchronous reference adapter: a blocked callback can block
its tick. Real-time deployment requires an independent watchdog and separate
balance execution domain with bounded communication; this module detects missed
deadlines only when called again. Callback failures latch FAULT, invoke on_fault
and propagate the error. on_fault itself must be fail-safe. Normal telemetry
faults are delivered to balance_step via Decision and remain latched.

## Energy and physical validation

A supported seated/docked rest posture may reduce actuator demand, but selecting
and transitioning to it requires a separate collision/contact/torque validated
controller. Standing sleep still needs actuator power. This version saves only
optional generation calls; it does not claim electrical savings or reduced heat.
Keep sensing, balance, thermal/battery limits and emergency recovery independent
of the optional generator and any remote/experimental compute backend.

Run `python -m unittest discover -s tests/sleep_mode -v`. Nine offline tests cover
dwell reset, hysteresis, wake, support/margin/speed disturbances, invalid and stale
samples, deadline/backward clock faults, recovery gates and callback failures.
A deterministic 100-tick trace with 0.1 s dwell at 100 Hz runs balance 100 times
and generation 10 times (versus 100 without sleep). This is a callback-count
comparison, not a physics simulation or measured 90% energy reduction.
The existing Ubuntu x86/ARM and macOS ARM Python 3.12/3.13 matrix runs this suite.

Before hardware admission: compare active idle and sleep with identical measured
loads; report watt-hours, RMS/peak tilt, support margin, actuator temperature,
wake-to-ready latency and recovery success. Include pushes, slopes, slipping or
lost support, sensor loss, frozen generator and low battery. Validate lower-power
postures and resumption separately in physics simulation and restrained hardware.
No real-robot balance, energy, latency, or quantum/BEC coherence result is claimed.
