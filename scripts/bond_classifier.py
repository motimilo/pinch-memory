#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "networkx>=3.0",
#     "requests>=2.31.0",
#     "lancedb>=0.5.0",
#     "pyarrow>=14.0.0",
# ]
# ///
"""
Bond Classifier — Labels bonds with semantic relationship types using local LLM.

Relationship types:
- extends: B builds on A
- contradicts: B opposes A  
- supports: B provides evidence for A
- prerequisite: A is needed to understand B
- example: B is an instance of A
- metaphor: B is a metaphorical expression of A
- temporal: A and B are temporally related
- same_topic: A and B discuss the same subject
"""

import json
import sys
import argparse
import requests
from pathlib import Path
import networkx as nx

GRAPH_FILE = Path.home() / ".openclaw/workspace/pinch-memory/memory_graph.json"
LLM_URL = "http://localhost:1234/v1/chat/completions"

RELATIONSHIP_TYPES = [
    "extends",      # B builds on A
    "contradicts",  # B opposes A
    "supports",     # B provides evidence for A
    "prerequisite", # A is needed to understand B
    "example",      # B is an instance of A
    "metaphor",     # B is metaphorical expression of A
    "temporal",     # A and B are temporally related
    "same_topic",   # A and B discuss same subject
]

def load_graph() -> nx.Graph:
    if GRAPH_FILE.exists():
        data = json.loads(GRAPH_FILE.read_text())
        return nx.node_link_graph(data)
    return nx.Graph()

def save_graph(G: nx.Graph):
    data = nx.node_link_data(G)
    GRAPH_FILE.write_text(json.dumps(data, indent=2))

def get_memory_content(mem_id: str) -> str:
    """Get memory content from LanceDB."""
    import lancedb
    db = lancedb.connect(str(Path.home() / ".openclaw/workspace/pinch-memory/lance_db_v2"))
    if "memories" not in db.table_names():
        return ""
    table = db.open_table("memories")
    results = table.search().where(f"id = '{mem_id}'").limit(1).to_list()
    if results:
        return results[0].get("content", "")[:500]
    return ""

def classify_relationship(content_a: str, content_b: str) -> tuple[str, float]:
    """Use local LLM to classify the relationship between two memories."""
    prompt = f"""Classify the relationship between these two memories.

Memory A:
{content_a[:300]}

Memory B:
{content_b[:300]}

Relationship types:
- extends: B builds on or extends A
- contradicts: B opposes or conflicts with A
- supports: B provides evidence or support for A
- prerequisite: A is needed to understand B
- example: B is a concrete instance of A
- metaphor: B expresses A metaphorically
- temporal: A and B are temporally connected
- same_topic: A and B discuss the same subject

Reply with ONLY the relationship type (one word) that best describes how B relates to A.
If unsure, reply "same_topic"."""

    try:
        resp = requests.post(LLM_URL, json={
            "model": "qwen2.5-14b-instruct-mlx",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 20,
            "temperature": 0.1,
        }, timeout=30)
        
        if resp.status_code == 200:
            result = resp.json()["choices"][0]["message"]["content"].strip().lower()
            # Extract just the relationship type
            for rel_type in RELATIONSHIP_TYPES:
                if rel_type in result:
                    return rel_type, 0.8
            return "same_topic", 0.5
    except Exception as e:
        print(f"LLM error: {e}")
    
    return "same_topic", 0.3

def classify_bonds(limit: int = 50, only_untyped: bool = True):
    """Classify bonds with semantic relationship types."""
    G = load_graph()
    
    classified = 0
    skipped = 0
    
    for u, v, data in list(G.edges(data=True)):
        if classified >= limit:
            break
            
        # Skip already classified (unless reclassifying all)
        current_type = data.get("type", "untyped")
        if only_untyped and current_type in RELATIONSHIP_TYPES:
            skipped += 1
            continue
        
        # Get memory contents
        content_a = get_memory_content(u)
        content_b = get_memory_content(v)
        
        if not content_a or not content_b:
            continue
        
        # Classify
        rel_type, confidence = classify_relationship(content_a, content_b)
        
        # Update edge
        G[u][v]["semantic_type"] = rel_type
        G[u][v]["semantic_confidence"] = confidence
        
        classified += 1
        print(f"[{classified}/{limit}] {u[:8]}..{v[:8]}: {current_type} -> {rel_type} ({confidence:.1f})")
    
    save_graph(G)
    print(f"\nClassified {classified} bonds, skipped {skipped}")
    return classified

def get_relationship_stats():
    """Get statistics on semantic relationship types."""
    G = load_graph()
    
    types = {}
    semantic_types = {}
    
    for u, v, data in G.edges(data=True):
        t = data.get("type", "untyped")
        types[t] = types.get(t, 0) + 1
        
        st = data.get("semantic_type")
        if st:
            semantic_types[st] = semantic_types.get(st, 0) + 1
    
    print("Bond types:")
    for t, count in sorted(types.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}")
    
    print("\nSemantic relationship types:")
    if semantic_types:
        for t, count in sorted(semantic_types.items(), key=lambda x: -x[1]):
            print(f"  {t}: {count}")
    else:
        print("  (none classified yet)")
    
    return types, semantic_types

def main():
    parser = argparse.ArgumentParser(description="Classify bond relationships")
    parser.add_argument("--classify", "-c", type=int, default=0, 
                       help="Classify N bonds with LLM")
    parser.add_argument("--all", action="store_true",
                       help="Reclassify all bonds (not just untyped)")
    parser.add_argument("--stats", "-s", action="store_true",
                       help="Show relationship statistics")
    
    args = parser.parse_args()
    
    if args.stats:
        get_relationship_stats()
    elif args.classify > 0:
        classify_bonds(args.classify, only_untyped=not args.all)
    else:
        get_relationship_stats()

if __name__ == "__main__":
    main()
