"""Posture state machine: pure, no I/O, no clocks.

    step(state, sample, config) -> (new_state, events)

The machine is stateless per request: the caller loads `MachineState` from the
session row, calls `step`, then persists the new state and the emitted events.
Time ONLY comes from `sample.t` (epoch ms), never from the wall clock.

States
    AWAY       nobody in frame (timers paused / cleared)
    GOOD       matches the goal posture (within the user's sensitivity)
    DEVIATING  off-posture, inside the user's grace period (slouch threshold)
    SLOUCHING  off-posture for >= the user's slouch threshold; alerts fire here

COOLDOWN is NOT a separate state. It is "an alert was sent less than
`cooldown_sec` ago" (`last_alert_t`), so time spent slouching is never split in
two for analytics. If the user is still slouching when the cooldown ends we
escalate (up to MAX_ALERTS_PER_EPISODE), otherwise we stay quiet.

How a sample is read (the model owns `label`/`deviation`, we own the policy):
    * confidence < MIN_CONFIDENCE or label UNKNOWN -> ignored entirely
    * label AWAY                                   -> AWAY (debounced)
    * otherwise `deviation` is compared with the USER's sensitivity:
        deviation >= bad_deviation   -> BAD
        deviation <= good_deviation  -> GOOD
        in between                   -> NEUTRAL (hysteresis dead-band)
      (if `deviation` is missing we fall back to the label)
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Optional

AWAY = "AWAY"
GOOD = "GOOD"
DEVIATING = "DEVIATING"
SLOUCHING = "SLOUCHING"
STATES = (AWAY, GOOD, DEVIATING, SLOUCHING)

# Tunables that are not user-facing.
MIN_CONFIDENCE = 0.5
RECOVER_SEC = 3.0          # must look good this long before DEVIATING/SLOUCHING -> GOOD
AWAY_AFTER_SEC = 5.0       # must look away this long before -> AWAY (debounce)
MAX_GAP_SEC = 20.0         # no usable sample for this long => treat as AWAY (phone asleep etc.)
MAX_ALERTS_PER_EPISODE = 3 # gentle escalation, then stop until the user recovers
HYSTERESIS_RATIO = 0.75    # good_deviation = bad_deviation * ratio


@dataclass(frozen=True)
class Config:
    slouch_threshold_sec: float = 30.0
    sensitivity: float = 0.5          # 0 = forgiving ... 1 = strict
    cooldown_sec: float = 120.0
    alert_phone: bool = True
    alert_desktop: bool = True
    quiet_hours_enabled: bool = False
    quiet_start_min: int = 22 * 60    # minutes after local midnight
    quiet_end_min: int = 7 * 60
    tz_offset_min: int = 0            # local = UTC + offset
    focus_only: bool = False          # nudge ONLY during a focus session the user started
    focus_until_ms: int = 0           # the active focus session ends at this time (epoch ms; 0 = none)

    @property
    def bad_deviation(self) -> float:
        # sensitivity 0 -> 0.60, 0.5 -> 0.40, 1 -> 0.20
        return 0.6 - 0.4 * min(1.0, max(0.0, self.sensitivity))

    @property
    def good_deviation(self) -> float:
        return self.bad_deviation * HYSTERESIS_RATIO


@dataclass(frozen=True)
class Sample:
    t: int                              # epoch ms (phone clock)
    label: str = "UNKNOWN"              # GOOD | SLOUCHING | AWAY | UNKNOWN
    deviation: Optional[float] = None   # 0 = goal posture, higher = worse
    confidence: float = 1.0


@dataclass(frozen=True)
class MachineState:
    state: str = AWAY
    since: Optional[int] = None             # ms: when `state` was entered
    last_t: Optional[int] = None            # ms: last usable sample time
    deviating_since: Optional[int] = None   # start of the current off-posture run
    recovering_since: Optional[int] = None  # start of the current good run (while DEVIATING/SLOUCHING)
    away_since: Optional[int] = None        # start of the current away run (while not AWAY)
    last_alert_t: Optional[int] = None      # survives GOOD so cooldown spans episodes
    alerts_sent: int = 0                    # alerts in the current episode (reset on GOOD)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state, "since": self.since, "last_t": self.last_t,
            "deviating_since": self.deviating_since, "recovering_since": self.recovering_since,
            "away_since": self.away_since, "last_alert_t": self.last_alert_t,
            "alerts_sent": self.alerts_sent,
        }

    @staticmethod
    def from_dict(d: Optional[dict[str, Any]]) -> "MachineState":
        if not d:
            return MachineState()
        return MachineState(
            state=d.get("state", AWAY), since=d.get("since"), last_t=d.get("last_t"),
            deviating_since=d.get("deviating_since"), recovering_since=d.get("recovering_since"),
            away_since=d.get("away_since"), last_alert_t=d.get("last_alert_t"),
            alerts_sent=int(d.get("alerts_sent") or 0),
        )


@dataclass(frozen=True)
class Event:
    """kind='transition': from_state -> to_state. kind='alert': an extra nudge while
    already SLOUCHING (escalation). `alert=True` means a push should be sent now."""
    kind: str
    t: int
    from_state: str
    to_state: str
    alert: bool = False
    level: int = 0                       # 1 = first nudge, 2/3 = escalations
    reason: str = ""
    deviation: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "t": self.t, "from_state": self.from_state,
            "to_state": self.to_state, "alert": self.alert, "level": self.level,
            "reason": self.reason, "deviation": self.deviation,
        }


# ---------------------------------------------------------------- helpers

BAD, NEUTRAL, IGNORE = "BAD", "NEUTRAL", "IGNORE"


def classify(sample: Sample, config: Config) -> str:
    """Return one of AWAY / GOOD / BAD / NEUTRAL / IGNORE."""
    if sample.confidence < MIN_CONFIDENCE or sample.label == "UNKNOWN":
        return IGNORE
    if sample.label == "AWAY":
        return AWAY
    if sample.deviation is None:
        return BAD if sample.label == "SLOUCHING" else GOOD
    if sample.deviation >= config.bad_deviation:
        return BAD
    if sample.deviation <= config.good_deviation:
        return GOOD
    return NEUTRAL


def in_quiet_hours(t_ms: int, config: Config) -> bool:
    if not config.quiet_hours_enabled or config.quiet_start_min == config.quiet_end_min:
        return False
    minute_of_day = ((t_ms // 60_000) + config.tz_offset_min) % 1440
    s, e = config.quiet_start_min, config.quiet_end_min
    return s <= minute_of_day < e if s < e else (minute_of_day >= s or minute_of_day < e)


def in_cooldown(machine: MachineState, t_ms: int, config: Config) -> bool:
    return machine.last_alert_t is not None and (t_ms - machine.last_alert_t) < config.cooldown_sec * 1000


def _alert_due(machine: MachineState, t: int, config: Config) -> bool:
    if not (config.alert_phone or config.alert_desktop):
        return False
    if machine.alerts_sent >= MAX_ALERTS_PER_EPISODE:
        return False
    if in_quiet_hours(t, config):
        return False
    if config.focus_only and t > config.focus_until_ms:
        return False           # focus mode: no nudges outside a focus session
    return not in_cooldown(machine, t, config)


def _enter(machine: MachineState, to: str, t: int) -> MachineState:
    """Move to `to`, clearing the timers that don't apply there."""
    if to == GOOD:
        return replace(machine, state=GOOD, since=t, deviating_since=None,
                       recovering_since=None, away_since=None, alerts_sent=0)
    if to == AWAY:
        return replace(machine, state=AWAY, since=t, deviating_since=None,
                       recovering_since=None, away_since=None, alerts_sent=0)
    if to == DEVIATING:
        return replace(machine, state=DEVIATING, since=t, deviating_since=t,
                       recovering_since=None, away_since=None)
    # SLOUCHING keeps deviating_since (the run began earlier)
    return replace(machine, state=SLOUCHING, since=t, recovering_since=None, away_since=None)


