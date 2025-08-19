from __future__ import annotations
import subprocess, time
from typing import Optional, Dict, Any
try:
    import requests  # type: ignore
except Exception:
    requests = None
class GeoResult(Dict[str, Any]):
    lat: float; lon: float; source: str; accuracy_m: float
def _manual_loc(cfg) -> Optional[GeoResult]:
    lat = cfg.location.manual.lat; lon = cfg.location.manual.lon
    if lat is not None and lon is not None:
        return {'lat': float(lat), 'lon': float(lon), 'source': 'manual', 'accuracy_m': 10000.0}
    return None
def _gpsd_loc() -> Optional[GeoResult]:
    try:
        import gps  # type: ignore
        session = gps.gps(mode=gps.WATCH_ENABLE)
        start = time.time()
        while time.time() - start < 2.5:
            rep = session.next()
            if getattr(rep,'class',None)=='TPV' and getattr(rep,'lat',None) and getattr(rep,'lon',None):
                lat=float(getattr(rep,'lat')); lon=float(getattr(rep,'lon'))
                acc=float(getattr(rep,'epy',25.0) or 25.0)*2.0
                return {'lat':lat,'lon':lon,'source':'gpsd','accuracy_m':acc}
    except Exception: pass
    return None
def _wifi_scan_bssids(iface: str) -> list[dict]:
    try:
        p = subprocess.run(['/usr/sbin/iw','dev',iface,'scan'], capture_output=True, text=True, timeout=4)
        if p.returncode != 0: return []
        aps=[]; mac=None; sig=None
        for line in p.stdout.splitlines():
            line=line.strip()
            if line.startswith('BSS '):
                if mac: aps.append({'macAddress': mac, 'signalStrength': int(sig) if sig is not None else -50})
                mac=line.split()[1]; sig=None
            elif line.startswith('signal:'):
                try: sig=int(float(line.split()[1]))
                except Exception: sig=None
        if mac: aps.append({'macAddress': mac, 'signalStrength': int(sig) if sig is not None else -50})
        return aps[:15]
    except Exception: return []
def _wifi_loc_mls(iface: str, api_key: str | None) -> Optional[GeoResult]:
    if not api_key or not requests: return None
    aps = _wifi_scan_bssids(iface)
    if not aps: return None
    try:
        r = requests.post(f'https://location.services.mozilla.com/v1/geolocate?key={api_key}', json={'wifiAccessPoints': aps}, timeout=4)
        if r.ok:
            j=r.json()
            return {'lat': j['location']['lat'], 'lon': j['location']['lng'], 'source': 'wifi-mls', 'accuracy_m': float(j.get('accuracy', 100.0))}
    except Exception: pass
    return None
def _ip_loc(provider: str = 'ip-api') -> Optional[GeoResult]:
    if not requests: return None
    try:
        if provider=='ipinfo':
            r = requests.get('https://ipinfo.io/json', timeout=4)
            if r.ok:
                j=r.json()
                lat,lon=map(float,j['loc'].split(',')); return {'lat':lat,'lon':lon,'source':'ipinfo','accuracy_m':50000.0}
        else:
            r = requests.get('http://ip-api.com/json', timeout=4)
            if r.ok and r.json().get('status')=='success':
                j=r.json()
                return {'lat': float(j['lat']), 'lon': float(j['lon']), 'source': 'ip-api','accuracy_m':50000.0}
    except Exception: pass
    return None
_last_good: Optional[GeoResult] = None
def resolve_location(cfg) -> Optional[GeoResult]:
    global _last_good
    m=_manual_loc(cfg)
    if m: _last_good=m; return m
    g=_gpsd_loc()
    if g: _last_good=g; return g
    w=_wifi_loc_mls(cfg.location.wifi.iface, cfg.location.wifi.mls_api_key)
    if w: _last_good=w; return w
    i=_ip_loc(cfg.location.ip.provider)
    if i: _last_good=i; return i
    return _last_good
