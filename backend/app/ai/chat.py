"""Role chat assistants (owner: Faouzi): doctor, nurse and patient ask questions in any language and get an answer
built only from one patient's record, every claim cited by passage number.

- The LLM goes through app/ai/llm.py (names stripped) with a role prompt from app/ai/prompts/chat_<role>.v1.md.
- An answer that cites an unknown passage or cites nothing is discarded. Numbers found nowhere in the question,
  the passages or the conversation are returned in "unverified" for staff to check; a patient answer with one is
  discarded.
- Without an LLM: doctors and nurses get the best-matching passages; patients get the rule-based assistant.
- Patients: red-flag questions never reach a model; they get the urgent or crisis answer.
"""

import logging
import re
from datetime import UTC, datetime, timedelta, timezone

from pydantic import BaseModel

from app.ai import assistant, rag
from app.ai.llm import LLMUnavailable, complete_json
from app.ai.triage import match_red_flags
from app.config import get_settings

ROLES = ("doctor", "nurse", "patient")
MAX_HISTORY = 6
NO_LLM = "The AI assistant is offline. These passages from the record match your question:"
NO_MATCH = "The AI assistant is offline and nothing in this record matches the question."
LANG_NAMES = {"en": "English", "fr": "French", "ar": "Arabic"}
TUNIS = timezone(timedelta(hours=1))  # Africa/Tunis: UTC+1, no DST


def _now_line() -> str:
    """The model cannot know the time: 'next dose' and 'today' need it."""
    return f"Current date and time (Tunis): {datetime.now(UTC).astimezone(TUNIS):%A %d %B %Y, %H:%M}."
log = logging.getLogger(__name__)


class _LlmChat(BaseModel):
    answer: str
    citations: list[int] = []
    found: bool = True  # false: the record does not answer the question (then no citation is needed)


def _numbers(text: str) -> set[str]:
    """Values to check: numbers that are not part of a name such as COVID-19, HbA1c or SpO2."""
    return set(re.findall(r"(?<![^\W_])(?<![^\W\d_]-)\d+(?:[.,]\d+)?", text))


def _cite(p: rag.Passage) -> dict:
    s = p.source
    return {"source_id": s.id, "kind": s.kind, "title": s.title, "ts": s.ts, "text": p.text}


def _prompt_text(question: str, ctx: list[rag.Passage], history: list[dict], lang: str | None, now_line: str) -> str:
    lines = [now_line, "Patient record passages:"]
    lines += [f"[{i}] {p.source.title}: {p.text}" for i, p in enumerate(ctx, 1)]
    if history:
        lines.append("\nConversation so far:")
        lines += [f"{'User' if h['role'] == 'user' else 'Assistant'}: {h['text']}" for h in history[-MAX_HISTORY:]]
    if lang in LANG_NAMES:
        lines.append(f"\nInterface language: {LANG_NAMES[lang]} (answer in the language of the question).")
    lines.append(f"\nQuestion: {question}")
    return "\n".join(lines)


def _fallback(role: str, question: str, ps: list[rag.Passage], patient_ctx: dict | None) -> dict:
    if role == "patient" and patient_ctx is not None:
        out = assistant.answer(question, patient_ctx)
        return {"answer": out["answer"], "citations": [], "source": "rules"}
    top = rag.rank(question, ps)
    return {"answer": NO_LLM if top else NO_MATCH, "citations": [_cite(p) for p in top], "source": "rules"}


def answer(role: str, question: str, sources: list[rag.Source], *, names: list[str], history: list[dict] = (),
           lang: str | None = None, patient_ctx: dict | None = None) -> dict:
    """{"answer", "citations": [{source_id, kind, title, ts, text}], "source": "llm"|"rules", "unverified"?, "urgent"?}"""
    if role == "patient":
        flags = {f["id"] for f in match_red_flags(question)}
        if flags:
            text = assistant.CRISIS if "suicide_self_harm" in flags else assistant.URGENT
            return {"answer": text, "citations": [], "source": "rules", "urgent": True}
    ps = rag.passages(sources)
    if get_settings().llm_provider == "none" or not ps:
        return _fallback(role, question, ps, patient_ctx)
    ctx = rag.context(question, ps)
    now_line = _now_line()
    history = list(history)[-MAX_HISTORY:]
    try:
        out = complete_json(f"chat_{role}", _prompt_text(question, ctx, history, lang, now_line), _LlmChat, names=names)
    except LLMUnavailable:
        return _fallback(role, question, ps, patient_ctx)
    cited = [n for n in dict.fromkeys(out.citations) if 1 <= n <= len(ctx)]
    allowed = _numbers(question) | _numbers(" ".join(f"{p.source.title} {p.text}" for p in ctx)) | _numbers(
        " ".join(h["text"] for h in history)) | {str(n) for n in range(1, len(ctx) + 1)} | {"190"} | _numbers(now_line)  # SAMU, the clock
    unverified = sorted(_numbers(out.answer) - allowed)
    if not out.answer.strip() or len(cited) != len(set(out.citations)) or (out.found and not cited):
        log.info("chat answer discarded: bad citations %s", out.citations)
        return _fallback(role, question, ps, patient_ctx)
    if unverified and role == "patient":  # a patient never sees a value that is not in their record
        log.info("chat answer discarded: numbers not in the record %s", unverified)
        return _fallback(role, question, ps, patient_ctx)
    return {"answer": out.answer.strip(), "citations": [_cite(ctx[n - 1]) | {"n": n} for n in cited], "source": "llm",
            "unverified": unverified}


GENERAL_OFFLINE = "The AI assistant is offline. Mention a patient with @ to search their record."


class _LlmGeneral(BaseModel):
    answer: str


def answer_general(role: str, question: str, *, history: list[dict] = (), lang: str | None = None) -> dict:
    """A staff question with no patient: general medical knowledge, no record, no citations."""
    if get_settings().llm_provider == "none":
        return {"answer": GENERAL_OFFLINE, "citations": [], "source": "rules"}
    lines = [f"User role: {role}.", _now_line()]
    if history:
        lines.append("Conversation so far:")
        lines += [f"{'User' if h['role'] == 'user' else 'Assistant'}: {h['text']}" for h in list(history)[-MAX_HISTORY:]]
    if lang in LANG_NAMES:
        lines.append(f"Interface language: {LANG_NAMES[lang]} (answer in the language of the question).")
    lines.append(f"Question: {question}")
    try:
        out = complete_json("chat_general", "\n".join(lines), _LlmGeneral)
    except LLMUnavailable:
        return {"answer": GENERAL_OFFLINE, "citations": [], "source": "rules"}
    return {"answer": out.answer.strip() or GENERAL_OFFLINE, "citations": [], "source": "llm"}
