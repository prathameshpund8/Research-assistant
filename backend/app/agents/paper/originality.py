"""Originality agent — built-in similarity check against the retrieved sources.

This is NOT a certified plagiarism scan (no Turnitin/iThenticate). It measures
how much of each section's wording overlaps the *actual source text we
retrieved*, using word n-gram (shingle) overlap. Passages that are too close to
a source are rewritten by the LLM to be original while keeping the citation, and
an overall originality score (0-100) is reported.
"""

from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents._util import emit
from app.agents.state import ResearchState
from app.services.llm import get_llm

logger = logging.getLogger(__name__)

# === EDITABLE PROMPT =======================================================
REWRITE_SYSTEM_PROMPT = """You rewrite a passage of an academic paper in your own
words to remove close paraphrasing of a source, while preserving the meaning and
any [S#] citations exactly. Return only the rewritten passage."""
# ===========================================================================

_NGRAM = 6  # shingle size (words)
_FLAG_THRESHOLD = 0.35  # fraction of a sentence's shingles seen in a source
_WORD = re.compile(r"\w+")
_CITE = re.compile(r"\[(S\d+)\]")


def _shingles(text: str, n: int = _NGRAM) -> set[str]:
    words = [w.lower() for w in _WORD.findall(text)]
    return {" ".join(words[i : i + n]) for i in range(max(0, len(words) - n + 1))}


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def originality_node(state: ResearchState) -> dict:
    sections = state.get("sections", [])
    sources = {s["id"]: s for s in state.get("sources", [])}

    emit(state, "summarizer", "started", "Checking originality against retrieved sources.")

    # Pre-compute shingle sets per source snippet.
    source_shingles = {sid: _shingles(src.get("snippet", "")) for sid, src in sources.items()}

    try:
        llm = get_llm(temperature=0.5)
        llm_ok = True
    except Exception:
        llm = None
        llm_ok = False

    flagged: list[dict] = []
    rewritten = 0
    total_sentences = 0
    overlapping_sentences = 0
    out_sections: list[dict] = []

    for sec in sections:
        sentences = _split_sentences(sec["body"])
        new_sentences: list[str] = []
        for sent in sentences:
            total_sentences += 1
            sh = _shingles(sent)
            if not sh:
                new_sentences.append(sent)
                continue
            # Compare against the sources this sentence cites (or all if none).
            cited = _CITE.findall(sent) or list(sources.keys())
            best_sid, best_sim = "", 0.0
            for sid in cited:
                ss = source_shingles.get(sid)
                if not ss:
                    continue
                sim = len(sh & ss) / max(1, len(sh))
                if sim > best_sim:
                    best_sim, best_sid = sim, sid

            if best_sim >= _FLAG_THRESHOLD:
                overlapping_sentences += 1
                flagged.append(
                    {
                        "section": sec["heading"],
                        "passage": sent[:200],
                        "source_id": best_sid,
                        "similarity": round(best_sim, 2),
                    }
                )
                sent = _rewrite(llm, sent) if llm_ok else sent
                if llm_ok:
                    rewritten += 1
            new_sentences.append(sent)
        out_sections.append({"heading": sec["heading"], "body": " ".join(new_sentences)})

    score = 100.0 if total_sentences == 0 else round(
        100.0 * (1.0 - overlapping_sentences / total_sentences), 1
    )
    # If we rewrote the flagged passages, reflect the improved originality.
    if rewritten:
        score = min(100.0, score + round(60.0 * rewritten / max(1, total_sentences), 1))

    originality = {
        "score": score,
        "flagged": flagged,
        "rewritten": rewritten,
        "method": "n-gram overlap vs. retrieved source text",
    }
    emit(
        state,
        "summarizer",
        "completed",
        f"Originality {score}% — flagged {len(flagged)} passage(s), rewrote {rewritten}.",
        score=score,
        flagged=len(flagged),
        rewritten=rewritten,
    )
    return {"sections": out_sections, "originality": originality}


def _rewrite(llm, sentence: str) -> str:
    try:
        msgs = [
            SystemMessage(content=REWRITE_SYSTEM_PROMPT),
            HumanMessage(content=sentence),
        ]
        out = llm.invoke(msgs).content.strip()
        # Keep any citations even if the model dropped them.
        for sid in _CITE.findall(sentence):
            if f"[{sid}]" not in out:
                out = f"{out} [{sid}]"
        return out or sentence
    except Exception:
        logger.exception("Originality rewrite failed; keeping original sentence.")
        return sentence
