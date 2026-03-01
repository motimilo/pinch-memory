---
name: pinch-memory
description: Brain-like semantic memory system with decay, Hebbian bonding, and explicit search. Use pinch_search when you need to recall past decisions, context, or how something was done before.
metadata:
  openclaw:
    emoji: "🧠"
    requires:
      bins: ["uv"]
      env: {}
---

# PINCH Memory System

Brain-like semantic memory with:
- **Explicit Search** — Actively search memory when you don't know something
- **Tiers:** working → short-term → long-term
- **Decay:** Strength fades unless reinforced by access or bonds
- **Hebbian bonding:** Co-retrieved memories strengthen connections
- **Atomic writes:** File locking prevents corruption

## 🔍 Search Tool Pattern (IMPORTANT)

**When to search memory:**
- Before answering questions about past work/decisions
- When asked "have we done X before?"
- When you need context you don't have
- Before repeating something that might exist

### CLI Search
```bash
# Basic search
uv run {baseDir}/scripts/pinch_search.py "CLAWBAZAAR contracts"

# Filter by type
uv run {baseDir}/scripts/pinch_search.py --type episodic "recent conversations"

# More results, full content
uv run {baseDir}/scripts/pinch_search.py --limit 10 --verbose "milo trading"

# JSON output for parsing
uv run {baseDir}/scripts/pinch_search.py --json "outreach radar"
```

### API Search (port 5112)
```bash
curl -X POST http://127.0.0.1:5112/search \
  -H "Content-Type: application/json" \
  -d '{"query": "what do I know about milo?", "limit": 5, "type": "semantic"}'
```

**Response:**
```json
{
  "memories": [
    {"content": "...", "type": "semantic", "score": 0.85, "strength": 0.9, "tags": [...]}
  ],
  "query": "...",
  "found": 3
}
```

## Commands

### Session Boot (run at session start)
```bash
uv run {baseDir}/scripts/boot.py
```

### Add to working memory (current session context)
```bash
uv run {baseDir}/scripts/memory_graph.py working "something that happened"
```

### Consolidate working memory (end of session)
```bash
uv run {baseDir}/scripts/memory_graph.py consolidate
```

### Add permanent memory
```bash
uv run {baseDir}/scripts/memory_graph.py add "important fact to remember"
```

### Recall with Hebbian reinforcement
```bash
uv run {baseDir}/scripts/memory_graph.py recall "your query"
```

### Run decay cycle
```bash
uv run {baseDir}/scripts/memory_graph.py decay 6  # 6 hours
```

### Get stats
```bash
uv run {baseDir}/scripts/memory_graph.py stats
```

## API Endpoints (port 5112)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/stats` | GET | Memory stats |
| `/query` | POST | Basic query (auto-retrieval) |
| `/search` | POST | **Explicit search with filtering** |

## Architecture

```
Layer 3: Cluster Synopses      ← LLM-generated abstractions
         ↓ contains
Layer 2: Graph Bonds           ← Semantic + Hebbian + Cluster (5600+ bonds)
         ↓ connects  
Layer 1: Memories              ← Raw events, facts, identity (317+)
         ↑
Layer 0: Working Memory        ← Current session (consolidates on end)
```

## Files

| File | Purpose |
|------|---------|
| `lance_db_v2/` | Vector store (LanceDB) |
| `strength.db` | Mutable strength tracking (SQLite) |
| `memory_graph.json` | Bond graph (NetworkX) — atomic writes |
| `.graph.lock` | File lock for concurrent access |
| `working_memory.json` | Current session context |
| `cluster_synopses.json` | LLM-generated cluster summaries |

## Best Practices

1. **Search first** — When you don't know something, search PINCH before asking
2. **Session start:** Run `boot.py` to load identity, goals, recent context
3. **During session:** Add significant events to working memory
4. **Session end:** Run `consolidate` to move working → short-term
5. **Important facts:** Use `add` to directly create permanent memories
6. **Queries:** Use `recall` to reinforce relevant memories via Hebbian learning

## Scheduled Jobs

- **Every 6h:** Decay cycle via `memory_cron.py decay 6`
- **Weekly (Sun 3am):** Smart maintenance
