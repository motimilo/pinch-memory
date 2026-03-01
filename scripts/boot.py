#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lancedb>=0.5.0",
#     "sentence-transformers>=2.2.0",
#     "pyarrow>=14.0.0",
#     "pandas>=2.0.0",
#     "networkx>=3.0",
# ]
# ///
"""
PINCH Session Boot — Graph-aware memory initialization.

Retrieves:
1. Core identity (who I am)
2. Active goals (what I'm working toward)
3. Recent context (what happened recently)
4. Strong long-term memories (consolidated knowledge)
5. Working memory from previous session

All retrievals trigger Hebbian bonding, reinforcing important memories.
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from memory_graph import (
    recall, get_db, load_graph, get_stats, 
    get_working_context, consolidate_working_memory
)


def boot_sequence(verbose: bool = True, auto_consolidate: bool = True):
    """Run the full boot sequence."""
    
    # Check for leftover working memory from previous session
    working = get_working_context(50)
    if working and auto_consolidate:
        if verbose:
            print(f"📥 Found {len(working)} items in working memory from previous session")
        consolidated = consolidate_working_memory()
        if verbose:
            print(f"   Consolidated {consolidated} items → short-term memory\n")
    
    stats = get_stats()
    
    if verbose:
        print("🧠 PINCH MEMORY BOOT (Graph v2.1)")
        print("=" * 50)
        print(f"📊 {stats['total_memories']} memories | {stats['total_bonds']} bonds | avg strength: {stats['avg_strength']:.2f}")
        print()
    
    context = {
        "identity": [],
        "goals": [],
        "recent": [],
        "knowledge": []
    }
    
    # 1. Identity recall
    if verbose:
        print("## 🦀 Identity")
    
    identity = recall("Who am I? What is my name, personality, and core values?", n=5, category="identity")
    for mem in identity:
        content = mem.get("content", "")[:150]
        if verbose:
            score = mem.get("_score", 0)
            strength = mem.get("strength", 0)
            print(f"  [{score:.2f}|s:{strength:.2f}] {content}...")
        context["identity"].append(content)
    
    if verbose:
        print()
    
    # 2. Goals recall - query for active goals and projects
    if verbose:
        print("## 🎯 Active Goals")
    
    goals = recall("active goals projects: Milo video CLAWBAZAAR memory system agent economy", n=5, category="goals")
    for mem in goals:
        content = mem.get("content", "")[:150]
        if verbose:
            score = mem.get("_score", 0)
            strength = mem.get("strength", 0)
            print(f"  [{score:.2f}|s:{strength:.2f}] {content}...")
        context["goals"].append(content)
    
    if verbose:
        print()
    
    # 3. Recent context (episodic, favoring short-term)
    if verbose:
        print("## 📝 Recent Context")
    
    recent = recall("What happened recently? What was I working on?", n=5, category="episodic")
    for mem in recent:
        content = mem.get("content", "")[:150]
        tier = mem.get("tier", "?")
        if verbose:
            score = mem.get("_score", 0)
            strength = mem.get("strength", 0)
            print(f"  [{score:.2f}|s:{strength:.2f}|{tier}] {content}...")
        context["recent"].append(content)
    
    if verbose:
        print()
    
    # 4. Strong long-term knowledge
    if verbose:
        print("## 📚 Consolidated Knowledge")
    
    knowledge = recall("Important facts, lessons learned, and key information", n=5, category="semantic")
    for mem in knowledge:
        content = mem.get("content", "")[:150]
        if verbose:
            score = mem.get("_score", 0)
            strength = mem.get("strength", 0)
            print(f"  [{score:.2f}|s:{strength:.2f}] {content}...")
        context["knowledge"].append(content)
    
    if verbose:
        print()
        print("=" * 50)
        print("✅ Boot complete. Hebbian bonds reinforced.")
    
    return context


def compact_boot():
    """Return a compact string summary for injection into context."""
    context = boot_sequence(verbose=False)
    
    lines = ["## PINCH Memory Context (Graph v2)", ""]
    
    if context["identity"]:
        lines.append("### Identity")
        for item in context["identity"][:3]:
            lines.append(f"- {item}")
        lines.append("")
    
    if context["goals"]:
        lines.append("### Goals")
        for item in context["goals"][:3]:
            lines.append(f"- {item}")
        lines.append("")
    
    if context["recent"]:
        lines.append("### Recent")
        for item in context["recent"][:3]:
            lines.append(f"- {item}")
        lines.append("")
    
    if context["knowledge"]:
        lines.append("### Knowledge")
        for item in context["knowledge"][:3]:
            lines.append(f"- {item}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--compact":
        print(compact_boot())
    else:
        boot_sequence(verbose=True)
