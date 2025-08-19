from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Dict, Tuple
import yaml, os, datetime as dt
Mode = Literal['off','heat','cool','auto']
DAYS = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
@dataclass
class Event: time:str; mode:Mode; setpoint_c:float
@dataclass
class DaySchedule: events: List[Event]=field(default_factory=list)
@dataclass
class Schedule: days: Dict[str, DaySchedule]=field(default_factory=lambda:{d:DaySchedule() for d in DAYS})
def load_schedule(path:str)->Schedule:
    if not os.path.exists(path): return Schedule()
    d=yaml.safe_load(open(path)) or {}; s=Schedule()
    for day in DAYS:
        arr=d.get(day,[]) or []; evs=[]
        for e in arr[:6]:
            try: evs.append(Event(time=str(e['time']), mode=str(e['mode']), setpoint_c=float(e['setpoint_c'])))
            except Exception: pass
        evs.sort(key=lambda E:E.time); s.days[day]=DaySchedule(evs)
    return s
def save_schedule(path:str, s:Schedule)->None:
    os.makedirs(os.path.dirname(path),exist_ok=True)
    out={day:[{'time':e.time,'mode':e.mode,'setpoint_c':float(e.setpoint_c)} for e in s.days[day].events[:6]] for day in DAYS}
    yaml.safe_dump(out, open(path,'w'), sort_keys=True)
def evaluate(s:Schedule, when:dt.datetime):
    evs=s.days[DAYS[when.weekday()]].events
    if not evs: return None
    now=when.strftime('%H:%M'); last=None
    for e in evs:
        if e.time<=now: last=e
        else: break
    if last is None:
        prev=DAYS[(when.weekday()-1)%7]; evs2=s.days[prev].events
        if evs2: last=evs2[-1]
    return (last.mode,last.setpoint_c) if last else None
