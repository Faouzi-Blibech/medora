"""AI radiograph reading (spec 2026-10-10-radiograph-reading-design.md). The model only drafts; a doctor confirms.
Works with no model: `template()` is the blank structured report (source "rules").

Smoke test on the demo laptop:  VISION_PROVIDER=local python -m app.ai.radiology path/to/xray.jpg
"""

import io
import json
import sys
import time
from pathlib import Path
from typing import Literal

from PIL import Image, ImageOps
from pydantic import BaseModel, Field

from app.ai import llm
from app.config import get_settings

MAX_SIDE = 1024
DISCLAIMER = "AI draft from a prototype, not a diagnosis and not clinically validated. A doctor must review it."
RULES = json.loads((Path(__file__).parent / "rules" / "radiograph.v1.json").read_text(encoding="utf-8"))
LANG_NAME = {"fr": "French", "en": "English"}
HEAD = {
    "fr": ("Technique", "Résultats", "Conclusion", "Diagnostics possibles", "Signes urgents", "Recommandation"),
    "en": ("Technique", "Findings", "Impression", "Possible conditions", "Urgent signs", "Recommendation"),
}
LIKELY = {"fr": {"low": "faible", "medium": "moyenne", "high": "élevée"},
          "en": {"low": "low", "medium": "medium", "high": "high"}}


class Condition(BaseModel):
    name: str = Field(max_length=160)
    likelihood: Literal["low", "medium", "high"]
    evidence: str = Field(default="", max_length=400)


class RadiographDraft(BaseModel):
    region: str = Field(default="", max_length=80)
    projection: str = Field(default="", max_length=80)
    quality: str = Field(default="", max_length=300)
    findings: list[str] = Field(default_factory=list, max_length=15)
    impression: str = Field(default="", max_length=800)
    possible_conditions: list[Condition] = Field(default_factory=list, max_length=6)
    urgent_flags: list[str] = Field(default_factory=list, max_length=6)
    recommendation: str = Field(default="", max_length=400)


def _lang(lang: str) -> str:
    return lang if lang in HEAD else "fr"


def _label(title: str, lang: str, value: str = "") -> str:
    """'Title : value' in French, 'Title: value' in English (a bare 'Title :' when there is no value)."""
    sep = " :" if lang == "fr" else ":"
    return f"{title}{sep} {value}" if value else f"{title}{sep}"


MAX_PIXELS = 50_000_000


def _to_grey(im: Image.Image) -> Image.Image:
    """8-bit grey; 16-bit / float images are rescaled to their real range first (convert("L") would clip them)."""
    if im.mode.startswith(("I", "F")):
        im = im.convert("I") if im.mode != "I" else im
        lo, hi = im.getextrema()
        scale = 255 / (hi - lo) if hi > lo else 1
        im = im.point(lambda v: (v - lo) * scale)
    return im.convert("L")


def prepare_image(data: bytes) -> bytes:
    """Decode, apply EXIF orientation, grey-scale, fit in MAX_SIDE, re-encode as a fresh PNG (no metadata)."""
    with Image.open(io.BytesIO(data)) as im:
        if im.width * im.height > MAX_PIXELS:
            raise ValueError("image too large")
        if im.format == "JPEG":
            im.draft("L", (MAX_SIDE * 2, MAX_SIDE * 2))
        im = _to_grey(ImageOps.exif_transpose(im))
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        im.save(out, format="PNG")
    return out.getvalue()


def render(d: RadiographDraft, lang: str) -> str:
    lang = _lang(lang)
    h, lk = HEAD[lang], LIKELY[lang]
    tech = ", ".join(x for x in (d.region, d.projection, d.quality) if x)
    parts = [_label(h[0], lang, tech), _label(h[1], lang), *[f"- {f}" for f in d.findings],
             _label(h[2], lang, d.impression)]
    if d.possible_conditions:
        parts.append(_label(h[3], lang))
        parts += [f"- {c.name} ({lk[c.likelihood]}){' — ' + c.evidence if c.evidence else ''}"
                  for c in d.possible_conditions]
    if d.urgent_flags:
        parts.append(_label(h[4], lang, "; ".join(d.urgent_flags)))
    if d.recommendation:
        parts.append(_label(h[5], lang, d.recommendation))
    return "\n".join(parts)


def template(lang: str, reason: str) -> dict:
    lang = _lang(lang)
    h = HEAD[lang]
    text = "\n\n".join(_label(x, lang) for x in (h[0], h[1], h[2], h[5]))
    return {"source": "rules", "reason": reason[:200], "draft_text": text, "disclaimer": DISCLAIMER}


def read(data: bytes, hint: str = "") -> tuple[str, dict]:
    """(status, ai_suggested): "ready" with a model draft, "unavailable" (no model / bad output) or "failed"
    (unreadable image), the last two with the blank template."""
    s = get_settings()
    lang = _lang(s.radiology_report_lang)
    try:
        png = prepare_image(data)
    except Exception:
        return "failed", template(lang, "unreadable image")
    try:
        d = llm.complete_vision_json("radiograph_report", png,
                                     f"Language: {LANG_NAME[lang]}. Requested exam: {hint or 'radiograph'}.",
                                     RadiographDraft)
    except llm.LLMUnavailable as e:
        bad = any(k in str(e).lower() for k in ("validation", "json", "expecting"))
        return "unavailable", template(lang, "invalid model output" if bad else "vision model unavailable")
    return "ready", {"source": "llm", "model": s.llm_vision_model, **d.model_dump(),
                     "draft_text": render(d, lang), "disclaimer": DISCLAIMER}


if __name__ == "__main__":
    t0 = time.monotonic()
    status, ai = read(Path(sys.argv[1]).read_bytes(), " ".join(sys.argv[2:]))
    print(json.dumps({"status": status, "seconds": round(time.monotonic() - t0, 1), **ai}, ensure_ascii=False, indent=2))
