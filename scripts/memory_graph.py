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
PINCH Memory Graph v2.1 — Brain-like memory with decay, bonds, tiers, and working memory.

Memory Tiers:
- working: Current session, consolidates on session end
- short: Recent (hours-days), high decay
- long: Consolidated, low decay (protected by bonds)

Features:
- Strength-based decay with actual updates
- Hebbian bonding (co-activation strengthens connections)
- Graph-aware retrieval
- Working memory for session context
- Automatic consolidation
"""

import lancedb
import json
import re
import os
import math
import hashlib
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from sentence_transformers import SentenceTransformer
import networkx as nx

# Memory store location
MEMORY_DIR = Path.home() / ".openclaw" / "workspace" / "pinch-memory"
LANCE_DIR = MEMORY_DIR / "lance_db_v2"
GRAPH_FILE = MEMORY_DIR / "memory_graph.json"
STRENGTH_DB = MEMORY_DIR / "strength.db"  # SQLite for mutable strength tracking
WORKING_MEMORY_FILE = MEMORY_DIR / "working_memory.json"

# Decay rates per hour
DECAY_RATES = {
    "working": 1.0,      # Gone by end of session
    "short": 0.02,       # ~50% in 35 hours
    "long": 0.0005       # ~50% in 1400 hours (~2 months)
}

# Thresholds
STRENGTH_PRUNE_THRESHOLD = 0.1
STRENGTH_CONSOLIDATE_THRESHOLD = 0.6
ACCESS_CONSOLIDATE_THRESHOLD = 3

# Categories (semantic groupings)
CATEGORIES = ["episodic", "semantic", "procedural", "goals", "identity"]

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


# ============================================================
# STRENGTH TRACKING (SQLite for mutability)
# ============================================================

def init_strength_db():
    """Initialize SQLite database for mutable strength tracking."""
    conn = sqlite3.connect(str(STRENGTH_DB))
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS memory_state (
        id TEXT PRIMARY KEY,
        strength REAL DEFAULT 1.0,
        tier TEXT DEFAULT 'short',
        access_count INTEGER DEFAULT 0,
        last_accessed TEXT,
        updated_at TEXT
    )''')
    conn.commit()
    conn.close()

def get_strength(mem_id: str) -> dict:
    """Get mutable state for a memory."""
    init_strength_db()
    conn = sqlite3.connect(str(STRENGTH_DB))
    c = conn.cursor()
    c.execute("SELECT strength, tier, access_count, last_accessed FROM memory_state WHERE id = ?", (mem_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return {
            "strength": row[0],
            "tier": row[1],
            "access_count": row[2],
            "last_accessed": row[3]
        }
    return None

def set_strength(mem_id: str, strength: float, tier: str = None, access_count: int = None):
    """Update mutable state for a memory."""
    init_strength_db()
    conn = sqlite3.connect(str(STRENGTH_DB))
    c = conn.cursor()
    
    now = datetime.now().isoformat()
    
    # Check if exists
    c.execute("SELECT id FROM memory_state WHERE id = ?", (mem_id,))
    exists = c.fetchone()
    
    if exists:
        updates = ["strength = ?", "updated_at = ?"]
        params = [strength, now]
        
        if tier:
            updates.append("tier = ?")
            params.append(tier)
        if access_count is not None:
            updates.append("access_count = ?")
            params.append(access_count)
        
        params.append(mem_id)
        c.execute(f"UPDATE memory_state SET {', '.join(updates)} WHERE id = ?", params)
    else:
        c.execute("""INSERT INTO memory_state (id, strength, tier, access_count, last_accessed, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (mem_id, strength, tier or "short", access_count or 0, now, now))
    
    conn.commit()
    conn.close()

