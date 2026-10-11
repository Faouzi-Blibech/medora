import jwt

from app.config import get_settings
from tests.helpers import login


def test_login_returns_token_and_user(client):
    r = client.post("/auth/login", json={"email": "patient@medora.tn", "password": "ward1234"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"] == {"id": "u-0005", "name": "Amira Ben Salah", "role": "patient", "patient_id": "p-0001"}
    claims = jwt.decode(body["access_token"], get_settings().jwt_secret, algorithms=["HS256"])
    assert claims["sub"] == "u-0005" and claims["role"] == "patient" and claims["patient_id"] == "p-0001"
    assert "exp" in claims


def test_login_wrong_password(client):
    r = client.post("/auth/login", json={"email": "doctor@medora.tn", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["code"] == "bad_credentials"


def test_me(client):
    r = client.get("/me", headers=login(client, "nurse@medora.tn"))
    assert r.json() == {"id": "u-0002", "name": "Nurse Ines", "email": "nurse@medora.tn", "role": "nurse",
                        "patient_id": None}


def test_me_requires_token(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer junk"}).status_code == 401
