"""Health watch: weather-health rules, risk groups and routes (network mocked)."""

import pytest

from app.ai import weather_health as W
from app.config import get_settings
from app.services import healthwatch as H
from tests.helpers import login


def day(date, tmax=25.0, tmin=17.0, apparent_max=25.0, dust_max=0.0, aqi_max=40, precip=0.0, **kw):
    return {"date": date, "tmax": tmax, "tmin": tmin, "apparent_max": apparent_max, "dust_max": dust_max,
            "pm10_max": None, "aqi_max": aqi_max, "precip": precip, "gusts": 30, "uv": 5, **kw}


CALM = [day("2026-10-09"), day("2026-10-10"), day("2026-10-11"), day("2026-10-12")]


def test_calm_week_has_no_alert():
    assert W.evaluate(CALM) == []


def test_heatwave_fires_high_and_sudden_warming_but_not_moderate_heat():
    days = [day("2026-10-09", tmax=24), day("2026-10-10", tmax=38, apparent_max=41)]
    ids = [a["id"] for a in W.evaluate(days)]
    assert ids == ["heat_high", "sudden_warming"]
    a = W.evaluate(days)[0]
    assert a["title"]["fr"] == "Vague de chaleur : 41 °C ressentis" and "cardiac" in a["groups"]


@pytest.mark.parametrize("d, rule", [
    (day("x", tmin=8), "cold_snap"),            # 17 -> 8: -9 overnight
    (day("x", tmin=2, tmax=20), "cold"),        # plain cold night is shadowed by the snap when both fire
    (day("x", dust_max=320), "dust"),
    (day("x", dust_max=90), "dust_moderate"),
    (day("x", precip=45), "heavy_rain"),
])
def test_each_rule(d, rule):
    prev = day("y", tmin=17 if rule != "cold" else 4)
    assert rule in [a["id"] for a in W.evaluate([prev, d])]


def test_patient_groups_from_age_and_history():
    assert W.patient_groups(80, "") == {"elderly"}
    assert W.patient_groups(54, "Hypertension") == {"cardiac"}
    assert W.patient_groups(30, "BPCO, asthme depuis l'enfance") == {"respiratory"}
    assert W.patient_groups(40, "مريض بالسكري") == {"diabetes"}


@pytest.fixture
def heat(monkeypatch):
    days = [day("2026-10-09", tmax=24), day("2026-10-10", tmax=38, apparent_max=41), day("2026-10-11")]
    monkeypatch.setattr(H, "weather", lambda: {"city": "Tunis", "days": days, "available": True})
    monkeypatch.setattr(H, "news", lambda: [{"title": "WHO news", "link": "https://who.int/x", "source": "WHO",
                                             "published": "2026-10-10T08:00:00Z", "lang": "en"}])


def test_staff_see_alerts_with_their_at_risk_patients_and_news(client, heat):
    r = client.get("/health-watch", headers=login(client, "doctor@ward.tn"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["days"]) == 2 and body["news"][0]["source"] == "WHO"
    heat_alert = next(a for a in body["alerts"] if a["id"] == "heat_high")
    assert "p-0001" in {p["id"] for p in heat_alert["at_risk"]}  # Amira: hypertension -> cardiac
    admin = client.get("/health-watch", headers=login(client, "admin@ward.tn")).json()
    assert all(a["at_risk"] == [] and a["at_risk_count"] >= 1 for a in admin["alerts"] if a["id"] == "heat_high")


def test_patient_sees_advice_marked_when_it_concerns_them(client, heat):
    r = client.get("/health-watch/me", headers=login(client, "patient@ward.tn"))
    a = next(x for x in r.json()["alerts"] if x["id"] == "heat_high")
    assert a["concerns_me"] and "staff" not in a and a["patient"]["ar"]
    assert client.get("/health-watch", headers=login(client, "patient@ward.tn")).status_code == 403


def test_n8n_reads_alerts_without_names(client, heat):
    assert client.get("/integrations/n8n/health-watch").status_code == 401
    r = client.get("/integrations/n8n/health-watch", headers={"X-N8N-Secret": get_settings().n8n_callback_secret})
    a = r.json()["alerts"][0]
    assert a["at_risk_count"] >= 1 and "at_risk" not in a and a["staff"]["fr"]


def test_demo_scenario_is_labelled(client, monkeypatch):
    monkeypatch.setattr(H, "weather", lambda: {"city": "Tunis", "days": CALM, "available": True})
    monkeypatch.setattr(H, "news", lambda: [])
    monkeypatch.setenv("HEALTH_WATCH_DEMO", "dust")
    get_settings.cache_clear()
    body = client.get("/health-watch", headers=login(client, "nurse@ward.tn")).json()
    assert body["demo"] == "dust" and body["alerts"][0]["id"] == "dust"
    monkeypatch.delenv("HEALTH_WATCH_DEMO")
    get_settings.cache_clear()
