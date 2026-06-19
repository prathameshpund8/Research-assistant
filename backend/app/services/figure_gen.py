"""Render simple, publication-style diagrams to PNG (base64).

Used by the Figures agent to turn a small LLM-provided spec into an actual
figure embedded in the paper. Two layouts are supported:
  - "flow": labelled boxes left-to-right joined by arrows (process/method flow);
  - "concept": a central concept with surrounding related boxes.
Uses the non-interactive Agg backend so it runs headless on a server.
"""

from __future__ import annotations

import base64
import io
import logging
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

logger = logging.getLogger(__name__)

_BOX = dict(boxstyle="round,pad=0.5", facecolor="#eef2ff", edgecolor="#4f46e5", linewidth=1.5)
_FONT = 9


def _wrap(label: str, width: int = 16) -> str:
    return "\n".join(textwrap.wrap(label, width)) or label


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def render_flow(nodes: list[str]) -> str:
    """Left-to-right boxes joined by arrows."""
    nodes = [n for n in nodes if n][:6] or ["Input", "Process", "Output"]
    n = len(nodes)
    fig, ax = plt.subplots(figsize=(min(2.0 * n, 10), 2.2))
    ax.set_xlim(0, n)
    ax.set_ylim(0, 1)
    ax.axis("off")
    centers = []
    for i, label in enumerate(nodes):
        cx = i + 0.5
        centers.append(cx)
        box = FancyBboxPatch(
            (cx - 0.42, 0.35), 0.84, 0.32, boxstyle="round,pad=0.02",
            facecolor="#eef2ff", edgecolor="#4f46e5", linewidth=1.5,
        )
        ax.add_patch(box)
        ax.text(cx, 0.51, _wrap(label, 14), ha="center", va="center", fontsize=_FONT)
    for i in range(n - 1):
        ax.add_patch(
            FancyArrowPatch(
                (centers[i] + 0.42, 0.51), (centers[i + 1] - 0.42, 0.51),
                arrowstyle="-|>", mutation_scale=14, color="#475569", linewidth=1.3,
            )
        )
    return _fig_to_b64(fig)


def render_concept(center: str, nodes: list[str]) -> str:
    """A central concept surrounded by related boxes."""
    import math

    nodes = [n for n in nodes if n][:6] or ["Aspect A", "Aspect B", "Aspect C"]
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.set_xlim(-1.6, 1.6)
    ax.set_ylim(-1.6, 1.6)
    ax.axis("off")
    ax.text(0, 0, _wrap(center, 14), ha="center", va="center", fontsize=_FONT + 1,
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#4f46e5", edgecolor="#4f46e5"),
            color="white", weight="bold")
    k = len(nodes)
    for i, label in enumerate(nodes):
        ang = 2 * math.pi * i / k + math.pi / 2
        x, y = 1.15 * math.cos(ang), 1.15 * math.sin(ang)
        ax.annotate("", xy=(x * 0.62, y * 0.62), xytext=(0, 0),
                    arrowprops=dict(arrowstyle="-", color="#94a3b8", linewidth=1.2))
        ax.text(x, y, _wrap(label, 12), ha="center", va="center", fontsize=_FONT, bbox=_BOX)
    return _fig_to_b64(fig)


def render_spec(spec: dict) -> str:
    """Render a figure from an LLM spec; never raises (returns '' on failure)."""
    try:
        kind = (spec.get("kind") or "flow").lower()
        nodes = [str(x) for x in spec.get("nodes", []) if str(x).strip()]
        if kind == "concept":
            return render_concept(spec.get("center", "Topic"), nodes)
        return render_flow(nodes)
    except Exception:
        logger.exception("Figure rendering failed.")
        return ""
