"""Health watch: the hospital city's weather and air quality (Open-Meteo, free, no key) and health news (WHO news RSS,
WHO Disease Outbreak News, Google News RSS for Tunisia in French and Arabic). Only the city's coordinates leave the
server, never patient data. Results are cached; a failed source gives an empty part, never an error."""

import logging
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)
TTL_S = 1800
TIMEOUT_S = 8.0
FORECAST = "https://api.open-meteo.com/v1/forecast"
AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"
WHO_RSS = "https://www.who.int/rss-feeds/news-english.xml"
WHO_DON = "https://www.who.int/api/news/diseaseoutbreaknews?$orderby=PublicationDate%20desc&$top=8"
LOCAL_NEWS = {
    "fr": "https://news.google.com/rss/search?q=sant%C3%A9+Tunisie&hl=fr&gl=TN&ceid=TN:fr",
    "ar": "https://news.google.com/rss/search?q=%D8%A7%D9%84%D8%B5%D8%AD%D8%A9+%D8%AA%D9%88%D9%86%D8%B3&hl=ar&gl=TN&ceid=TN:ar",
}
NEWS_PER_SOURCE = 6
NEWS_MAX = 15

_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, fn):
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < TTL_S:
        return hit[1]
    value = fn()
    _cache[key] = (time.monotonic(), value)
    return value


def clear_cache() -> None:
    _cache.clear()


def _get(url: str, **params) -> httpx.Response:
    r = httpx.get(url, params=params or None, timeout=TIMEOUT_S, follow_redirects=True,
                  headers={"User-Agent": "Ward-hospital-prototype/1.0"})
    r.raise_for_status()
    return r


def _days() -> list[dict]:
    s = get_settings()
    f = _get(FORECAST, latitude=s.hospital_lat, longitude=s.hospital_lon, timezone="Africa/Tunis", past_days=1,
             forecast_days=4, daily="temperature_2m_max,temperature_2m_min,apparent_temperature_max,"
                                    "wind_gusts_10m_max,precipitation_sum,uv_index_max").json()["daily"]
    days = [{"date": d, "tmax": f["temperature_2m_max"][i], "tmin": f["temperature_2m_min"][i],
             "apparent_max": f["apparent_temperature_max"][i], "gusts": f["wind_gusts_10m_max"][i],
             "precip": f["precipitation_sum"][i], "uv": f["uv_index_max"][i],
             "dust_max": None, "pm10_max": None, "aqi_max": None} for i, d in enumerate(f["time"])]
    try:
        a = _get(AIR, latitude=s.hospital_lat, longitude=s.hospital_lon, timezone="Africa/Tunis", past_days=1,
                 forecast_days=4, hourly="dust,pm10,us_aqi").json()["hourly"]
        for day in days:
            idx = [i for i, t in enumerate(a["time"]) if t.startswith(day["date"])]
            for key, src in (("dust_max", "dust"), ("pm10_max", "pm10"), ("aqi_max", "us_aqi")):
                vals = [a[src][i] for i in idx if a[src][i] is not None]
                day[key] = max(vals) if vals else None
    except Exception as e:  # air quality is a bonus: the forecast still counts
        log.warning("air quality unavailable: %s", e)
    return days


def weather() -> dict:
    """{"city", "days": [...] (yesterday first), "available"}"""
    s = get_settings()
    if s.health_watch_offline:
        return {"city": s.hospital_city, "days": [], "available": False}
    try:
        return {"city": s.hospital_city, "days": _cached("weather", _days), "available": True}
    except Exception as e:
        log.warning("weather unavailable: %s", e)
        return {"city": s.hospital_city, "days": [], "available": False}


def _rss(url: str, source: str, lang: str) -> list[dict]:
    root = ET.fromstring(_get(url).content)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        pub = item.findtext("pubDate")
        try:
            published = parsedate_to_datetime(pub).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if pub else None
        except (TypeError, ValueError):
            published = None
        src = item.findtext("source") or source
        out.append({"title": title, "link": link, "source": src.strip(), "published": published, "lang": lang})
        if len(out) >= NEWS_PER_SOURCE:
            break
    return out


def _who_don() -> list[dict]:
    rows = _get(WHO_DON).json().get("value", [])
    out = []
    for r in rows[:NEWS_PER_SOURCE]:
        url = r.get("ItemDefaultUrl") or r.get("UrlName") or ""
        link = url if url.startswith("http") else f"https://www.who.int/emergencies/disease-outbreak-news/item{url}"
        published = (r.get("PublicationDate") or "")[:19] + "Z" if r.get("PublicationDate") else None
        out.append({"title": r.get("Title") or r.get("OverrideTitle") or "", "link": link,
                    "source": "WHO Disease Outbreak News", "published": published, "lang": "en"})
    return [x for x in out if x["title"]]


def _news() -> list[dict]:
    parts = []
    for name, fn in (("who", lambda: _rss(WHO_RSS, "WHO", "en")), ("don", _who_don),
                     *((f"local_{lg}", (lambda u=u, lg=lg: _rss(u, "Google News", lg))) for lg, u in LOCAL_NEWS.items())):
        try:
            parts.extend(fn())
        except Exception as e:
            log.warning("news source %s unavailable: %s", name, e)
    seen, out = set(), []
    for n in sorted(parts, key=lambda x: x["published"] or "", reverse=True):
        if n["link"] in seen:
            continue
        seen.add(n["link"])
        out.append(n)
    return out[:NEWS_MAX]


def news() -> list[dict]:
    if get_settings().health_watch_offline:
        return []
    return _cached("news", _news)


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
