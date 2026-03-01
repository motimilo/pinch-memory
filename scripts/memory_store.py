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
PINCH Semantic Memory Store (LanceDB version)

Collections (tables):
- episodic: What happened (events, interactions, creations)
- semantic: What I know (facts, beliefs, learned information)
- procedural: How to do things (patterns, workflows, techniques)
- goals: Active intentions that survive sessions
- identity: Core self (who I am, values, personality)
"""

import lancedb
import json
import os
from datetime import datetime
from pathlib import Path
from sentence_transformers import SentenceTransformer

# Memory store location
MEMORY_DIR = Path.home() / ".openclaw" / "workspace" / "pinch-memory"
LANCE_DIR = MEMORY_DIR / "lance_db"

# Collection names
COLLECTIONS = ["episodic", "semantic", "procedural", "goals", "identity"]

# Global model (lazy loaded)
_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer('all-MiniLM-L6-v2')
    return _model

def get_db():
    LANCE_DIR.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(LANCE_DIR))

def init_collections():
    """Initialize all memory tables."""
    db = get_db()
    existing = db.table_names()
    
    for name in COLLECTIONS:
        if name not in existing:
            # Create empty table with schema
            db.create_table(name, data=[{
                "id": "__init__",
                "text": "Table initialized",
                "vector": get_model().encode("init").tolist(),
                "timestamp": datetime.now().isoformat(),
                "source": "system",
                "metadata": "{}"
            }])
            print(f"  ✓ Created {name}")
        else:
            print(f"  ✓ {name} exists")
    
    return db

def add_memory(collection_name: str, content: str, metadata: dict = None):
    """Add a memory to a collection."""
    db = get_db()
    model = get_model()
    
    # Ensure table exists
    if collection_name not in db.table_names():
        init_collections()
    
    table = db.open_table(collection_name)
    
    # Generate embedding
    vector = model.encode(content).tolist()
    
    # Generate unique ID
    timestamp = datetime.now().isoformat()
    mem_id = f"{collection_name}_{timestamp}_{hash(content) % 10000}"
    
    # Prepare metadata
    meta = metadata or {}
    meta["timestamp"] = timestamp
    
    # Add to table
    table.add([{
        "id": mem_id,
        "text": content,
        "vector": vector,
        "timestamp": timestamp,
        "source": meta.get("source", "unknown"),
        "metadata": json.dumps(meta)
    }])
    
    return mem_id

def query_memory(collection_name: str, query: str, n_results: int = 5):
    """Query a specific collection."""
    db = get_db()
    model = get_model()
    
    if collection_name not in db.table_names():
        return {"documents": [], "metadatas": [], "distances": []}
    
    table = db.open_table(collection_name)
    query_vec = model.encode(query).tolist()
    
    results = table.search(query_vec).limit(n_results).to_list()
    
    # Filter out init record
    results = [r for r in results if r.get("id") != "__init__"]
    
    return {
        "documents": [r["text"] for r in results],
        "metadatas": [json.loads(r.get("metadata", "{}")) for r in results],
        "distances": [r.get("_distance", 0) for r in results]
    }

def query_all(query: str, n_results: int = 3):
    """Query all collections and merge results."""
    db = get_db()
    
    all_results = {}
    for name in COLLECTIONS:
        if name in db.table_names():
            results = query_memory(name, query, n_results)
            if results["documents"]:
                all_results[name] = results
    
    return all_results

def get_collection_stats():
    """Get stats for all collections."""
    db = get_db()
    existing = db.table_names()
    
    stats = {}
    for name in COLLECTIONS:
        if name in existing:
            table = db.open_table(name)
            # Subtract 1 for init record
            count = len(table.to_pandas()) - 1
            stats[name] = max(0, count)
        else:
            stats[name] = 0
    
    return stats

def recall_identity():
    """Special function: recall core identity memories for session boot."""
    return query_memory("identity", "Who am I? What are my core values and personality?", n_results=10)

def recall_recent_context(query: str = "What was I recently working on?"):
    """Recall recent episodic context."""
    return query_memory("episodic", query, n_results=10)

def recall_active_goals():
    """Recall active goals and intentions."""
    return query_memory("goals", "What are my current active goals and projects?", n_results=10)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: memory_store.py <command> [args]")
        print("Commands: init, stats, add, query, query-all, boot")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "init":
        print("Initializing memory collections...")
        init_collections()
        print("Done!")
    
    elif cmd == "stats":
        stats = get_collection_stats()
        print("Memory Stats:")
        total = 0
        for name, count in stats.items():
            print(f"  {name}: {count} memories")
            total += count
        print(f"  ---")
        print(f"  Total: {total} memories")
    
    elif cmd == "add":
        if len(sys.argv) < 4:
            print("Usage: memory_store.py add <collection> <content> [metadata_json]")
            sys.exit(1)
        collection = sys.argv[2]
        content = sys.argv[3]
        metadata = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
        mem_id = add_memory(collection, content, metadata)
        print(f"Added memory: {mem_id}")
    
    elif cmd == "query":
        if len(sys.argv) < 4:
            print("Usage: memory_store.py query <collection> <query> [n_results]")
            sys.exit(1)
        collection = sys.argv[2]
        query = sys.argv[3]
        n = int(sys.argv[4]) if len(sys.argv) > 4 else 5
        results = query_memory(collection, query, n)
        for doc, meta, dist in zip(results["documents"], results["metadatas"], results["distances"]):
            print(f"[{dist:.3f}] {doc[:100]}...")
    
    elif cmd == "query-all":
        if len(sys.argv) < 3:
            print("Usage: memory_store.py query-all <query> [n_results]")
            sys.exit(1)
        query = sys.argv[2]
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
        results = query_all(query, n)
        for collection, data in results.items():
            print(f"\n## {collection.upper()}")
            for doc, dist in zip(data["documents"], data["distances"]):
                print(f"  [{dist:.3f}] {doc[:80]}...")
    
    elif cmd == "boot":
        print("=== PINCH MEMORY BOOT SEQUENCE ===\n")
        
        stats = get_collection_stats()
        print(f"Total memories: {sum(stats.values())}\n")
        
        print("## Identity")
        identity = recall_identity()
        for doc in identity["documents"][:3]:
            print(f"  • {doc[:100]}...")
        
        print("\n## Active Goals")
        goals = recall_active_goals()
        for doc in goals["documents"][:3]:
            print(f"  • {doc[:100]}...")
        
        print("\n## Recent Context")
        recent = recall_recent_context()
        for doc in recent["documents"][:3]:
            print(f"  • {doc[:100]}...")
    
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