def record_access(mem_id: str, strength_boost: float = 0.1):
    """Record that a memory was accessed (reinforcement)."""
    init_strength_db()
    conn = sqlite3.connect(str(STRENGTH_DB))
    c = conn.cursor()
    
    now = datetime.now().isoformat()
    
    c.execute("SELECT strength, access_count FROM memory_state WHERE id = ?", (mem_id,))
    row = c.fetchone()
    
    if row:
        new_strength = min(1.0, row[0] + strength_boost)
        new_count = row[1] + 1
        c.execute("""UPDATE memory_state SET strength = ?, access_count = ?, last_accessed = ?, updated_at = ?
                     WHERE id = ?""", (new_strength, new_count, now, now, mem_id))
    else:
        c.execute("""INSERT INTO memory_state (id, strength, tier, access_count, last_accessed, updated_at)
                     VALUES (?, ?, 'short', 1, ?, ?)""", (mem_id, 1.0, now, now))
    
    conn.commit()
    conn.close()

def get_all_strengths() -> dict:
    """Get all memory states from SQLite."""
    init_strength_db()
    conn = sqlite3.connect(str(STRENGTH_DB))
    c = conn.cursor()
    c.execute("SELECT id, strength, tier, access_count, last_accessed FROM memory_state")
    rows = c.fetchall()
    conn.close()
    
    return {row[0]: {
        "strength": row[1],
        "tier": row[2],
        "access_count": row[3],
        "last_accessed": row[4]
    } for row in rows}


# ============================================================
# WORKING MEMORY (Session-scoped)
# ============================================================

def load_working_memory() -> list:
    """Load working memory from disk."""
    if WORKING_MEMORY_FILE.exists():
        return json.loads(WORKING_MEMORY_FILE.read_text())
    return []

def save_working_memory(memories: list):
    """Save working memory to disk."""
    WORKING_MEMORY_FILE.write_text(json.dumps(memories, indent=2))

def add_to_working_memory(content: str, category: str = "episodic", metadata: dict = None):
    """Add something to working memory (current session context)."""
    memories = load_working_memory()
    
    memories.append({
        "content": content,
        "category": category,
        "metadata": metadata or {},
        "timestamp": datetime.now().isoformat()
    })
    
    # Keep last 50 items max
    memories = memories[-50:]
    save_working_memory(memories)
    
    return len(memories)

def consolidate_working_memory(min_importance: float = 0.5):
    """Consolidate working memory into short-term memory."""
    memories = load_working_memory()
    
    if not memories:
        print("No working memory to consolidate")
        return 0
    
    consolidated = 0
    
    for mem in memories:
        # Add to main memory as short-term
        mem_id = add_memory(
            content=mem["content"],
            category=mem.get("category", "episodic"),
            tier="short",
            source="working_memory",
            metadata=mem.get("metadata", {}),
            initial_strength=0.8
        )
        consolidated += 1
    
    # Clear working memory
    save_working_memory([])
    
    return consolidated

def get_working_context(n: int = 10) -> list:
    """Get recent working memory for context."""
    memories = load_working_memory()
    return memories[-n:]


# ============================================================
# MEMORY SCHEMA (LanceDB)
# ============================================================

def init_memories_table():
    """Initialize the memories table with full schema."""
    db = get_db()
    
    if "memories" in db.table_names():
        return db.open_table("memories")
    
    # Create with initial record
    model = get_model()
    init_vec = model.encode("initialization").tolist()
    
    db.create_table("memories", data=[{
        "id": "__init__",
        "content": "Table initialized",
        "vector": init_vec,
        "category": "system",
        "tier": "long",
        "strength": 1.0,
        "created_at": datetime.now().isoformat(),
        "last_accessed": datetime.now().isoformat(),
        "access_count": 0,
        "source": "system",
        "metadata": "{}"
    }])
    
    return db.open_table("memories")


def generate_memory_id(content: str) -> str:
    """Generate a unique ID for a memory."""
    timestamp = datetime.now().isoformat()
    hash_input = f"{content}:{timestamp}"
    return hashlib.sha256(hash_input.encode()).hexdigest()[:16]


