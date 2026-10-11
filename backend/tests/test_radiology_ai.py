import io
import json

import httpx
import pytest
from PIL import Image

from app.ai import llm, radiology
from app.config import get_settings


def jpeg_with_exif(w=2000, h=1500) -> bytes:
    im = Image.new("RGB", (w, h), (90, 90, 90))
    exif = Image.Exif()
    exif[0x010E] = "Patient: Amira Ben Salah"  # ImageDescription
    buf = io.BytesIO()
    im.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


DRAFT = {"region": "chest", "projection": "PA", "quality": "adequate", "findings": ["Clear lung fields"],
         "impression": "No acute abnormality seen.",
         "possible_conditions": [{"name": "Normal chest", "likelihood": "high", "evidence": "clear lungs"}],
         "urgent_flags": [], "recommendation": ""}


class FakeResp:
    def __init__(self, content: str, status: int = 200):
        self._content, self.status_code = content, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)

    def json(self):
        return {"message": {"content": self._content}}


@pytest.fixture()
def local_vision(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "vision_provider", "local")
    monkeypatch.setattr(s, "llm_vision_model", "qwen3-vl:4b")
    return s


def test_prepare_image_strips_metadata_and_caps_size():
    png = radiology.prepare_image(jpeg_with_exif())
    im = Image.open(io.BytesIO(png))
    assert im.format == "PNG" and max(im.size) == radiology.MAX_SIDE and im.mode == "L"
    assert "exif" not in im.info and not im.getexif()


def test_prepare_image_rejects_garbage():
    with pytest.raises(Exception):
        radiology.prepare_image(b"not an image")


def test_vision_call_payload(monkeypatch, local_vision):
    seen = {}

    def fake_post(url, timeout, json):  # noqa: A002
        seen.update(url=url, timeout=timeout, body=json)
        return FakeResp(__import__("json").dumps(DRAFT))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    out = llm.complete_vision_json("radiograph_report", b"PNGDATA", "Exam: Chest X-ray", radiology.RadiographDraft)
    assert out.region == "chest"
    body = seen["body"]
    assert seen["url"].endswith("/api/chat") and body["model"] == "qwen3-vl:4b" and body["stream"] is False
    user = body["messages"][1]
    assert user["images"] == ["UE5HREFUQQ=="] and "format" in body
    assert body["messages"][-1]["role"] == "assistant" and "</think>" in body["messages"][-1]["content"]  # no thinking


def test_vision_no_think_prefill_only_for_qwen3(monkeypatch, local_vision):
    monkeypatch.setattr(get_settings(), "llm_vision_model", "qwen2.5vl:3b")
    seen = {}

    def fake_post(url, timeout, json):  # noqa: A002
        seen.update(body=json)
        return FakeResp(__import__("json").dumps(DRAFT))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    llm.complete_vision_json("radiograph_report", b"x", "", radiology.RadiographDraft)
    assert [m["role"] for m in seen["body"]["messages"]] == ["system", "user"]


def test_vision_needs_local_provider(monkeypatch):
    monkeypatch.setattr(get_settings(), "vision_provider", "none")
    with pytest.raises(llm.LLMUnavailable):
        llm.complete_vision_json("radiograph_report", b"x", "", radiology.RadiographDraft)


def test_read_ready(monkeypatch, local_vision):
    monkeypatch.setattr(llm.httpx, "post", lambda url, timeout, json: FakeResp(__import__("json").dumps(DRAFT)))
    status, ai = radiology.read(jpeg_with_exif(), "Chest X-ray")
    assert status == "ready" and ai["source"] == "llm" and ai["model"] == "qwen3-vl:4b"
    assert ai["disclaimer"] == radiology.DISCLAIMER and "No acute abnormality" in ai["draft_text"]
    assert ai["possible_conditions"][0]["likelihood"] == "high"


@pytest.mark.parametrize("content", ["not json", json.dumps({"possible_conditions": [{"name": "x", "likelihood": "certain"}]})])
def test_read_invalid_output_is_unavailable(monkeypatch, local_vision, content):
    monkeypatch.setattr(llm.httpx, "post", lambda url, timeout, json: FakeResp(content))
    status, ai = radiology.read(jpeg_with_exif(), "")
    assert status == "unavailable" and ai["source"] == "rules" and ai["draft_text"]


def test_read_timeout_is_unavailable(monkeypatch, local_vision):
    def boom(url, timeout, json):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(llm.httpx, "post", boom)
    assert radiology.read(jpeg_with_exif(), "")[0] == "unavailable"


def test_read_without_model_gives_template(monkeypatch):
    monkeypatch.setattr(get_settings(), "vision_provider", "none")
    monkeypatch.setattr(get_settings(), "radiology_report_lang", "fr")
    status, ai = radiology.read(jpeg_with_exif(), "")
    assert status == "unavailable" and ai["draft_text"].startswith("Technique")
    assert "Conclusion" in ai["draft_text"]


def test_read_garbage_is_failed():
    status, ai = radiology.read(b"%PDF-1.4 nope", "")
    assert status == "failed" and ai["source"] == "rules" and ai["draft_text"]


def test_render_english(monkeypatch):
    d = radiology.RadiographDraft.model_validate(DRAFT | {"urgent_flags": ["Possible pneumothorax"]})
    text = radiology.render(d, "en")
    assert text.index("Findings") < text.index("Impression") and "Possible pneumothorax" in text


def test_render_french_uses_spaced_colon():
    d = radiology.RadiographDraft.model_validate(DRAFT)
    text = radiology.render(d, "fr")
    assert "Conclusion : No acute" in text and "Résultats :" in text and "(élevée)" in text


def test_prepare_image_rescales_16_bit():
    im = Image.new("I;16", (64, 64))
    im.putdata([(i % 64) * 4000 // 63 for i in range(64 * 64)])
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    lo, hi = Image.open(io.BytesIO(radiology.prepare_image(buf.getvalue()))).getextrema()
    assert hi - lo > 100


def test_read_pixel_bomb_is_failed():
    buf = io.BytesIO()
    Image.new("L", (8000, 8000)).save(buf, format="PNG")
    assert radiology.read(buf.getvalue(), "")[0] == "failed"


def test_read_http_500_is_unavailable(monkeypatch, local_vision):
    monkeypatch.setattr(llm.httpx, "post", lambda url, timeout, json: FakeResp("", 500))
    status, ai = radiology.read(jpeg_with_exif(), "")
    assert status == "unavailable" and ai["reason"] == "vision model unavailable"
