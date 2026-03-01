#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lancedb>=0.5.0",
#     "sentence-transformers>=2.2.0",
#     "pyarrow>=14.0.0",
#     "pandas>=2.0.0",
#     "networkx>=3.0",
#     "requests>=2.31.0",
# ]
# ///
"""
Fast PINCH memory query - uses embedding server when available.
Usage: uv run query_fast.py "search query" [--limit N] [--max-chars 200]
"""

import argparse
import json
import sys
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

EMBEDDING_SERVER = "http://127.0.0.1:5111"

def get_embedding_fast(text: str) -> list[float] | None:
    """Get embedding from server (fast) or fall back to local loading."""
    try:
        resp = requests.post(f"{EMBEDDING_SERVER}/embed", 
                           json={"text": text}, timeout=5)
        if resp.status_code == 200:
            return resp.json()["embedding"]
    except:
        pass
    
    # Fallback to local
    try:
        from local_llm import get_embedding
        return get_embedding(text)
    except:
        return None

def query_memories(query: str, limit: int = 3, max_chars: int = 200) -> list[dict]:
    """Query memories with cost-optimized settings."""
    from memory_graph import recall, get_strength
    
    results = recall(query, n=limit * 2)
    
    formatted = []
    for mem in results[:limit]:
        strength_data = get_strength(mem.get("id", ""))
        strength = strength_data.get("strength", 0.5) if strength_data else 0.5
        
        content = mem.get("content", "")
        if len(content) > max_chars:
            content = content[:max_chars] + "..."
        
        formatted.append({
            "category": mem.get("category", "episodic"),
            "strength": round(strength, 2),
            "content": content,
        })
    
    return formatted

def format_for_context(memories: list[dict]) -> str:
    """Format memories compactly for context injection."""
    if not memories:
        return ""
    
    lines = []
    for mem in memories:
        cat = mem["category"]
        content = mem["content"].replace("\n", " ").strip()
        lines.append(f"- [{cat}] {content}")
    
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Fast PINCH memory query")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--limit", "-n", type=int, default=3, help="Max results (default: 3)")
    parser.add_argument("--max-chars", "-c", type=int, default=200, help="Max chars per memory")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument("--context", action="store_true", help="Output for context injection")
    
    args = parser.parse_args()
    
    # Skip very short queries
    if len(args.query.strip()) < 10:
        if args.json:
            print("[]")
        return
    
    results = query_memories(args.query, args.limit, args.max_chars)
    
    if args.json:
        print(json.dumps(results, indent=2))
    elif args.context:
        formatted = format_for_context(results)
        if formatted:
            print("## Relevant Memories\n")
            print(formatted)
    else:
        if not results:
            print("No relevant memories.")
            return
        for i, mem in enumerate(results, 1):
            print(f"{i}. [{mem['category']}] {mem['content'][:100]}...")

if __name__ == "__main__":
    main()