def clean_memory_content(content: str) -> str:
    """Clean noise from memory content before storing."""
    import re
    
    cleaned = content
    
    # Remove conversation metadata blocks
    cleaned = re.sub(r'Conversation info \(untrusted metadata\):\s*```json\s*\{[^}]+\}\s*```\s*', '', cleaned)
    
    # Remove message ID references
    cleaned = re.sub(r'\[message_id:\s*[^\]]+\]', '', cleaned)
    
    # Remove System message timestamps at start
    cleaned = re.sub(r'^System:\s*\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+\w+\]\s*', '', cleaned)
    
    # Remove relay boilerplate
    cleaned = re.sub(r'Please relay this reminder to the user in a helpful and friendly way\.\s*Current time:[^\n]+\n', '', cleaned)
    
    # Remove hourly check-in prefix
    cleaned = re.sub(r'CLAWBAZAAR HOURLY CHECK-IN:[^\n]+\n', '', cleaned)
    
    # Clean assistant/user prefixes
    cleaned = re.sub(r'^(assistant|user):\s*', '', cleaned, flags=re.MULTILINE)
    
    # Collapse excessive newlines
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    
    return cleaned.strip()


def is_low_value_content(content: str) -> bool:
    """Check if content is too low-value to store."""
    # Too short
    if len(content) < 20:
        return True
    
    # Pure metadata
    if content.startswith('Conversation info') and 'message_id' in content:
        return True
    
    # Just timestamps or IDs
    if re.match(r'^[\d\-:\s\w]+$', content):
        return True
    
    return False


def add_memory(
    content: str,
    category: str = "episodic",
    tier: str = "short",
    source: str = "unknown",
    metadata: dict = None,
    initial_strength: float = 1.0
) -> str:
    """Add a new memory to the graph."""
    # Clean content before storing
    content = clean_memory_content(content)
    
    # Skip low-value content
    if is_low_value_content(content):
        return None
    
    db = get_db()
    model = get_model()
    
    # Ensure table exists
    if "memories" not in db.table_names():
        init_memories_table()
    
    table = db.open_table("memories")
    
    # Generate embedding and ID
    vector = model.encode(content).tolist()
    mem_id = generate_memory_id(content)
    now = datetime.now().isoformat()
    
    # Prepare metadata
    meta = metadata or {}
    
    # Add to LanceDB (immutable content)
    table.add([{
        "id": mem_id,
        "content": content,
        "vector": vector,
        "category": category,
        "tier": tier,
        "strength": initial_strength,
        "created_at": now,
        "last_accessed": now,
        "access_count": 0,
        "source": source,
        "metadata": json.dumps(meta)
    }])
    
    # Add to SQLite strength tracker (mutable state)
    set_strength(mem_id, initial_strength, tier, 0)
    
    return mem_id


# ============================================================
# GRAPH (BONDS)
# ============================================================

def load_graph() -> nx.Graph:
    """Load the memory bond graph from disk with locking."""
    import fcntl
    
    if not GRAPH_FILE.exists():
        return nx.Graph()
    
    lock_file = GRAPH_FILE.parent / ".graph.lock"
    
    try:
        with open(lock_file, 'w') as lf:
            # Shared lock for reading
            fcntl.flock(lf.fileno(), fcntl.LOCK_SH)
            
            data = json.loads(GRAPH_FILE.read_text())
            G = nx.node_link_graph(data)
            
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
            return G
    except json.JSONDecodeError as e:
        print(f"Warning: Corrupted graph file, returning empty graph: {e}")
        return nx.Graph()
    except Exception as e:
        print(f"Warning: load_graph error: {e}")
        return nx.Graph()


