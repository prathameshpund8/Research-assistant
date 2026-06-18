"""LangGraph assembly.

Wires the five agents into a state machine::

    planner -> searcher -> summarizer -> critic --(gaps & rounds left)--> searcher
                                              \\--(done)--> writer -> END

The conditional edge after the Critic implements the bounded re-search loop.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from app.agents.critic import critic_node
from app.agents.planner import planner_node
from app.agents.searcher import searcher_node
from app.agents.state import ResearchState
from app.agents.summarizer import summarizer_node
from app.agents.writer import writer_node

logger = logging.getLogger(__name__)


def should_continue(state: ResearchState) -> str:
    """Conditional router after the Critic.

    Returns the name of the next node: loop back to "searcher" to fill gaps,
    or move on to "writer". All termination guarantees live in the Critic,
    which sets ``should_research_more`` honouring the round cap and the
    no-new-sources rule.
    """
    return "searcher" if state.get("should_research_more") else "writer"


def build_graph():
    """Construct and compile the research LangGraph."""
    graph = StateGraph(ResearchState)

    graph.add_node("planner", planner_node)
    graph.add_node("searcher", searcher_node)
    graph.add_node("summarizer", summarizer_node)
    graph.add_node("critic", critic_node)
    graph.add_node("writer", writer_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "searcher")
    graph.add_edge("searcher", "summarizer")
    graph.add_edge("summarizer", "critic")
    graph.add_conditional_edges(
        "critic",
        should_continue,
        {"searcher": "searcher", "writer": "writer"},
    )
    graph.add_edge("writer", END)

    compiled = graph.compile()
    logger.info("Research graph compiled.")
    return compiled


# Compile once at import time and reuse across requests.
research_graph = build_graph()
