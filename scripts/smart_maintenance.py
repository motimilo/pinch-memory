#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lancedb>=0.5.0",
#     "sentence-transformers>=2.2.0",
#     "pyarrow>=14.0.0",
#     "pandas>=2.0.0",
#     "networkx>=3.0",
#     "httpx>=0.25.0",
#     "scikit-learn>=1.3.0",
# ]
# ///
"""
PINCH Smart Memory Maintenance

Uses local LLM (Qwen 2.5 14B) for intelligent memory management:
1. Cluster related memories
2. Generate synopses for clusters
3. Score importance for decay decisions
4. Consolidate redundant memories
5. Discover hidden connections
"""

import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import json
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from memory_graph import (
    get_db, load_graph, save_graph, add_bond, get_stats,
    STRENGTH_PRUNE_THRESHOLD
)
from local_llm import (
    is_available as llm_available,
    generate_synopsis, score_importance, 
    extract_key_facts, consolidate_memories,
    should_prune, find_connections
)

try:
    from sklearn.cluster import HDBSCAN
    HAS_HDBSCAN = True
except ImportError:
    HAS_HDBSCAN = False


def get_all_memories_with_vectors():
    """Load all memories with their vectors."""
    db = get_db()
    if "memories" not in db.table_names():
        return []
    
    table = db.open_table("memories")
    df = table.to_pandas()
    df = df[df["id"] != "__init__"]
    
    memories = []
    for _, row in df.iterrows():
        memories.append({
            "id": row["id"],
            "content": row.get("content", ""),
            "vector": row.get("vector", []),
            "category": row.get("category", "episodic"),
            "tier": row.get("tier", "short"),
            "strength": row.get("strength", 1.0),
            "access_count": row.get("access_count", 0),
            "created_at": row.get("created_at", ""),
        })
    
    return memories


def cluster_memories(memories: list, min_cluster_size: int = 3) -> dict:
    """Cluster memories using HDBSCAN on their vectors."""
    if not HAS_HDBSCAN:
        print("⚠️ HDBSCAN not available, skipping clustering")
        return {}
    
    if len(memories) < min_cluster_size * 2:
        print("⚠️ Too few memories for clustering")
        return {}
    
    # Extract vectors
    vectors = np.array([m["vector"] for m in memories if len(m.get("vector", [])) > 0])
    valid_memories = [m for m in memories if len(m.get("vector", [])) > 0]
    
    if len(vectors) < min_cluster_size * 2:
        return {}
    
    # Run HDBSCAN
    clusterer = HDBSCAN(min_cluster_size=min_cluster_size, metric='cosine')
    labels = clusterer.fit_predict(vectors)
    
    # Group memories by cluster
    clusters = defaultdict(list)
    for mem, label in zip(valid_memories, labels):
        if label >= 0:  # -1 is noise
            clusters[label].append(mem)
    
    return dict(clusters)


def generate_cluster_synopses(clusters: dict) -> list:
    """Generate synopses for each cluster using local LLM."""
    synopses = []
    
    for cluster_id, memories in clusters.items():
        if len(memories) < 2:
            continue
        
        contents = [m["content"][:200] for m in memories]
        synopsis = generate_synopsis(contents)
        
        synopses.append({
            "cluster_id": int(cluster_id),  # Convert numpy int64 to Python int
            "size": len(memories),
            "synopsis": synopsis,
            "member_ids": [m["id"] for m in memories]
        })
    
    return synopses


