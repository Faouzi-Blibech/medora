"""GET/POST/PATCH /drugs (api 1.12 → Drug catalogue)."""

import pytest
from sqlalchemy import select

from app.models import AuditLog, Drug
from tests.helpers import login, pharmacist

NEW = {"dci": "Nitrofurantoin", "brand_names": ["Furadantine"], "form": "capsule", "strength": "50 mg", "unit_mg": 50,
       "max_daily_mg": 400, "atc_code": "j01xe01", "allergy_classes": [" Nitrofuran "], "interaction_groups": [],
       "high_alert": False, "min_stock": 20}


def _ids(rows):
    return {r["id"] for r in rows}


@pytest.mark.parametrize("q,expected", [("amox", {"d-0003", "d-0004", "d-0005"}), ("doliprane", {"d-0001", "d-0002"}),
                                        ("J01FA", {"d-0006", "d-0007"}), ("j01fa", {"d-0006", "d-0007"})])
def test_search_by_dci_brand_or_atc(client, q, expected):
    r = client.get("/drugs", params={"q": q}, headers=login(client, "doctor@medora.tn"))
    assert r.status_code == 200 and _ids(r.json()) == expected


def test_search_shape_and_limit(client):
    rows = client.get("/drugs", headers=login(client, "nurse@medora.tn")).json()
    assert len(rows) == 50  # 51 drugs, capped
    assert set(rows[0]) == {"id", "dci", "brand_names", "form", "strength", "unit_mg", "max_daily_mg", "atc_code",
                            "allergy_classes", "interaction_groups", "high_alert", "min_stock", "active", "created_at",
                            "updated_at"}
    amox = next(r for r in client.get("/drugs", params={"q": "clamoxyl"},
                                      headers=login(client, "nurse@medora.tn")).json() if r["id"] == "d-0003")
    assert (amox["unit_mg"], amox["max_daily_mg"], amox["active"]) == (1000.0, 6000.0, True)


@pytest.mark.parametrize("q", ["_", "باراسيتامول", "a'b"])
def test_search_input_is_literal(client, q):
    r = client.get("/drugs", params={"q": q}, headers=login(client, "doctor@medora.tn"))
    assert r.status_code == 200 and r.json() == []


def test_percent_is_a_literal_not_a_wildcard(client):
    r = client.get("/drugs", params={"q": "%"}, headers=login(client, "doctor@medora.tn"))
    assert _ids(r.json()) == {"d-0027"}  # only the brand "KCl 10%"; a wildcard would match all 50


def test_read_roles(client):
    for email in ("doctor@medora.tn", "nurse@medora.tn", "admin@medora.tn"):
        assert client.get("/drugs", headers=login(client, email)).status_code == 200
    assert client.get("/drugs", headers=login(client, "patient@medora.tn")).status_code == 403
    assert client.get("/drugs").status_code == 401


def test_pharmacist_creates_a_drug(client, db):
    r = client.post("/drugs", headers=pharmacist(client, db), json=NEW)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["id"].startswith("d-") and (d["atc_code"], d["allergy_classes"], d["active"]) == (
        "J01XE01", ["nitrofuran"], True)
    assert db.scalar(select(AuditLog.id).where(AuditLog.resource == "drug", AuditLog.action == "create",
                                               AuditLog.resource_id == d["id"]))
    again = client.post("/drugs", headers=login(client, "ph.t@medora.tn"), json={**NEW, "dci": "nitrofurantoin"})
    assert again.status_code == 409 and again.json()["code"] == "conflict"


def test_who_may_write(client, db):
    assert client.post("/drugs", headers=login(client, "doctor@medora.tn"), json=NEW).status_code == 403
    assert client.post("/drugs", headers=login(client, "nurse@medora.tn"), json=NEW).status_code == 403
    assert client.post("/drugs", headers=login(client, "admin@medora.tn"), json=NEW).status_code == 201
    assert client.patch("/drugs/d-0001", headers=login(client, "doctor@medora.tn"),
                        json={"min_stock": 1}).status_code == 403


@pytest.mark.parametrize("bad", [{"form": "powder"}, {"atc_code": "XYZ"}, {"allergy_classes": ["Penicillin!"]},
                                 {"unit_mg": 0}, {"min_stock": -1}, {"dci": ""}, {"colour": "red"}])
def test_invalid_drug_is_422(client, db, bad):
    r = client.post("/drugs", headers=pharmacist(client, db), json={**NEW, **bad})
    assert r.status_code == 422 and r.json()["code"] == "invalid"


def test_patch_and_deactivate(client, db):
    h = pharmacist(client, db)
    r = client.patch("/drugs/d-0041", headers=h, json={"min_stock": 30, "brand_names": ["Mopral", "Zoltum"]})
    assert r.status_code == 200 and (r.json()["min_stock"], r.json()["brand_names"]) == (30, ["Mopral", "Zoltum"])
    assert client.patch("/drugs/d-0041", headers=h, json={"active": False}).json()["active"] is False
    assert "d-0041" not in _ids(client.get("/drugs", params={"q": "omepra"}, headers=h).json())
    assert _ids(client.get("/drugs", params={"q": "omepra", "active": "false"}, headers=h).json()) == {"d-0041"}
    assert "d-0041" in _ids(client.get("/drugs", params={"q": "omepra", "active": "all"}, headers=h).json())
    assert db.get(Drug, "d-0041") is not None  # deactivated, never deleted
    assert client.patch("/drugs/d-0041", headers=h, json={"dci": None}).status_code == 422
    assert client.patch("/drugs/d-9999", headers=h, json={"min_stock": 1}).status_code == 404
    assert client.patch("/drugs/d-0002", headers=h, json={"strength": "500 mg"}).status_code == 409  # = d-0001
    assert client.delete("/drugs/d-0041", headers=h).status_code == 405
