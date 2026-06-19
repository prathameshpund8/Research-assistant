"""LangGraph assembly for the IEEE paper pipeline.

    outliner -> searcher -> summarizer -> critic --(gaps & rounds left)--> searcher
                                              \\--(done)--> section_writer
        -> verifier -> originality -> references -> assembler -> END

The research front-half (searcher/summarizer/critic + bounded re-search loop) is
reused from the report pipeline; the back-half adds the paper-specific agents.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from app.agents.critic import critic_node
from app.agents.searcher import searcher_node
from app.agents.state import ResearchState
from app.agents.summarizer import summarizer_node
from app.agents.paper.assembler import assembler_node
from app.agents.paper.originality import originality_node
from app.agents.paper.outliner import outliner_node
from app.agents.paper.references import references_node
from app.agents.paper.section_writer import section_writer_node
from app.agents.paper.verifier import verifier_node

logger = logging.getLogger(__name__)


def _should_continue(state: ResearchState) -> str:
    """After the Critic: re-search to fill gaps, or start writing the paper."""
    return "searcher" if state.get("should_research_more") else "section_writer"


def build_paper_graph():
    g = StateGraph(ResearchState)

    g.add_node("outliner", outliner_node)
    g.add_node("searcher", searcher_node)
    g.add_node("summarizer", summarizer_node)
    g.add_node("critic", critic_node)
    g.add_node("section_writer", section_writer_node)
    g.add_node("verifier", verifier_node)
    g.add_node("originality_check", originality_node)
    g.add_node("reference_builder", references_node)
    g.add_node("assembler", assembler_node)

    g.set_entry_point("outliner")
    g.add_edge("outliner", "searcher")
    g.add_edge("searcher", "summarizer")
    g.add_edge("summarizer", "critic")
    g.add_conditional_edges(
        "critic",
        _should_continue,
        {"searcher": "searcher", "section_writer": "section_writer"},
    )
    g.add_edge("section_writer", "verifier")
    g.add_edge("verifier", "originality_check")
    g.add_edge("originality_check", "reference_builder")
    g.add_edge("reference_builder", "assembler")
    g.add_edge("assembler", END)

    compiled = g.compile()
    logger.info("Paper graph compiled.")
    return compiled


paper_graph = build_paper_graph()
