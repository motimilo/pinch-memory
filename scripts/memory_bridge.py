#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lancedb>=0.5.0",
#     "sentence-transformers>=2.2.0",
#     "networkx>=3.0",
#     "engramai[sentence-transformers]>=0.1.0",
#     "flask>=3.0.0",
# ]
# ///
"""
PINCH Memory Bridge — Best of both worlds.

Combines:
  - PINCH graph (LanceDB + networkx bonds) → storage + spreading activation
  - Engram cognitive mechanics → reward, forget, pin, session cache, MCP

API (drop-in replacement for memory_server.py routes):
  POST /search       — graph-aware semantic search + session cache
  POST /add          — store memory with type + importance
  POST /reward       — strengthen recent memories
  POST /forget       — prune below threshold
  POST /pin          — protect from decay
  POST /consolidate  — working → long-term
  GET  /stats        — combined stats
  GET  /health       — liveness
"""

import json
import time
import sys
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional
from flask import Flask, request, jsonify

# Add pinch scripts to path
sys.path.insert(0, str(Path(__file__).parent))

# ── PINCH graph (primary store) ───────────────────────────────────────────────
try:
    import memory_graph as _mg
    _PINCH_AVAILABLE = True
except ImportError:
    _PINCH_AVAILABLE = False
    print("⚠ PINCH graph not available — falling back to Engram only")

# ── Engram (cognitive mechanics layer) — thread-local for SQLite safety ──────
import threading
_ENGRAM_DB = Path.home() / ".openclaw" / "workspace" / "pinch-memory" / "engram.db"
_engram_local = threading.local()

try:
    from engram import Memory as _EngramMemory
    _ENGRAM_AVAILABLE = True
    # Test instantiation
    _test = _EngramMemory(str(_ENGRAM_DB))
    print(f"✓ Engram available ({_test.stats()['total_memories']} memories)")
    del _test
except Exception as e:
    _ENGRAM_AVAILABLE = False
    print(f"⚠ Engram not available: {e}")


def _engram() -> Optional["_EngramMemory"]:
    """Get or create thread-local Engram instance."""
    if not _ENGRAM_AVAILABLE:
        return None
    if not hasattr(_engram_local, "instance"):
        _engram_local.instance = _EngramMemory(str(_ENGRAM_DB))
    return _engram_local.instance

app = Flask(__name__)

# ── Session cache ─────────────────────────────────────────────────────────────
_session_cache: dict[str, tuple[float, list]] = {}  # key → (ts, results)
SESSION_TTL = 300  # 5 minutes


def _session_key(query: str, session_id: str) -> str:
    return hashlib.md5(f"{session_id}:{query[:50]}".encode()).hexdigest()


def _cache_get(query: str, session_id: str) -> Optional[list]:
    key = _session_key(query, session_id)
    if key in _session_cache:
        ts, results = _session_cache[key]
        if time.time() - ts < SESSION_TTL:
            return results
    return None


def _cache_set(query: str, session_id: str, results: list):
    key = _session_key(query, session_id)
    _session_cache[key] = (time.time(), results)


# ── Core search (PINCH graph + Engram fallback) ───────────────────────────────

def _pinch_search(query: str, limit: int, max_chars: int = 300) -> list[dict]:
    """Search PINCH's LanceDB with graph spreading activation."""
    results = _mg.recall(query, n=limit * 2)
    formatted = []
    for mem in results[:limit]:
        strength_data = _mg.get_strength(mem.get("id", ""))
        strength = strength_data.get("strength", 0.5) if strength_data else 0.5
        content = mem.get("content", "")
        if len(content) > max_chars:
            content = content[:max_chars] + "..."
        formatted.append({
            "id": mem.get("id", ""),
            "content": content,
            "category": mem.get("category", "episodic"),
            "type": mem.get("type", mem.get("category", "episodic")),
            "strength": round(strength, 3),
            "confidence": round(strength, 3),
            "source": "pinch_graph",
        })
    return formatted


