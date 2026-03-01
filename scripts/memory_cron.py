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
PINCH Memory Cron Jobs

Run periodically to:
1. Apply decay to all memories
2. Consolidate strong short-term → long-term
3. Prune weak memories
4. Report stats
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from memory_graph import (
    get_db, load_graph, save_graph,
    DECAY_RATES, STRENGTH_PRUNE_THRESHOLD, 
    STRENGTH_CONSOLIDATE_THRESHOLD, ACCESS_CONSOLIDATE_THRESHOLD,
    get_stats, print_stats
)


def run_maintenance(hours_elapsed: float = 1.0):
    """Run full maintenance cycle."""
    print(f"🔧 PINCH Memory Maintenance")
    print(f"   Simulating {hours_elapsed} hours of decay")
    print("=" * 50)
    
    db = get_db()
    if "memories" not in db.table_names():
        print("No memories table found")
        return
    
    table = db.open_table("memories")
    G = load_graph()
    
    # Get all memories
    df = table.to_pandas()
    df = df[df["id"] != "__init__"]
    
    decayed = 0
    pruned = 0
    consolidated = 0
    
    # Track changes
    prune_list = []
    consolidate_list = []
    decay_summary = {"working": 0, "short": 0, "long": 0}
    
    for _, row in df.iterrows():
        mem_id = row["id"]
        tier = row.get("tier", "short")
        strength = row.get("strength", 1.0)
        access_count = row.get("access_count", 0)
        
        # Calculate decay
        base_decay = DECAY_RATES.get(tier, 0.02)
        
        # Protection from bonds
        if mem_id in G:
            total_bond = sum(d["weight"] for _, _, d in G.edges(mem_id, data=True))
            protection = 1 + (total_bond * 0.5)
        else:
            protection = 1.0
        
        # Access count protection
        access_protection = 1 + (access_count * 0.1)
        
        effective_decay = base_decay / (protection * access_protection)
        decay_amount = effective_decay * hours_elapsed
        new_strength = max(0, strength - decay_amount)
        
        # Check for pruning
        if new_strength < STRENGTH_PRUNE_THRESHOLD:
            prune_list.append({
                "id": mem_id,
                "content": row.get("content", "")[:50],
                "old_strength": strength,
                "new_strength": new_strength
            })
            pruned += 1
        
        # Check for consolidation
        elif (tier == "short" and 
              new_strength >= STRENGTH_CONSOLIDATE_THRESHOLD and
              access_count >= ACCESS_CONSOLIDATE_THRESHOLD):
            consolidate_list.append({
                "id": mem_id,
                "content": row.get("content", "")[:50],
                "strength": new_strength,
                "access_count": access_count
            })
            consolidated += 1
        
        else:
            if strength != new_strength:
                decay_summary[tier] = decay_summary.get(tier, 0) + 1
                decayed += 1
    
    # Report
    print(f"\n📉 Decay Applied:")
    for tier, count in decay_summary.items():
        if count > 0:
            print(f"   {tier}: {count} memories")
    
    if consolidate_list:
        print(f"\n📦 Ready for Consolidation (short → long): {len(consolidate_list)}")
        for item in consolidate_list[:5]:
            print(f"   • {item['content']}... (accessed {item['access_count']}x)")
    
    if prune_list:
        print(f"\n🗑️ Ready for Pruning: {len(prune_list)}")
        for item in prune_list[:5]:
            print(f"   • {item['content']}... (strength: {item['new_strength']:.3f})")
    
    print(f"\n📊 Summary:")
    print(f"   Decayed: {decayed}")
    print(f"   To consolidate: {consolidated}")
    print(f"   To prune: {pruned}")
    
    # Note: Actual updates would require delete+re-add in LanceDB
    # or a different storage backend that supports updates
    print(f"\n⚠️  Note: Changes are simulated. Full update support coming soon.")
    
    return {
        "decayed": decayed,
        "consolidated": consolidated,
        "pruned": pruned
    }


def show_health():
    """Show memory system health."""
    stats = get_stats()
    
    print("\n🧠 PINCH Memory Health Report")
    print("=" * 50)
    
    # Overall health indicators
    if stats["total_memories"] == 0:
        print("⚠️  No memories found!")
        return
    
    # Strength distribution
    print(f"\n💪 Strength:")
    print(f"   Average: {stats['avg_strength']:.2f}")
    if stats['avg_strength'] > 0.8:
        print("   Status: 🟢 Healthy")
    elif stats['avg_strength'] > 0.5:
        print("   Status: 🟡 Normal decay")
    else:
        print("   Status: 🔴 Heavy decay - consider reinforcement")
    
    # Tier balance
    total = stats["total_memories"]
    long_ratio = stats["by_tier"]["long"] / total if total > 0 else 0
    
    print(f"\n📊 Tier Balance:")
    print(f"   Long-term: {stats['by_tier']['long']} ({long_ratio*100:.1f}%)")
    print(f"   Short-term: {stats['by_tier']['short']}")
    print(f"   Working: {stats['by_tier']['working']}")
    
    if long_ratio < 0.05:
        print("   Status: 🟡 Few consolidated memories - need more reinforcement")
    elif long_ratio > 0.5:
        print("   Status: 🟢 Good consolidation")
    else:
        print("   Status: 🟢 Healthy balance")
    
    # Graph connectivity
    print(f"\n🔗 Graph Connectivity:")
    print(f"   Nodes: {stats['graph_nodes']}")
    print(f"   Bonds: {stats['total_bonds']}")
    
    if stats['total_bonds'] > 0:
        avg_degree = (stats['total_bonds'] * 2) / stats['graph_nodes']
        print(f"   Avg degree: {avg_degree:.2f}")
        
        if avg_degree < 0.5:
            print("   Status: 🟡 Sparse - need more cross-activation")
        else:
            print("   Status: 🟢 Well-connected")
    else:
        print("   Status: 🔴 No bonds - recall more to build connections")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("PINCH Memory Cron")
        print()
        print("Commands:")
        print("  decay [hours]   Run decay cycle (default: 1 hour)")
        print("  health          Show memory health report")
        print("  stats           Show raw statistics")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "decay":
        hours = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
        run_maintenance(hours)
    
    elif cmd == "health":
        show_health()
    
    elif cmd == "stats":
        print_stats()
    
    else:
        print(f"Unknown command: {cmd}")