def save_graph(G: nx.Graph):
    """Save the memory bond graph to disk atomically."""
    import tempfile
    import fcntl
    
    GRAPH_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = nx.node_link_data(G)
    json_str = json.dumps(data, indent=2)
    
    # Atomic write: write to temp file, then rename
    lock_file = GRAPH_FILE.parent / ".graph.lock"
    
    try:
        # Acquire lock
        with open(lock_file, 'w') as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            
            # Write to temp file in same directory (for atomic rename)
            fd, tmp_path = tempfile.mkstemp(
                dir=GRAPH_FILE.parent, 
                prefix='.graph_tmp_',
                suffix='.json'
            )
            try:
                with os.fdopen(fd, 'w') as tf:
                    tf.write(json_str)
                # Atomic rename
                os.rename(tmp_path, GRAPH_FILE)
            except:
                # Clean up temp file on error
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
            
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        print(f"Warning: save_graph error: {e}")


def add_bond(mem_id_1: str, mem_id_2: str, weight: float = 0.1, bond_type: str = "semantic"):
    """Add or strengthen a bond between two memories."""
    G = load_graph()
    
    if G.has_edge(mem_id_1, mem_id_2):
        G[mem_id_1][mem_id_2]["weight"] = min(
            G[mem_id_1][mem_id_2]["weight"] + weight,
            1.0
        )
    else:
        G.add_edge(mem_id_1, mem_id_2, weight=weight, type=bond_type)
    
    save_graph(G)
    return G[mem_id_1][mem_id_2]["weight"]


def get_bond_strength(mem_id: str) -> float:
    """Get total bond strength for a memory."""
    G = load_graph()
    if mem_id not in G:
        return 0.0
    return sum(data["weight"] for _, _, data in G.edges(mem_id, data=True))


# ============================================================
# DECAY & CONSOLIDATION
# ============================================================

def run_decay_cycle(hours_elapsed: float = 1.0):
    """Run decay on all memories with actual updates."""
    print(f"⏳ Running decay cycle ({hours_elapsed}h)...")
    
    db = get_db()
    if "memories" not in db.table_names():
        print("No memories table")
        return
    
    table = db.open_table("memories")
    G = load_graph()
    
    # Get all memories
    df = table.to_pandas()
    df = df[df["id"] != "__init__"]
    
    # Get current strengths from SQLite
    strengths = get_all_strengths()
    
    decayed = 0
    pruned = 0
    consolidated = 0
    
    for _, row in df.iterrows():
        mem_id = row["id"]
        
        # Get current state from SQLite or fall back to LanceDB
        state = strengths.get(mem_id, {
            "strength": row.get("strength", 1.0),
            "tier": row.get("tier", "short"),
            "access_count": row.get("access_count", 0),
            "last_accessed": row.get("last_accessed", datetime.now().isoformat())
        })
        
        tier = state["tier"]
        strength = state["strength"]
        access_count = state["access_count"]
        
        # Calculate decay
        base_decay = DECAY_RATES.get(tier, 0.02)
        
        # Protection from bonds
        if mem_id in G:
            total_bond = sum(d["weight"] for _, _, d in G.edges(mem_id, data=True))
            protection = 1 + (total_bond * 0.5)
        else:
            protection = 1.0
        
        # Access protection
        access_protection = 1 + (access_count * 0.1)
        
        effective_decay = base_decay / (protection * access_protection)
        decay_amount = effective_decay * hours_elapsed
        new_strength = max(0, strength - decay_amount)
        
        # Apply decay
        if new_strength < STRENGTH_PRUNE_THRESHOLD:
            # Mark for pruning (don't actually delete yet)
            set_strength(mem_id, 0.0, tier, access_count)
            pruned += 1
        elif (tier == "short" and 
              new_strength >= STRENGTH_CONSOLIDATE_THRESHOLD and
              access_count >= ACCESS_CONSOLIDATE_THRESHOLD):
            # Consolidate to long-term
            set_strength(mem_id, new_strength, "long", access_count)
            consolidated += 1
        else:
            # Normal decay
            set_strength(mem_id, new_strength, tier, access_count)
            if strength != new_strength:
                decayed += 1
    
    print(f"   Decayed: {decayed}")
    print(f"   Consolidated: {consolidated}")
    print(f"   Pruned: {pruned}")
    
    return {"decayed": decayed, "consolidated": consolidated, "pruned": pruned}