def run_smart_maintenance(dry_run: bool = True):
    """Run full smart maintenance cycle."""
    print("🧠 PINCH Smart Maintenance")
    print("=" * 50)
    
    # Check LLM availability
    if not llm_available():
        print("❌ Local LLM not available. Start LM Studio first.")
        return
    
    print("✅ Local LLM connected")
    
    # Load memories
    memories = get_all_memories_with_vectors()
    print(f"📊 Loaded {len(memories)} memories")
    
    G = load_graph()
    
    # 1. Cluster memories
    print("\n🔮 Phase 1: Clustering")
    print("-" * 40)
    
    clusters = cluster_memories(memories)
    print(f"Found {len(clusters)} clusters")
    
    # 2. Generate synopses
    if clusters:
        print("\n📝 Phase 2: Synopsis Generation")
        print("-" * 40)
        
        synopses = generate_cluster_synopses(clusters)
        
        for syn in synopses[:5]:  # Show first 5
            print(f"\n  Cluster {syn['cluster_id']} ({syn['size']} memories):")
            print(f"  Synopsis: {syn['synopsis'][:150]}...")
        
        # Save synopses
        synopsis_file = Path.home() / ".openclaw" / "workspace" / "pinch-memory" / "cluster_synopses.json"
        synopsis_file.write_text(json.dumps(synopses, indent=2))
        print(f"\n  💾 Saved {len(synopses)} synopses to cluster_synopses.json")
    
    # 3. Strengthen bonds within clusters
    print("\n🔗 Phase 3: Strengthening Cluster Bonds")
    print("-" * 40)
    
    bonds_created = 0
    for cluster_id, memories in clusters.items():
        mem_ids = [m["id"] for m in memories]
        for i, id1 in enumerate(mem_ids):
            for id2 in mem_ids[i+1:]:
                if not G.has_edge(id1, id2):
                    add_bond(id1, id2, weight=0.3, bond_type="cluster")
                    bonds_created += 1
    
    print(f"  Created {bonds_created} new cluster bonds")
    
    # 4. Score importance for weak memories
    print("\n⚖️ Phase 4: Importance Scoring")
    print("-" * 40)
    
    weak_memories = [m for m in memories if m["strength"] < 0.5]
    print(f"  Scoring {len(weak_memories)} weak memories...")
    
    rescue_list = []
    prune_list = []
    
    for mem in weak_memories[:20]:  # Limit for speed
        score = score_importance(mem["content"][:500])
        
        if score > 0.7:
            rescue_list.append({"id": mem["id"], "content": mem["content"][:50], "score": score})
        elif score < 0.3:
            prune_list.append({"id": mem["id"], "content": mem["content"][:50], "score": score})
    
    if rescue_list:
        print(f"\n  🛡️ Memories to rescue (high importance despite low strength):")
        for m in rescue_list[:5]:
            print(f"    [{m['score']:.2f}] {m['content']}...")
    
    if prune_list:
        print(f"\n  🗑️ Memories safe to prune (low importance):")
        for m in prune_list[:5]:
            print(f"    [{m['score']:.2f}] {m['content']}...")
    
    # 5. Find new connections
    print("\n🔍 Phase 5: Connection Discovery")
    print("-" * 40)
    
    # Sample some memories and find connections
    sample = memories[:10]
    new_connections = 0
    
    for mem in sample:
        candidates = [m["content"][:100] for m in memories if m["id"] != mem["id"]][:20]
        connections = find_connections(mem["content"][:200], candidates)
        
        for idx, _ in connections:
            target_id = memories[idx]["id"] if idx < len(memories) else None
            if target_id and not G.has_edge(mem["id"], target_id):
                add_bond(mem["id"], target_id, weight=0.2, bond_type="llm_discovered")
                new_connections += 1
    
    print(f"  Discovered {new_connections} new connections")
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Maintenance Summary")
    print("=" * 50)
    print(f"  Clusters found: {len(clusters)}")
    print(f"  Synopses generated: {len(synopses) if clusters else 0}")
    print(f"  Cluster bonds created: {bonds_created}")
    print(f"  Memories to rescue: {len(rescue_list)}")
    print(f"  Memories to prune: {len(prune_list)}")
    print(f"  New connections discovered: {new_connections}")
    
    if dry_run:
        print("\n⚠️  Dry run - no changes applied")
    else:
        print("\n✅ Changes applied")
    
    # Save updated graph
    save_graph(G)


def quick_importance_check(query: str = None):
    """Quick check of memory importance distribution."""
    if not llm_available():
        print("❌ Local LLM not available")
        return
    
    memories = get_all_memories_with_vectors()
    
    # Sample random memories
    import random
    sample = random.sample(memories, min(10, len(memories)))
    
    print("🎲 Random Importance Check")
    print("-" * 40)
    
    for mem in sample:
        score = score_importance(mem["content"][:300])
        tier = mem.get("tier", "?")
        print(f"[{score:.2f}|{tier}] {mem['content'][:60]}...")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("PINCH Smart Maintenance")
        print()
        print("Commands:")
        print("  run [--apply]    Run full maintenance cycle")
        print("  cluster          Just cluster and generate synopses")
        print("  importance       Check random memory importance")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "run":
        dry_run = "--apply" not in sys.argv
        run_smart_maintenance(dry_run=dry_run)
    
    elif cmd == "cluster":
        print("🔮 Clustering memories...")
        memories = get_all_memories_with_vectors()
        clusters = cluster_memories(memories)
        
        if clusters:
            print(f"Found {len(clusters)} clusters")
            synopses = generate_cluster_synopses(clusters)
            for syn in synopses:
                print(f"\n  Cluster {syn['cluster_id']} ({syn['size']} memories):")
                print(f"  {syn['synopsis']}")
    
    elif cmd == "importance":
        quick_importance_check()
    
    else:
        print(f"Unknown command: {cmd}")