def _transition(machine: MachineState, to: str, t: int, events: list[Event], *,
                reason: str, deviation: Optional[float], alert: bool = False,
                level: int = 0) -> MachineState:
    events.append(Event("transition", t, machine.state, to, alert=alert, level=level,
                        reason=reason, deviation=deviation))
    return _enter(machine, to, t)


# ---------------------------------------------------------------- the machine

def step(state: MachineState, sample: Sample, config: Config) -> tuple[MachineState, list[Event]]:
    """Advance the machine by one sample. Pure: returns a new state + the events to persist."""
    events: list[Event] = []
    m = state
    t = sample.t
    dev = sample.deviation

    # Very first sample for this session: the machine "exists" from now.
    if m.last_t is None:
        m = replace(m, since=t, last_t=t)
    # Samples can arrive out of order across serverless invocations; never go back in time.
    t = max(t, m.last_t)

    kind = classify(sample, config)
    if kind == IGNORE:
        return m, events  # not even a heartbeat: a long run of unusable samples reads as a gap

    # No usable sample for a long time (phone asleep / app killed): close the old state at the
    # last time we actually saw them, then treat this sample as someone (re)appearing.
    if m.state != AWAY and (t - m.last_t) > MAX_GAP_SEC * 1000:
        m = _transition(m, AWAY, m.last_t, events, reason="gap", deviation=None)

    if kind == AWAY:
        if m.state != AWAY:
            away_since = m.away_since if m.away_since is not None else t
            m = replace(m, away_since=away_since)
            if t - away_since >= AWAY_AFTER_SEC * 1000:
                # stamp the transition when they actually left, not when we became sure
                m = _transition(m, AWAY, away_since, events, reason="left_frame", deviation=None)
        return replace(m, last_t=t), events

    # From here the person is visible (GOOD / BAD / NEUTRAL).
    m = replace(m, away_since=None)

    if m.state == AWAY:
        if kind == BAD:
            m = _transition(m, DEVIATING, t, events, reason="appeared", deviation=dev)
        else:
            m = _transition(m, GOOD, t, events, reason="appeared", deviation=dev)

    elif m.state == GOOD:
        if kind == BAD:
            m = _transition(m, DEVIATING, t, events, reason="deviated", deviation=dev)

    elif m.state == DEVIATING:
        if kind == BAD:
            m = replace(m, recovering_since=None)
            assert m.deviating_since is not None
            if t - m.deviating_since >= config.slouch_threshold_sec * 1000:
                due = _alert_due(m, t, config)
                m = _transition(m, SLOUCHING, t, events, reason="threshold", deviation=dev,
                                alert=due, level=(m.alerts_sent + 1) if due else 0)
                if due:
                    m = replace(m, alerts_sent=m.alerts_sent + 1, last_alert_t=t)
        elif kind == GOOD:
            m = _maybe_recover(m, t, events, dev)

    elif m.state == SLOUCHING:
        if kind == BAD:
            m = replace(m, recovering_since=None)
            if _alert_due(m, t, config):  # still slouching after the cooldown: gentle escalation
                level = m.alerts_sent + 1
                events.append(Event("alert", t, SLOUCHING, SLOUCHING, alert=True, level=level,
                                    reason="escalation", deviation=dev))
                m = replace(m, alerts_sent=level, last_alert_t=t)
        elif kind == GOOD:
            m = _maybe_recover(m, t, events, dev)

    return replace(m, last_t=t), events


def _maybe_recover(m: MachineState, t: int, events: list[Event], dev: Optional[float]) -> MachineState:
    recovering_since = m.recovering_since if m.recovering_since is not None else t
    m = replace(m, recovering_since=recovering_since)
    if t - recovering_since >= RECOVER_SEC * 1000:
        # stamp when they actually sat up, not when we became sure
        return _transition(m, GOOD, recovering_since, events, reason="recovered", deviation=dev)
    return m


# ---------------------------------------------------------------- read-side helper

def describe(machine: MachineState, now_t: int, config: Config) -> dict[str, Any]:
    """Derived facts for /status. `now_t` is on the same clock as sample times."""
    since = machine.since if machine.since is not None else now_t
    out: dict[str, Any] = {
        "state": machine.state,
        "timeInStateSec": max(0.0, (now_t - since) / 1000),
        "inCooldown": in_cooldown(machine, now_t, config),
        "alertsSent": machine.alerts_sent,
        "deviatingForSec": None,
    }
    if machine.state in (DEVIATING, SLOUCHING) and machine.deviating_since is not None:
        out["deviatingForSec"] = max(0.0, (now_t - machine.deviating_since) / 1000)
    return out
