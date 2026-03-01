#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lancedb>=0.5.0",
#     "sentence-transformers>=2.2.0",
#     "pyarrow>=14.0.0",
#     "pandas>=2.0.0",
# ]
# ///
"""
PINCH Recall — Quick semantic memory queries for session boot.

Usage:
  pinch_recall.py boot              # Full boot sequence
  pinch_recall.py query "question"  # General query across all collections
  pinch_recall.py remember "fact"   # Quick add to semantic memory
  pinch_recall.py episode "event"   # Quick add to episodic memory
  pinch_recall.py goal "intention"  # Quick add to goals
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from memory_store import (
    query_all, query_memory, add_memory,
    recall_identity, recall_active_goals, recall_recent_context,
    get_collection_stats
)


def boot_sequence():
    """Full memory boot for session start."""
    print("🧠 PINCH MEMORY BOOT\n")
    
    stats = get_collection_stats()
    total = sum(stats.values())
    print(f"📊 {total} total memories across {len([s for s in stats.values() if s > 0])} collections\n")
    
    # Identity
    print("## 🦀 Identity")
    try:
        identity = recall_identity()
        if identity["documents"]:
            for doc in identity["documents"][:5]:
                summary = doc[:150] + "..." if len(doc) > 150 else doc
                print(f"  • {summary}")
            print()
    except Exception as e:
        print(f"  (no identity memories yet: {e})\n")
    
    # Goals
    print("## 🎯 Active Goals")
    try:
        goals = recall_active_goals()
        if goals["documents"]:
            for doc in goals["documents"][:5]:
                summary = doc[:150] + "..." if len(doc) > 150 else doc
                print(f"  • {summary}")
            print()
    except Exception as e:
        print(f"  (no goals yet: {e})\n")
    
    # Recent context
    print("## 📝 Recent Context")
    try:
        recent = recall_recent_context("What happened recently? What was I working on?")
        if recent["documents"]:
            for doc in recent["documents"][:3]:
                summary = doc[:150] + "..." if len(doc) > 150 else doc
                print(f"  • {summary}")
            print()
    except Exception as e:
        print(f"  (no recent context: {e})\n")


def general_query(query: str, n: int = 5):
    """Query all collections."""
    results = query_all(query, n)
    
    if not results:
        print("No relevant memories found.")
        return
    
    print(f"🔍 Query: {query}\n")
    
    for collection, data in results.items():
        if data["documents"]:
            print(f"## {collection.upper()}")
            for i, (doc, meta, dist) in enumerate(zip(
                data["documents"], 
                data["metadatas"], 
                data["distances"]
            )):
                relevance = max(0, 100 - int(dist * 50))  # Convert distance to relevance %
                summary = doc[:200] + "..." if len(doc) > 200 else doc
                print(f"  [{relevance}%] {summary}")
            print()


def quick_add(collection: str, content: str):
    """Quick add to a collection."""
    mem_id = add_memory(collection, content, {"source": "quick_add"})
    print(f"✓ Added to {collection}: {content[:60]}...")
    print(f"  ID: {mem_id}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "boot":
        boot_sequence()
    
    elif cmd == "query":
        if len(sys.argv) < 3:
            print("Usage: pinch_recall.py query \"your question\"")
            sys.exit(1)
        query = " ".join(sys.argv[2:])
        general_query(query)
    
    elif cmd == "remember":
        if len(sys.argv) < 3:
            print("Usage: pinch_recall.py remember \"fact to remember\"")
            sys.exit(1)
        content = " ".join(sys.argv[2:])
        quick_add("semantic", content)
    
    elif cmd == "episode":
        if len(sys.argv) < 3:
            print("Usage: pinch_recall.py episode \"event that happened\"")
            sys.exit(1)
        content = " ".join(sys.argv[2:])
        quick_add("episodic", content)
    
    elif cmd == "goal":
        if len(sys.argv) < 3:
            print("Usage: pinch_recall.py goal \"goal or intention\"")
            sys.exit(1)
        content = " ".join(sys.argv[2:])
        quick_add("goals", content)
    
    elif cmd == "stats":
        stats = get_collection_stats()
        print("📊 Memory Stats:")
        for name, count in stats.items():
            bar = "█" * min(count // 5, 20)
            print(f"  {name:12} {count:4} {bar}")
    
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
