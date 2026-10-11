from tests.helpers import login, make_patient

GOOD = "correct-horse-battery"


def test_enrollment_codes_are_gone(client):
    admin = login(client, "admin@medora.tn")
    assert client.post("/patients/p-0002/enrollment-code", headers=admin).status_code == 404
    assert "/patients/{patient_id}/enrollment-code" not in client.get("/openapi.json").json()["paths"]


def test_patient_password_reset_code_from_attending_or_admin(client, db):
    # patient@medora.tn owns p-0001, whose attending doctor is u-0001
    r = client.post("/patients/p-0001/reset-code", headers=login(client, "doctor@medora.tn"))
    assert r.status_code == 200
    assert client.post("/auth/reset", json={"email": "patient@medora.tn", "code": r.json()["code"],
                                            "new_password": GOOD}).status_code == 204
    assert client.post("/patients/p-0001/reset-code", headers=login(client, "nurse@medora.tn")).status_code == 403
    p = make_patient(db, attending="u-0001")  # no account yet
    assert client.post(f"/patients/{p.id}/reset-code", headers=login(client, "admin@medora.tn")).status_code == 404
