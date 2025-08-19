from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Dict, Tuple
import yaml, os, datetime as dt

Mode = Literal['off','heat','cool','auto']

DAYS = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']

@dataclass
class Event:
    time: str            # 'HH:MM' 24h
    mode: Mode
    setpoint_c: float

@dataclass
class DaySchedule:
    events: List[Event] = field(default_factory=list)

@dataclass
class Schedule:
    days: Dict[str, DaySchedule] = field(default_factory=lambda: {d: DaySchedule() for d in DAYS})

def load_schedule(path: str) -> Schedule:
    if not os.path.exists(path):
        return Schedule()
    data = yaml.safe_load(open(path, 'r')) or {}
    sch = Schedule()
    for d in DAYS:
        lst = data.get(d, []) or []
        evs = []
        for e in lst[:6]:  # up to 6
            try:
                evs.append(Event(time=str(e['time']), mode=str(e['mode']), setpoint_c=float(e['setpoint_c'])))
            except Exception:
                continue
        # sort by time
        evs.sort(key=lambda E: E.time)
        sch.days[d] = DaySchedule(evs)
    return sch

def save_schedule(path: str, sch: Schedule) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out = {d: [{'time': e.time, 'mode': e.mode, 'setpoint_c': float(e.setpoint_c)} for e in sch.days[d].events[:6]] for d in DAYS}
    with open(path, 'w') as f:
        yaml.safe_dump(out, f, sort_keys=True)

def evaluate(sch: Schedule, when: dt.datetime) -> Tuple[Mode, float] | None:
    day = DAYS[when.weekday()]
    evs = sch.days[day].events
    if not evs:
        return None
    # pick the last event whose time <= now
    now_hm = when.strftime('%H:%M')
    last = None
    for e in evs:
        if e.time <= now_hm:
            last = e
        else:
            break
    if last is None:
        # wrap to previous day's last event
        prev_day = DAYS[(when.weekday() - 1) % 7]
        evs_prev = sch.days[prev_day].events
        if evs_prev:
            last = evs_prev[-1]
    return (last.mode, last.setpoint_c) if last else None
