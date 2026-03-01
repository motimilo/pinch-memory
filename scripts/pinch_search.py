#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lancedb>=0.5.0",
#     "sentence-transformers>=2.2.0",
#     "pyarrow>=14.0.0",
# ]
# ///
"""
PINCH Search Tool — Explicit memory search for agent use.

Use this tool when you need to:
- Recall past decisions, conversations, or context
- Look up how something was done before
- Find relevant information from previous sessions
- Check if something was already discussed/decided

Usage:
    uv run pinch_search.py "what do I know about CLAWBAZAAR?"
    uv run pinch_search.py --type episodic "recent conversations"
    uv run pinch_search.py --limit 10 "milo trading"
    
Returns relevant memories ranked by similarity + strength.
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Setup paths
MEMORY_DIR = Path(__file__).parent.parent
LANCE_DB_PATH = MEMORY_DIR / "lance_db_v2"  # Same as memory_graph.py

# Lazy load heavy imports
_model = None
_db = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer('all-MiniLM-L6-v2')
    return _model


def get_db():
    global _db
    if _db is None:
        import lancedb
        _db = lancedb.connect(str(LANCE_DB_PATH))
    return _db


def search_memories(
    query: str,
    limit: int = 5,
    mem_type: str = None,
    min_strength: float = 0.3,
    max_age_days: int = None
) -> list[dict]:
    """
    Search PINCH memory for relevant information.
    
    Args:
        query: What to search for (natural language)
        limit: Maximum results to return
        mem_type: Filter by type (episodic, semantic, procedural, identity, goals)
        min_strength: Minimum memory strength (0-1)
        max_age_days: Only return memories newer than N days
        
    Returns:
        List of relevant memories with content, metadata, and scores
    """
    db = get_db()
    model = get_model()
    
    # Check if table exists
    try:
        tables = db.table_names() if hasattr(db, 'table_names') else list(db)
    except:
        tables = []
    
    if "memories" not in tables:
        return []
    
    table = db.open_table("memories")
    
    # Generate query embedding
    query_vec = model.encode(query).tolist()
    
    # Search
    results = table.search(query_vec).limit(limit * 3).to_list()  # Get extra for filtering
    
    # Filter and enhance results
    filtered = []
    now = datetime.now().timestamp()
    
    for r in results:
        # Type filter
        if mem_type and r.get("type") != mem_type:
            continue
            
        # Strength filter (default 1.0 if not set)
        strength = r.get("strength", 1.0)
        if strength < min_strength:
            continue
            
        # Age filter
        if max_age_days:
            created = r.get("created_at", 0)
            if isinstance(created, str):
                try:
                    created = datetime.fromisoformat(created).timestamp()
                except:
                    created = 0
            age_days = (now - created) / 86400
            if age_days > max_age_days:
                continue
        
        # Calculate combined score (similarity * strength)
        similarity = 1 - r.get("_distance", 0)
        combined_score = similarity * strength
        
        filtered.append({
            "content": r.get("content", ""),
            "type": r.get("type", "unknown"),
            "score": round(combined_score, 3),
            "similarity": round(similarity, 3),
            "strength": round(strength, 3),
            "tags": r.get("tags", []),
            "created": r.get("created_at", ""),
            "id": r.get("id", ""),
        })
    
    # Sort by combined score and limit
    filtered.sort(key=lambda x: x["score"], reverse=True)
    return filtered[:limit]


def format_results(results: list[dict], verbose: bool = False) -> str:
    """Format search results for display."""
    if not results:
        return "No relevant memories found."
    
    lines = [f"Found {len(results)} relevant memories:\n"]
    
    for i, r in enumerate(results, 1):
        content = r["content"]
        if len(content) > 200 and not verbose:
            content = content[:200] + "..."
        
        lines.append(f"[{i}] ({r['type']}) score={r['score']}")
        if r.get("tags"):
            lines.append(f"    Tags: {', '.join(r['tags'])}")
        lines.append(f"    {content}")
        lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Search PINCH memory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  pinch_search.py "CLAWBAZAAR contracts"
  pinch_search.py --type episodic "recent conversations"
  pinch_search.py --limit 10 --verbose "milo trading agent"
  pinch_search.py --json "outreach radar"
        """
    )
    parser.add_argument("query", help="What to search for")
    parser.add_argument("--limit", "-n", type=int, default=5, help="Max results (default: 5)")
    parser.add_argument("--type", "-t", choices=["episodic", "semantic", "procedural", "identity", "goals"],
                        help="Filter by memory type")
    parser.add_argument("--min-strength", type=float, default=0.3, help="Min strength 0-1 (default: 0.3)")
    parser.add_argument("--max-age", type=int, help="Max age in days")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show full content")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    results = search_memories(
        query=args.query,
        limit=args.limit,
        mem_type=args.type,
        min_strength=args.min_strength,
        max_age_days=args.max_age
    )
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(format_results(results, verbose=args.verbose))


if __name__ == "__main__":
    main()
