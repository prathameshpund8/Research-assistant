"""Plagiarism agent — explicit similarity check + paraphrasing.

For every sentence it measures word n-gram (shingle) overlap against the actual
retrieved source text. Sentences above the threshold are paraphrased by the LLM
(citations preserved), then re-measured to confirm the overlap dropped. Reports
both the pre- and post-paraphrase originality scores.

This is a built-in similarity check against the sources we retrieved — NOT a
certified Turnitin/iThenticate scan against the whole web.
"""

from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents._util import emit
from app.agents.state import ResearchState
from app.services.llm import get_fast_llm

logger = logging.getLogger(__name__)

# === EDITABLE PROMPT =======================================================
PARAPHRASE_SYSTEM_PROMPT = """You rewrite a sentence from an academic paper in
your own words to eliminate close paraphrasing of a source, while preserving the
exact meaning and any [n] citation markers. Use different sentence structure and
vocabulary. Return only the rewritten sentence, nothing else."""
# ===========================================================================

_NGRAM = 5
_FLAG = 0.30  # fraction of a sentence's shingles found in a source -> flag
_WORD = re.compile(r"\w+")
_CITE = re.compile(r"\[(\d+|S\d+)\]")


def _shingles(text: str, n: int = _NGRAM) -> set[str]:
    words = [w.lower() for w in _WORD.findall(text)]
    return {" ".join(words[i : i + n]) for i in range(max(0, len(words) - n + 1))}


def _paragraphs(text: str) -> list[str]:
    """Split a section body into paragraphs (preserving subsection lines)."""
    return [p.strip() for p in re.split(r"\n+", text) if p.strip()]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _max_overlap(sentence: str, source_shingles: list[set[str]]) -> float:
    sh = _shingles(sentence)
    if not sh:
        return 0.0
    return max((len(sh & ss) / len(sh) for ss in source_shingles if ss), default=0.0)


def plagiarism_node(state: ResearchState) -> dict:
    sections = state.get("sections", [])
    sources = state.get("sources", [])
    source_shingles = [_shingles(s.get("snippet", "")) for s in sources if s.get("snippet")]

    emit(state, "summarizer", "started", "Plagiarism check: measuring source overlap.")

    try:
        llm = get_fast_llm(temperature=0.6)
        llm_ok = True
    except Exception:
        llm, llm_ok = None, False

    flagged: list[dict] = []
    total = 0
    pre_over = 0
    post_over = 0
    rewritten = 0
    out_sections: list[dict] = []

    for sec in sections:
        # Process paragraph-by-paragraph so paragraph breaks (and any "**A.
        # Subsection**" lines) are preserved — flattening them would collapse a
        # multi-paragraph section into a single block.
        new_paragraphs: list[str] = []
        for para in _paragraphs(sec["body"]):
            new_sents: list[str] = []
            for sent in _sentences(para):
                total += 1
                sim = _max_overlap(sent, source_shingles)
                if sim >= _FLAG:
                    pre_over += 1
                    flagged.append(
                        {
                            "section": sec["heading"],
                            "passage": sent[:200],
                            "source_id": "",
                            "similarity": round(sim, 2),
                        }
                    )
                    if llm_ok:
                        new = _paraphrase(llm, sent)
                        rewritten += 1
                        if _max_overlap(new, source_shingles) >= _FLAG:
                            post_over += 1
                        sent = new
                    else:
                        post_over += 1
                new_sents.append(sent)
            new_paragraphs.append(" ".join(new_sents))
        out_sections.append({"heading": sec["heading"], "body": "\n\n".join(new_paragraphs)})

    pre_score = 100.0 if total == 0 else round(100.0 * (1 - pre_over / total), 1)
    post_score = 100.0 if total == 0 else round(100.0 * (1 - post_over / total), 1)

    report = {
        "score": post_score,
        "pre_score": pre_score,
        "flagged": flagged,
        "rewritten": rewritten,
        "still_flagged": post_over,
        "method": "n-gram overlap vs. retrieved source text + LLM paraphrase",
    }
    emit(
        state,
        "summarizer",
        "completed",
        f"Plagiarism check: {pre_score}% → {post_score}% original after paraphrasing "
        f"{rewritten} passage(s); {post_over} still flagged.",
        score=post_score,
        pre_score=pre_score,
        rewritten=rewritten,
    )
    return {"sections": out_sections, "originality": report}


def _paraphrase(llm, sentence: str) -> str:
    try:
        msgs = [
            SystemMessage(content=PARAPHRASE_SYSTEM_PROMPT),
            HumanMessage(content=sentence),
        ]
        out = llm.invoke(msgs).content.strip()
        for cite in _CITE.findall(sentence):
            if f"[{cite}]" not in out:
                out = f"{out} [{cite}]"
        return out or sentence
    except Exception:
        logger.exception("Paraphrase failed; keeping original sentence.")
        return sentence
