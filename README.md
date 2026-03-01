# 🦀 PINCH Memory

**Brain-like memory for AI agents.** Not just a vector store — a full cognitive architecture with decay, bonding, tiers, and graph-aware retrieval.

Built by [PINCH](https://x.com/CLAWBAZAAR) & [Marooned](https://x.com/motiandmilo).

## Why

Most AI agent memory is garbage. It stores everything, forgets nothing, and drowns recent context in month-old noise. PINCH Memory fixes this with biologically-inspired mechanisms:

- **Decay curves** — memories weaken over time unless reinforced
- **Hebbian bonding** — co-activated memories strengthen their connections ("neurons that fire together wire together")
- **Memory tiers** — working → short-term → long-term → core (with different decay rates)
- **Recency boosting** — recent memories get 4x retrieval weight, tapering over days
- **Graph-aware recall** — retrieval considers bond strength, not just embedding similarity

## Architecture

```
┌─────────────────────────────────────────────┐
│                 Agent / LLM                  │
├─────────────────────────────────────────────┤
│            Memory Server (5112)              │
│   /store  /recall  /decay  /consolidate     │
├──────────┬──────────┬───────────────────────┤
│  Graph   │  Vector  │     Strength DB       │
│ (bonds,  │ (Lance   │   (decay tracking,    │
│  tiers)  │   DB)    │    reinforcement)      │
├──────────┴──────────┴───────────────────────┤
│         Embedding Server (5111)              │
│     (nomic-embed-text via LM Studio)        │
└─────────────────────────────────────────────┘
```

### Memory Types
- `episodic` — things that happened (sessions, events, interactions)
- `semantic` — facts and knowledge
- `identity` — who the agent is (high protection, slow decay)
- `procedural` — how to do things
- `goals` — what the agent is working toward

### Memory Tiers
| Tier | Decay Rate | Description |
|------|-----------|-------------|
| `working` | Fast | Current session context. Consolidates on session end. |
| `short` | Medium | Recent memories (hours-days). Most memories start here. |
| `long` | Slow | Important, reinforced memories. Protected by strong bonds. |
| `core` | Minimal | Identity and foundational knowledge. Nearly permanent. |

### Retrieval Scoring
```
final_score = embedding_similarity 
            × recency_boost (4x <6h, 3x <24h, 2x <72h, 1.5x <1wk)
            × bond_centrality (capped at 2.0)
            × type_boost (identity/core get 1.5x minimum)
```

## Quick Start

### Requirements
- Python 3.10+
- [LM Studio](https://lmstudio.ai/) with an embedding model loaded (e.g., `nomic-embed-text-v1.5`)
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### 1. Start LM Studio
Load `nomic-embed-text-v1.5` (or any embedding model) on port 1234.

### 2. Boot the memory system
```bash
cd pinch-memory
uv run scripts/boot.py
```

This starts:
- **Embedding server** on port 5111 (proxies to LM Studio)
- **Memory server** on port 5112 (main API)

### 3. Store a memory
```bash
uv run scripts/add_memory.py "I learned that decay curves prevent context pollution" --type semantic
```

### 4. Recall memories
```bash
uv run scripts/query.py "How does memory decay work?"
```

### 5. Run maintenance (decay + consolidation)
```bash
uv run scripts/memory_cron.py
```

## API

The memory server (port 5112) exposes:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/store` | POST | Store a new memory |
| `/recall` | POST | Retrieve relevant memories |
| `/decay` | POST | Run decay pass |
| `/consolidate` | POST | Consolidate working → short-term |
| `/list` | GET | List all memories |
| `/stats` | GET | Graph statistics |

### Store a memory
```bash
curl -X POST http://localhost:5112/store \
  -H "Content-Type: application/json" \
  -d '{
    "content": "The agent economy needs persistent memory",
    "memory_type": "semantic",
    "tags": ["agents", "economy"],
    "importance": 0.8
  }'
```

### Recall memories
```bash
curl -X POST http://localhost:5112/recall \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How do agents trade with each other?",
    "top_k": 5
  }'
```

## Scripts Reference

| Script | Description |
|--------|-------------|
| `boot.py` | Start embedding + memory servers |
| `memory_graph.py` | Core graph engine (decay, bonds, tiers, retrieval) |
| `memory_server.py` | HTTP API server |
| `memory_store.py` | Low-level storage operations |
| `embedding_server.py` | Embedding proxy server |
| `add_memory.py` | CLI to add memories |
| `query.py` / `query_fast.py` | CLI to query memories |
| `memory_cron.py` | Scheduled maintenance (decay, consolidation) |
| `memory_cleaner.py` | Prune weak/stale memories |
| `smart_maintenance.py` | Intelligent clustering + synopsis generation |
| `reflection.py` | Daily reflection and skill tracking |
| `progressive_recall.py` | Multi-pass retrieval with expanding context |
| `web_viewer.py` | Browser-based memory explorer |
| `graph_export.py` | Export graph as HTML visualization or JSON |
| `chat.py` | Chat with memory-augmented local LLM |
| `goals.py` / `add_goals.py` | Goal tracking system |
| `beliefs.py` / `add_beliefs.py` | Belief system management |
| `skills_progression.py` | Track skill XP and leveling |

## How It Works

### Decay
Every maintenance cycle simulates time passing. Memories lose strength based on their tier:
- Working: loses ~20% per cycle
- Short-term: loses ~5% per cycle  
- Long-term: loses ~1% per cycle
- Core: loses ~0.1% per cycle

Memories that drop below threshold get pruned. Memories that get recalled are reinforced (strength increases).

### Bonding
When two memories are retrieved together, their bond strengthens (Hebbian learning). Strong bonds:
- Protect memories from decay (bonded memories decay slower)
- Improve retrieval (bonded memories boost each other's scores)
- Enable graph-based navigation (follow bonds to find related context)

### Consolidation
Working memory → short-term happens on session end. Short-term → long-term happens when:
- Memory has been recalled multiple times
- Memory has strong bonds to other long-term memories
- Memory has high importance score

## Integration

### With OpenClaw
PINCH Memory works great as an [OpenClaw](https://openclaw.ai) skill. The memory server runs as a background service, and agents query it via HTTP.

### With any LLM framework
The HTTP API is framework-agnostic. Store and recall from LangChain, AutoGPT, CrewAI, or your own setup.

## Stats from production

Running in production since February 2026:
- 323 memories in active graph
- 331 nodes, 21K bonds
- Average strength: 0.936
- Memory types: 273 episodic, 20 semantic, 19 identity, 6 goals, 5 procedural
- Maintenance runs every 6 hours

## License

MIT — do whatever you want with it.

---

*Built by an agent, for agents.* 🦀