# ============================================================
# RETRIEVAL WITH HEBBIAN LEARNING
# ============================================================

def recall(query: str, n: int = 10, category: str = None) -> list:
    """Retrieve memories with graph-aware scoring and Hebbian reinforcement."""
    db = get_db()
    model = get_model()
    G = load_graph()
    
    if "memories" not in db.table_names():
        return []
    
    table = db.open_table("memories")
    query_vec = model.encode(query).tolist()
    
    # Vector search
    results = table.search(query_vec).limit(n * 3).to_list()
    results = [r for r in results if r.get("id") != "__init__"]
    
    if category:
        results = [r for r in results if r.get("category") == category]
    
    # Get current strengths
    strengths = get_all_strengths()
    
    # Score with graph awareness + recency
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    
    scored = []
    for r in results:
        mem_id = r["id"]
        base_score = 1 / (1 + r.get("_distance", 1))
        
        # Get current strength from SQLite
        state = strengths.get(mem_id, {"strength": r.get("strength", 0.5)})
        strength = state.get("strength", r.get("strength", 0.5))
        
        # Skip pruned memories
        if strength < STRENGTH_PRUNE_THRESHOLD:
            continue
        
        # Bond centrality bonus
        if mem_id in G:
            degree = G.degree(mem_id, weight="weight")
            centrality_bonus = 1 + (degree * 0.1)
        else:
            centrality_bonus = 1.0
        
        # Recency boost: memories from last 24h get up to 2x, 
        # last week get 1.5x, older get 1.0x (no penalty)
        recency_boost = 1.0
        created_at = r.get("created_at", "")
        if created_at:
            try:
                if isinstance(created_at, str):
                    ct = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                else:
                    ct = created_at
                if ct.tzinfo is None:
                    ct = ct.replace(tzinfo=timezone.utc)
                age_hours = (now - ct).total_seconds() / 3600
                if age_hours < 6:
                    recency_boost = 4.0
                elif age_hours < 24:
                    recency_boost = 3.0
                elif age_hours < 72:
                    recency_boost = 2.0
                elif age_hours < 168:  # 1 week
                    recency_boost = 1.5
            except (ValueError, TypeError):
                pass
        
        # Identity/core memories always get a boost regardless of age
        category = r.get("category", "")
        if category in ("identity", "core"):
            recency_boost = max(recency_boost, 1.5)
        
        # Cap centrality bonus to prevent over-accessed memories from dominating
        centrality_bonus = min(centrality_bonus, 2.0)
        
        final_score = base_score * strength * centrality_bonus * recency_boost
        r["_score"] = final_score
        r["_current_strength"] = strength
        scored.append(r)
    
    scored.sort(key=lambda x: x["_score"], reverse=True)
    top_results = scored[:n]
    
    # Hebbian reinforcement
    if len(top_results) >= 2:
        ids = [r["id"] for r in top_results]
        for i, id1 in enumerate(ids):
            for id2 in ids[i+1:]:
                add_bond(id1, id2, weight=0.05, bond_type="co-retrieval")
        
        # Boost strength of accessed memories
        for r in top_results:
            record_access(r["id"], strength_boost=0.05)
    
    return top_results


# ============================================================
# STATS
# ============================================================

