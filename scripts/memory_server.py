#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lancedb>=0.5.0",
#     "sentence-transformers>=2.2.0",
#     "pyarrow>=14.0.0",
#     "pandas>=2.0.0",
#     "networkx>=3.0",
#     "flask>=3.0.0",
#     "engramai[sentence-transformers]>=0.1.0",
# ]
# ///
"""
PINCH Memory Server
Keeps memory graph + embeddings loaded for sub-second queries.
Run: uv run memory_server.py
"""

import json
import sys
from pathlib import Path
from flask import Flask, request, jsonify

sys.path.insert(0, str(Path(__file__).parent))


# ── Engram cognitive mechanics (reward, forget, pin, session cache) ───────────
_engram_instance = None
_engram_db_path = str(Path.home() / ".openclaw" / "workspace" / "pinch-memory" / "engram.db")

def get_engram():
    global _engram_instance
    if _engram_instance is None:
        try:
            from engram import Memory as EngramMemory
            _engram_instance = EngramMemory(_engram_db_path)
            print("✓ Engram cognitive layer loaded")
        except Exception as e:
            print(f"⚠ Engram not available: {e}")
    return _engram_instance

# Session cache (skip DB on repeated queries)
import hashlib, time as _time
_session_cache = {}
SESSION_TTL = 300

def _cache_get(query, session_id):
    key = hashlib.md5(f"{session_id}:{query[:50]}".encode()).hexdigest()
    if key in _session_cache:
        ts, results = _session_cache[key]
        if _time.time() - ts < SESSION_TTL:
            return results
    return None

def _cache_set(query, session_id, results):
    key = hashlib.md5(f"{session_id}:{query[:50]}".encode()).hexdigest()
    _session_cache[key] = (_time.time(), results)

app = Flask(__name__)

# Global state
memory_graph = None
embedding_model = None

def get_embedding_model():
    global embedding_model
    if embedding_model is None:
        print("Loading embedding model...")
        from sentence_transformers import SentenceTransformer
        embedding_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        print("Embedding model loaded!")
    return embedding_model

def get_memory_graph():
    global memory_graph
    if memory_graph is None:
        print("Loading memory graph...")
        import memory_graph as mg
        memory_graph = mg
        # Test that recall works
        db = mg.get_db()
        if "memories" in db.table_names():
            table = db.open_table("memories")
            count = len(table.to_pandas())
            print(f"Memory graph loaded! {count} memories")
        else:
            print("Memory graph loaded! (no memories table yet)")
    return memory_graph

def query_memories(query: str, limit: int = 3, max_chars: int = 200) -> list[dict]:
    """Query memories with the loaded graph."""
    mg = get_memory_graph()
    
    results = mg.recall(query, n=limit * 2)
    
    formatted = []
    for mem in results[:limit]:
        strength_data = mg.get_strength(mem.get("id", ""))
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

def format_context(memories: list[dict]) -> str:
    """Format memories for context injection."""
    if not memories:
        return ""
    
    lines = ["## Relevant Memories", ""]
    for mem in memories:
        cat = mem["category"]
        content = mem["content"].replace("\n", " ").strip()
        lines.append(f"- [{cat}] {content}")
    
    return "\n".join(lines)

@app.route('/query', methods=['POST'])
def query():
    data = request.json
    query_text = data.get('query', '')
    limit = data.get('limit', 3)
    max_chars = data.get('max_chars', 200)
    
    if not query_text or len(query_text) < 10:
        return jsonify({'memories': [], 'context': ''})
    
    memories = query_memories(query_text, limit, max_chars)
    context = format_context(memories)
    
    return jsonify({
        'memories': memories,
        'context': context,
        'count': len(memories)
    })

@app.route('/health', methods=['GET'])
def health():
    mg = get_memory_graph()
    db = mg.get_db()
    G = mg.load_graph()
    
    mem_count = 0
    if "memories" in db.table_names():
        table = db.open_table("memories")
        mem_count = len(table.to_pandas())
    
    return jsonify({
        'status': 'ok',
        'memories': mem_count,
        'bonds': G.number_of_edges()
    })

@app.route('/stats', methods=['GET'])
def stats():
    mg = get_memory_graph()
    db = mg.get_db()
    G = mg.load_graph()
    
    mem_count = 0
    categories = {}
    
    if "memories" in db.table_names():
        table = db.open_table("memories")
        df = table.to_pandas()
        mem_count = len(df)
        for cat in df['category']:
            categories[cat] = categories.get(cat, 0) + 1
    
    eng = get_engram()
    engram_stats = {}
    if eng:
        try:
            s = eng.stats()
            engram_stats = {'total': s.get('total_memories', 0), 'by_type': s.get('by_type', {})}
        except Exception:
            pass

    return jsonify({
        'total_memories': mem_count,
        'total_bonds': G.number_of_edges(),
        'categories': categories,
        'engram': engram_stats,
        'session_cache_entries': len(_session_cache),
    })