def _engram_search(query: str, limit: int) -> list[dict]:
    """Search Engram (fallback or supplement)."""
    if not _ENGRAM_AVAILABLE:
        return []
    results = _engram().recall(query, limit=limit)
    return [
        {
            "id": r.get("id", ""),
            "content": r.get("content", ""),
            "category": r.get("type", "episodic"),
            "type": r.get("type", "episodic"),
            "strength": round(r.get("confidence", 0.5), 3),
            "confidence": round(r.get("confidence", 0.5), 3),
            "source": "engram",
        }
        for r in results
    ]


def _merge_results(pinch: list, engram: list, limit: int) -> list:
    """Merge, deduplicate, and re-rank by confidence."""
    seen = set()
    merged = []
    for r in pinch + engram:
        c = r["content"][:80]
        if c not in seen:
            seen.add(c)
            merged.append(r)
    merged.sort(key=lambda x: x["confidence"], reverse=True)
    return merged[:limit]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    stats = {}
    if _PINCH_AVAILABLE:
        try:
            db = _mg.get_db()
            tbl = db.open_table("memories")
            stats["pinch_memories"] = len(tbl.to_pandas())
            stats["pinch_bonds"] = 0
            try:
                import memory_graph as mg
                g = mg.load_graph()
                stats["pinch_bonds"] = g.number_of_edges()
            except Exception:
                pass
        except Exception:
            pass
    if _ENGRAM_AVAILABLE:
        s = _engram().stats()
        stats["engram_memories"] = s["total_memories"]
    return jsonify({"status": "ok", "bonds": stats.get("pinch_bonds", 0),
                    "memories": stats.get("pinch_memories", 0), **stats})


@app.route("/search", methods=["POST"])
def search():
    data = request.json or {}
    query = data.get("query", "")
    limit = int(data.get("limit", 5))
    session_id = data.get("session_id", "default")

    if not query:
        return jsonify({"results": [], "source": "none"})

    # Check session cache first
    cached = _cache_get(query, session_id)
    if cached is not None:
        return jsonify({"results": cached, "source": "session_cache", "cached": True})

    # Search PINCH graph
    results = []
    if _PINCH_AVAILABLE:
        try:
            results = _pinch_search(query, limit)
        except Exception as e:
            print(f"PINCH search error: {e}")

    # If PINCH gives < half results, supplement with Engram
    if len(results) < limit // 2 and _ENGRAM_AVAILABLE:
        engram_results = _engram_search(query, limit)
        results = _merge_results(results, engram_results, limit)

    _cache_set(query, session_id, results)
    return jsonify({"results": results, "source": "pinch_graph", "cached": False})


@app.route("/add", methods=["POST"])
def add_memory():
    data = request.json or {}
    content = data.get("content", "")
    category = data.get("category", data.get("type", "episodic"))
    importance = float(data.get("importance", 0.5))
    metadata = data.get("metadata", {})

    if not content:
        return jsonify({"error": "content required"}), 400

    mem_id = None

    # Add to PINCH graph
    if _PINCH_AVAILABLE:
        try:
            mem_id = _mg.add_memory(content, category=category, metadata={
                **metadata, "importance": importance, "type": category
            })
        except Exception as e:
            print(f"PINCH add error: {e}")

    # Sync to Engram (for cognitive mechanics)
    if _ENGRAM_AVAILABLE:
        try:
            _engram().add(content, type=category, importance=importance)
        except Exception as e:
            print(f"Engram sync error: {e}")

    return jsonify({"id": mem_id, "status": "added"})


@app.route("/reward", methods=["POST"])
def reward():
    """Dopaminergic reward — strengthen recent memories."""
    data = request.json or {}
    reason = data.get("reason", "positive feedback")
    recent_n = int(data.get("recent_n", 3))

    if _ENGRAM_AVAILABLE:
        _engram().reward(reason, recent_n=recent_n)

    # Also boost strength in PINCH for recently accessed memories
    if _PINCH_AVAILABLE:
        try:
            db = _mg.get_db()
            tbl = db.open_table("memories")
            df = tbl.to_pandas().sort_values("created_at", ascending=False).head(recent_n)
            for _, row in df.iterrows():
                mem_id = row.get("id")
                if mem_id:
                    _mg.update_strength(mem_id, delta=0.1)
        except Exception as e:
            print(f"PINCH reward error: {e}")

    return jsonify({"status": "rewarded", "n": recent_n, "reason": reason})