def get_stats():
    """Get memory system statistics."""
    db = get_db()
    G = load_graph()
    strengths = get_all_strengths()
    
    stats = {
        "total_memories": 0,
        "by_tier": {"working": 0, "short": 0, "long": 0},
        "by_category": {},
        "avg_strength": 0,
        "total_bonds": G.number_of_edges(),
        "total_bond_weight": sum(d["weight"] for _, _, d in G.edges(data=True)) if G.edges() else 0,
        "graph_nodes": G.number_of_nodes(),
        "working_memory_size": len(load_working_memory())
    }
    
    if "memories" not in db.table_names():
        return stats
    
    table = db.open_table("memories")
    df = table.to_pandas()
    df = df[df["id"] != "__init__"]
    
    stats["total_memories"] = len(df)
    
    if len(df) > 0:
        # Calculate from SQLite strengths
        total_strength = 0
        for _, row in df.iterrows():
            mem_id = row["id"]
            state = strengths.get(mem_id, {"strength": row.get("strength", 0.5), "tier": row.get("tier", "short")})
            
            tier = state.get("tier", row.get("tier", "short"))
            strength = state.get("strength", row.get("strength", 0.5))
            
            stats["by_tier"][tier] = stats["by_tier"].get(tier, 0) + 1
            total_strength += strength
            
            cat = row.get("category", "unknown")
            stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
        
        stats["avg_strength"] = total_strength / len(df)
    
    return stats


def print_stats():
    """Print formatted stats."""
    stats = get_stats()
    
    print("\n📊 PINCH Memory Graph Stats")
    print("=" * 40)
    print(f"Total memories: {stats['total_memories']}")
    print(f"Working memory: {stats['working_memory_size']} items")
    print(f"Average strength: {stats['avg_strength']:.3f}")
    print()
    print("By tier:")
    for tier, count in stats["by_tier"].items():
        bar = "█" * min(count // 10, 20)
        print(f"  {tier:8} {count:4} {bar}")
    print()
    print("By category:")
    for cat, count in stats["by_category"].items():
        bar = "█" * min(count // 10, 20)
        print(f"  {cat:12} {count:4} {bar}")
    print()
    print("Graph:")
    print(f"  Nodes: {stats['graph_nodes']}")
    print(f"  Bonds: {stats['total_bonds']}")
    print(f"  Total bond weight: {stats['total_bond_weight']:.2f}")


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("PINCH Memory Graph v2.1")
        print()
        print("Commands:")
        print("  init              Initialize tables")
        print("  stats             Show statistics")
        print("  add <content>     Add a memory (short-term)")
        print("  working <content> Add to working memory")
        print("  consolidate       Consolidate working → short-term")
        print("  recall <query>    Retrieve with Hebbian learning")
        print("  decay [hours]     Run decay cycle")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "init":
        print("Initializing PINCH Memory Graph v2.1...")
        init_memories_table()
        init_strength_db()
        print("Done!")
    
    elif cmd == "stats":
        print_stats()
    
    elif cmd == "add":
        if len(sys.argv) < 3:
            print("Usage: memory_graph.py add <content>")
            sys.exit(1)
        content = " ".join(sys.argv[2:])
        mem_id = add_memory(content, tier="short")
        print(f"Added memory: {mem_id}")
    
    elif cmd == "working":
        if len(sys.argv) < 3:
            print("Usage: memory_graph.py working <content>")
            sys.exit(1)
        content = " ".join(sys.argv[2:])
        count = add_to_working_memory(content)
        print(f"Added to working memory ({count} items)")
    
    elif cmd == "consolidate":
        count = consolidate_working_memory()
        print(f"Consolidated {count} memories from working → short-term")
    
    elif cmd == "recall":
        if len(sys.argv) < 3:
            print("Usage: memory_graph.py recall <query>")
            sys.exit(1)
        query = " ".join(sys.argv[2:])
        results = recall(query, n=5)
        print(f"\n🔍 Retrieved {len(results)} memories (Hebbian bonds reinforced)")
        for i, r in enumerate(results):
            score = r.get("_score", 0)
            strength = r.get("_current_strength", r.get("strength", 0))
            content = r.get("content", "")[:80]
            print(f"   [{i+1}] score={score:.2f} str={strength:.2f} | {content}...")
    
    elif cmd == "decay":
        hours = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
        run_decay_cycle(hours)
    
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
