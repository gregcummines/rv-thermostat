from typing import Optional, Dict, Any
try:
    import requests  # type: ignore
except Exception:
    requests = None

def owm_current(lat: float, lon: float, api_key: str, units: str = 'imperial') -> Optional[Dict[str, Any]]:
    if not requests or not api_key:
        return None
    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"lat": lat, "lon": lon, "appid": api_key.strip(), "units": units},
            timeout=5,
        )
        if not r.ok:
            # Helpful when debugging: uncomment the next line to inspect the error
            print("OWM error:", r.status_code, r.text)
            return None
        d = r.json()
        main = d.get("main", {}) or {}
        wx = (d.get("weather") or [{}])[0]
        return {
            "temp": float(main.get("temp")) if main.get("temp") is not None else None,
            "desc": wx.get("main") or wx.get("description") or "",
            "icon": wx.get("icon") or "",
            "city": d.get("name") or "",
            "raw": d,
        }
    except Exception:
        return None

def fmt_temp(temp: Optional[float], units: str) -> str:
    if temp is None:
        return "--"
    return f"{round(temp):.0f}{'°F' if units=='imperial' else '°C'}"