@app.route('/search', methods=['POST'])
def search():
    """
    Enhanced memory search with filtering.
    
    POST JSON:
        query: str - What to search for
        limit: int - Max results (default 5)
        type: str - Filter by type (episodic/semantic/procedural/identity/goals)
        min_strength: float - Minimum strength 0-1 (default 0.3)
    
    Returns:
        memories: list of {content, type, score, strength, tags, id}
    """
    data = request.get_json()
    query = data.get('query', '')
    limit = data.get('limit', 5)
    mem_type = data.get('type')
    min_strength = data.get('min_strength', 0.3)
    session_id = data.get('session_id', 'default')

    if not query or len(query) < 5:
        return jsonify({'error': 'Query must be at least 5 characters', 'memories': []})

    # Session cache — skip DB on repeated queries within same session
    cached = _cache_get(query, session_id)
    if cached is not None:
        return jsonify({'memories': cached, 'query': query, 'found': len(cached), 'cached': True})
    
    mg = get_memory_graph()
    model = get_embedding_model()
    db = mg.get_db()
    
    if "memories" not in db.table_names():
        return jsonify({'memories': []})
    
    table = db.open_table("memories")
    query_vec = model.encode(query).tolist()
    
    # Get extra results for filtering
    results = table.search(query_vec).limit(limit * 3).to_list()
    
    filtered = []
    for r in results:
        # Type filter — stored as 'category' field
        mem_category = r.get("category") or r.get("type", "unknown")
        if mem_type and mem_category != mem_type:
            continue
        
        # Strength filter
        strength = r.get("strength", 1.0)
        if strength < min_strength:
            continue
        
        similarity = 1 - r.get("_distance", 0)
        combined_score = similarity * strength
        
        filtered.append({
            "content": r.get("content", ""),
            "type": mem_category,
            "score": round(combined_score, 3),
            "similarity": round(similarity, 3),
            "strength": round(strength, 3),
            "tags": r.get("tags", []),
            "id": r.get("id", ""),
        })
    
    filtered.sort(key=lambda x: x["score"], reverse=True)
    results = filtered[:limit]
    _cache_set(query, session_id, results)
    return jsonify({'memories': results, 'query': query, 'found': len(filtered), 'cached': False})


@app.route('/list', methods=['GET'])
def list_memories():
    """List all memories with optional type filter. For the web viewer."""
    mem_type = request.args.get('type')
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    
    mg = get_memory_graph()
    db = mg.get_db()
    
    if "memories" not in db.table_names():
        return jsonify({'memories': [], 'total': 0})
    
    table = db.open_table("memories")
    df = table.to_pandas()
    
    # Filter by type
    if mem_type:
        df = df[df['category'] == mem_type]
    
    # Sort by created_at desc
    if 'created_at' in df.columns:
        df = df.sort_values('created_at', ascending=False)
    
    total = len(df)
    df = df.iloc[offset:offset + limit]
    
    memories = []
    for _, row in df.iterrows():
        memories.append({
            'id': str(row.get('id', '')),
            'content': str(row.get('content', '')),
            'category': str(row.get('category', row.get('type', 'unknown'))),
            'strength': float(row.get('strength', 1.0)),
            'created_at': str(row.get('created_at', '')),
        })
    
    return jsonify({'memories': memories, 'total': total})



@app.route('/reward', methods=['POST'])
def reward():
    data = request.json or {}
    reason = data.get('reason', 'positive feedback')
    n = int(data.get('recent_n', 3))
    eng = get_engram()
    if eng:
        eng.reward(reason, recent_n=n)
    return jsonify({'status': 'rewarded', 'reason': reason, 'n': n})

@app.route('/forget', methods=['POST'])
def forget():
    data = request.json or {}
    threshold = float(data.get('threshold', 0.1))
    pruned = 0
    try:
        mg = get_memory_graph()
        pruned = mg.prune_weak_memories(threshold=threshold)
    except Exception as e:
        pass
    eng = get_engram()
    if eng:
        eng.forget(threshold=threshold)
    return jsonify({'status': 'pruned', 'count': pruned, 'threshold': threshold})

@app.route('/pin', methods=['POST'])
def pin():
    data = request.json or {}
    content = data.get('content', '')
    eng = get_engram()
    if eng and content:
        results = eng.recall(content, limit=1)
        if results:
            eng.pin(results[0]['id'])
    return jsonify({'status': 'pinned'})

@app.route('/session/clear', methods=['POST'])
def clear_session():
    _session_cache.clear()
    return jsonify({'status': 'cleared'})

if __name__ == '__main__':
    # Preload everything
    get_embedding_model()
    get_memory_graph()
    
    print("Starting PINCH memory server on port 5112...")
    app.run(host='127.0.0.1', port=5112, threaded=True)
