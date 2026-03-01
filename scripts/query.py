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
Query PINCH memory graph for semantically similar memories.
Usage: uv run query.py "search query" [--limit N] [--threshold 0.5]

Returns JSON array of relevant memories for injection into agent context.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from memory_graph import recall, get_strength


def query_memories(query: str, limit: int = 5, min_strength: float = 0.3) -> list[dict]:
    """Query memories using PINCH recall with bond-aware retrieval."""
    
    # Use built-in recall function which does semantic search + bond traversal
    results = recall(query, n=limit * 2)  # Get more, filter by strength
    
    formatted = []
    for mem in results:
        strength_data = get_strength(mem.get("id", ""))
        strength = strength_data.get("strength", 0.5) if strength_data else 0.5
        
        if strength >= min_strength:
            formatted.append({
                "id": mem.get("id", ""),
                "content": mem.get("content", ""),
                "category": mem.get("category", "episodic"),
                "tier": strength_data.get("tier", "short") if strength_data else "short",
                "strength": round(strength, 3),
                "created": mem.get("created_at", ""),
            })
    
    # Sort by strength, return top N
    formatted.sort(key=lambda x: x["strength"], reverse=True)
    return formatted[:limit]


def format_for_context(memories: list[dict]) -> str:
    """Format memories for injection into agent context."""
    if not memories:
        return ""
    
    lines = ["## Relevant Memories (auto-retrieved)", ""]
    for mem in memories:
        cat = mem["category"]
        strength = mem["strength"]
        content = mem["content"]
        lines.append(f"- **[{cat}]** (strength: {strength}): {content}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Query PINCH memory graph")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--limit", "-n", type=int, default=5, help="Max results")
    parser.add_argument("--min-strength", "-s", type=float, default=0.3, help="Min strength threshold")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument("--context", "-c", action="store_true", help="Output formatted for context injection")
    
    args = parser.parse_args()
    
    results = query_memories(args.query, args.limit, args.min_strength)
    
    if args.json:
        print(json.dumps(results, indent=2))
    elif args.context:
        print(format_for_context(results))
    else:
        if not results:
            print("No relevant memories found.")
            return
        
        print(f"Found {len(results)} relevant memories:\n")
        for i, mem in enumerate(results, 1):
            print(f"{i}. [{mem['category']}] (strength: {mem['strength']})")
            content = mem['content']
            if len(content) > 200:
                content = content[:200] + "..."
            print(f"   {content}")
            print()


if __name__ == "__main__":
    main()
