from types import SimpleNamespace as NS

from app.services import integrations as I


def test_secret_check(monkeypatch):
    monkeypatch.setattr(I, "get_settings", lambda: NS(n8n_callback_secret="s3cret"))
    assert I.callback_secret_ok("s3cret") is True
    assert I.callback_secret_ok("wrong") is False
    assert I.callback_secret_ok(None) is False
    assert I.callback_secret_ok("") is False


def test_secret_check_rejects_when_unset(monkeypatch):
    monkeypatch.setattr(I, "get_settings", lambda: NS(n8n_callback_secret=""))
    assert I.callback_secret_ok("") is False


def test_digest_entries_shape_and_filtering():
    doc1 = NS(id="u-0001", name="Dr Trabelsi", email="doctor@medora.tn")
    doc2 = NS(id="u-0007", name="Dr Haddad", email="haddad@medora.tn")
    rows = [
        (doc1, NS(first_name="Amira", last_name="Ben Salah"), "C-12", 5, "Fever overnight."),
        (doc1, NS(first_name="Sami", last_name="Gharbi"), "C-14", None, "Stable."),
    ]
    out = I.digest_entries(rows, doctors=[doc1, doc2])
    assert out == [{"doctor": {"id": "u-0001", "name": "Dr Trabelsi", "email": "doctor@medora.tn"},
                    "patients": [{"name": "Amira", "bed": "C-12", "news2": 5, "summary": "Fever overnight."},
                                 {"name": "Sami", "bed": "C-14", "news2": None, "summary": "Stable."}]}]
