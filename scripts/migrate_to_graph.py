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
Migrate existing v1 memories to the v2 graph-based system.

Strategy:
1. Read all memories from v1 lance_db
2. Deduplicate by content similarity
3. Assign tiers based on age and category
4. Create initial bonds based on:
   - Temporal proximity (same day)
   - Category similarity
   - Semantic similarity (cosine > 0.8)
5. Set initial strength based on age
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import hashlib

import lancedb
from sentence_transformers import SentenceTransformer
import networkx as nx
import numpy as np

# Paths
MEMORY_DIR = Path.home() / ".openclaw" / "workspace" / "pinch-memory"
OLD_LANCE_DIR = MEMORY_DIR / "lance_db"
NEW_LANCE_DIR = MEMORY_DIR / "lance_db_v2"
GRAPH_FILE = MEMORY_DIR / "memory_graph.json"

# Import from memory_graph
import sys
sys.path.insert(0, str(Path(__file__).parent))
from memory_graph import (
    get_model, init_memories_table, generate_memory_id,
    save_graph, CATEGORIES
)


def cosine_similarity(v1, v2):
    """Calculate cosine similarity between two vectors."""
    v1 = np.array(v1)
    v2 = np.array(v2)
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))


def content_hash(content: str) -> str:
    """Hash content for deduplication."""
    return hashlib.md5(content.strip().lower().encode()).hexdigest()


def assign_tier(category: str, source: str, age_days: float) -> str:
    """Assign tier based on category and age."""
    # Identity and core goals are always long-term
    if category in ["identity", "goals"]:
        return "long"
    
    # Recent memories are short-term
    if age_days < 3:
        return "short"
    
    # Older memories that survived are long-term
    return "long"


def calculate_initial_strength(age_days: float, category: str) -> float:
    """Calculate initial strength based on age and category."""
    # Identity memories are strong
    if category == "identity":
        return 0.95
    
    # Goals are strong
    if category == "goals":
        return 0.9
    
    # Recent memories are strong
    if age_days < 1:
        return 0.95
    elif age_days < 7:
        return 0.8
    elif age_days < 30:
        return 0.6
    else:
        return 0.5


def migrate():
    """Run the migration."""
    print("=" * 50)
    print("PINCH Memory Migration: v1 → v2 (Graph)")
    print("=" * 50)
    
    # Connect to old database
    if not OLD_LANCE_DIR.exists():
        print("❌ No v1 database found at", OLD_LANCE_DIR)
        return
    
    old_db = lancedb.connect(str(OLD_LANCE_DIR))
    model = get_model()
    
    # Collect all memories from old tables
    all_memories = []
    seen_hashes = set()
    
    print("\n📖 Reading v1 memories...")
    
    for table_name in old_db.table_names():
        if table_name.startswith("_"):
            continue
        
        try:
            table = old_db.open_table(table_name)
            df = table.to_pandas()
            
            for _, row in df.iterrows():
                if row.get("id") == "__init__":
                    continue
                
                content = row.get("text") or row.get("content", "")
                if not content or len(content) < 10:
                    continue
                
                # Deduplicate
                h = content_hash(content)
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)
                
                # Parse metadata
                meta = {}
                if "metadata" in row and row["metadata"]:
                    try:
                        meta = json.loads(row["metadata"])
                    except:
                        pass
                
                # Determine category (table name or from metadata)
                category = table_name if table_name in CATEGORIES else "episodic"
                
                # Get timestamps
                created_at = meta.get("timestamp") or datetime.now().isoformat()
                try:
                    created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except:
                    created_dt = datetime.now()
                
                age_days = (datetime.now() - created_dt.replace(tzinfo=None)).days
                
                # Assign tier and strength
                tier = assign_tier(category, meta.get("source", ""), age_days)
                strength = calculate_initial_strength(age_days, category)
                
                all_memories.append({
                    "content": content,
                    "category": category,
                    "tier": tier,
                    "strength": strength,
                    "created_at": created_at,
                    "source": meta.get("source", "migration"),
                    "metadata": meta
                })
        
        except Exception as e:
            print(f"  ⚠️ Error reading {table_name}: {e}")
    
    print(f"\n📊 Found {len(all_memories)} unique memories")
    
    # Initialize new database
    print("\n📝 Creating v2 database...")
    NEW_LANCE_DIR.mkdir(parents=True, exist_ok=True)
    new_db = lancedb.connect(str(NEW_LANCE_DIR))
    
    # Create table with schema
    init_memories_table()
    table = new_db.open_table("memories")
    
    # Add memories with embeddings
    print("\n🔄 Migrating memories...")
    
    records = []
    id_map = {}  # content_hash -> mem_id
    embeddings = {}  # mem_id -> vector
    
    for i, mem in enumerate(all_memories):
        if (i + 1) % 50 == 0:
            print(f"  Processing {i + 1}/{len(all_memories)}...")
        
        # Generate embedding
        vector = model.encode(mem["content"]).tolist()
        mem_id = generate_memory_id(mem["content"])
        
        h = content_hash(mem["content"])
        id_map[h] = mem_id
        embeddings[mem_id] = vector
        
        records.append({
            "id": mem_id,
            "content": mem["content"],
            "vector": vector,
            "category": mem["category"],
            "tier": mem["tier"],
            "strength": mem["strength"],
            "created_at": mem["created_at"],
            "last_accessed": datetime.now().isoformat(),
            "access_count": 0,
            "source": mem["source"],
            "metadata": json.dumps(mem["metadata"])
        })
    
    # Batch insert
    if records:
        table.add(records)
    
    print(f"\n✅ Migrated {len(records)} memories")
    
    # Build initial graph bonds
    print("\n🔗 Building initial bonds...")
    G = nx.Graph()
    
    # Add all memory IDs as nodes
    for mem_id in embeddings.keys():
        G.add_node(mem_id)
    
    # Create bonds based on semantic similarity
    mem_ids = list(embeddings.keys())
    bond_count = 0
    
    print("  Computing semantic bonds (this may take a moment)...")
    
    for i, id1 in enumerate(mem_ids):
        if (i + 1) % 100 == 0:
            print(f"  Processing node {i + 1}/{len(mem_ids)}...")
        
        v1 = embeddings[id1]
        
        # Compare with nearby memories (not all, for efficiency)
        for j in range(i + 1, min(i + 50, len(mem_ids))):
            id2 = mem_ids[j]
            v2 = embeddings[id2]
            
            sim = cosine_similarity(v1, v2)
            
            if sim > 0.75:  # High similarity = strong bond
                weight = (sim - 0.75) * 4  # Map 0.75-1.0 to 0-1
                G.add_edge(id1, id2, weight=weight, type="semantic")
                bond_count += 1
    
    # Save graph
    save_graph(G)
    
    print(f"\n✅ Created {bond_count} initial bonds")
    
    # Print summary
    print("\n" + "=" * 50)
    print("Migration Complete!")
    print("=" * 50)
    
    tier_counts = defaultdict(int)
    cat_counts = defaultdict(int)
    
    for mem in all_memories:
        tier_counts[mem["tier"]] += 1
        cat_counts[mem["category"]] += 1
    
    print("\nBy tier:")
    for tier, count in tier_counts.items():
        print(f"  {tier}: {count}")
    
    print("\nBy category:")
    for cat, count in cat_counts.items():
        print(f"  {cat}: {count}")
    
    print(f"\nGraph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    
    if G.number_of_edges() > 0:
        avg_weight = sum(d["weight"] for _, _, d in G.edges(data=True)) / G.number_of_edges()
        print(f"Average bond weight: {avg_weight:.3f}")


if __name__ == "__main__":
    migrate()
