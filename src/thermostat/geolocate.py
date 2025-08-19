from __future__ import annotations
from typing import Optional, Dict, Any
try:
    import requests  # type: ignore
except Exception:
    requests = None
def resolve_location(cfg) -> Optional[Dict[str, Any]]:
    # manual first
    lat=cfg.location.manual.lat; lon=cfg.location.manual.lon
    if lat is not None and lon is not None: return {'lat':float(lat),'lon':float(lon),'source':'manual'}
    # ip-api fallback
    if not requests: return None
    try:
        r = requests.get('http://ip-api.com/json', timeout=4)
        if r.ok and r.json().get('status')=='success':
            j=r.json(); return {'lat':float(j['lat']), 'lon':float(j['lon']), 'source':'ip-api'}
    except Exception: pass
    return None