@app.route("/forget", methods=["POST"])
def forget():
    """Prune memories below strength threshold."""
    data = request.json or {}
    threshold = float(data.get("threshold", 0.1))

    pruned = 0
    if _PINCH_AVAILABLE:
        try:
            pruned = _mg.prune_weak_memories(threshold=threshold)
        except Exception as e:
            print(f"PINCH prune error: {e}")

    if _ENGRAM_AVAILABLE:
        _engram().forget(threshold=threshold)

    return jsonify({"status": "pruned", "count": pruned, "threshold": threshold})


@app.route("/pin", methods=["POST"])
def pin():
    """Pin a memory to protect it from decay."""
    data = request.json or {}
    mem_id = data.get("id", "")
    content = data.get("content", "")

    if _ENGRAM_AVAILABLE and content:
        results = _engram().recall(content, limit=1)
        if results:
            _engram().pin(results[0]["id"])

    # In PINCH: boost strength to max and add to long tier
    if _PINCH_AVAILABLE and mem_id:
        try:
            _mg.update_strength(mem_id, delta=0.5)
        except Exception as e:
            print(f"PINCH pin error: {e}")

    return jsonify({"status": "pinned", "id": mem_id})


@app.route("/consolidate", methods=["POST"])
def consolidate():
    """Run consolidation: working → long-term."""
    data = request.json or {}
    days = float(data.get("days", 1.0))
    min_importance = float(data.get("min_importance", 0.5))

    result = {"pinch": None, "engram": None}

    if _PINCH_AVAILABLE:
        try:
            n = _mg.consolidate_working_memory(min_importance=min_importance)
            result["pinch"] = f"{n} memories consolidated"
        except Exception as e:
            result["pinch"] = f"error: {e}"

    if _ENGRAM_AVAILABLE:
        _engram().consolidate(days=days)
        result["engram"] = "done"

    return jsonify({"status": "consolidated", **result})


@app.route("/stats", methods=["GET"])
def stats():
    result = {
        "timestamp": datetime.now().isoformat(),
        "pinch": {},
        "engram": {},
    }

    if _PINCH_AVAILABLE:
        try:
            db = _mg.get_db()
            tbl = db.open_table("memories")
            df = tbl.to_pandas()
            result["pinch"]["memories"] = len(df)
            result["pinch"]["by_category"] = df["category"].value_counts().to_dict() if "category" in df.columns else {}
            try:
                g = _mg.load_graph()
                result["pinch"]["bonds"] = g.number_of_edges()
                result["pinch"]["graph_nodes"] = g.number_of_nodes()
            except Exception:
                result["pinch"]["bonds"] = 0
        except Exception as e:
            result["pinch"]["error"] = str(e)

    if _ENGRAM_AVAILABLE:
        result["engram"] = _engram().stats()

    return jsonify(result)


@app.route("/session/clear", methods=["POST"])
def clear_session_cache():
    data = request.json or {}
    session_id = data.get("session_id")
    if session_id:
        keys_to_del = [k for k in _session_cache if session_id in k]
        for k in keys_to_del:
            del _session_cache[k]
        return jsonify({"cleared": len(keys_to_del)})
    _session_cache.clear()
    return jsonify({"cleared": "all"})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("BRIDGE_PORT", 5112))
    print(f"\n🧠 PINCH Memory Bridge starting on :{port}")
    print(f"   PINCH graph: {'✓' if _PINCH_AVAILABLE else '✗'}")
    print(f"   Engram layer: {'✓' if _ENGRAM_AVAILABLE else '✗'}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=False)
