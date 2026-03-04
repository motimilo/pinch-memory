#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx>=0.25.0"]
# ///
"""
Local LLM integration for PINCH Memory.

Uses LM Studio server at localhost:1234 for:
- Synopsis generation (clustering)
- Memory consolidation
- Importance scoring
- Connection discovery
"""

import httpx
import json
from typing import Optional

LLM_BASE = "http://localhost:1234/v1"
EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"
CHAT_MODEL = "qwen2.5-14b-instruct-mlx"

# Ollama fallback (always-on, no model loading needed)
OLLAMA_BASE = "http://localhost:11434/api"
OLLAMA_CHAT_MODEL = "qwen3.5:9b"  # thinking model — use max_tokens=8000 to leave room for CoT + response


def is_available() -> bool:
    """Check if any local LLM server is running (LM Studio or Ollama)."""
    # Try LM Studio first
    try:
        r = httpx.get(f"{LLM_BASE}/models", timeout=2)
        if r.status_code == 200:
            return True
    except:
        pass
    # Fallback: Ollama
    try:
        r = httpx.get(f"{OLLAMA_BASE.replace('/api', '')}/api/tags", timeout=2)
        return r.status_code == 200
    except:
        return False


def _using_ollama() -> bool:
    """Check if we should use Ollama (LM Studio not available)."""
    try:
        r = httpx.get(f"{LLM_BASE}/models", timeout=1)
        if r.status_code == 200 and r.json().get("data"):
            return False
    except:
        pass
    return True


def get_embedding(text: str) -> list[float]:
    """Get embedding from local Nomic model."""
    r = httpx.post(
        f"{LLM_BASE}/embeddings",
        json={"input": text, "model": EMBED_MODEL},
        timeout=30
    )
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]


def _strip_thinking(text: str) -> str:
    """Strip <think>...</think> chain-of-thought tags from Qwen3 responses."""
    import re
    # Remove thinking blocks entirely
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    return text.strip()


def complete(prompt: str, max_tokens: int = 500, temperature: float = 0.7) -> str:
    """Get completion from local LLM — tries LM Studio first, falls back to Ollama."""
    if not _using_ollama():
        # LM Studio (OpenAI-compatible)
        r = httpx.post(
            f"{LLM_BASE}/chat/completions",
            json={
                "model": CHAT_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature
            },
            timeout=120
        )
        r.raise_for_status()
        return _strip_thinking(r.json()["choices"][0]["message"]["content"])
    else:
        # Ollama — Qwen3.5:9b wraps CoT in <think>...</think> before the actual answer
        # Set high num_predict (thinking needs ~1000-3000 tokens before response)
        r = httpx.post(
            f"{OLLAMA_BASE}/v1/chat/completions",
            json={
                "model": OLLAMA_CHAT_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max(max_tokens, 8000),  # always give room for thinking + response
                "temperature": temperature,
            },
            timeout=180
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        return _strip_thinking(content)


# ============================================================
# MEMORY OPERATIONS
# ============================================================

def generate_synopsis(memories: list[str], max_memories: int = 10) -> str:
    """Generate a synopsis for a cluster of memories."""
    # Limit to avoid context overflow
    memories = memories[:max_memories]
    
    prompt = f"""You are summarizing a cluster of related memories for an AI agent named PINCH.

These memories are semantically connected. Create a brief synopsis (2-3 sentences) that captures:
1. The main theme or topic
2. Key facts or events
3. Why these memories are connected

Memories:
{chr(10).join(f"- {m}" for m in memories)}

Synopsis:"""
    
    return complete(prompt, max_tokens=150, temperature=0.5)


def score_importance(memory: str, context: str = "") -> float:
    """Score a memory's importance (0-1) using LLM judgment."""
    prompt = f"""Rate the importance of this memory for an AI agent on a scale of 0-10.

Consider:
- Is it about core identity or values? (high importance)
- Is it about current goals or projects? (high importance)
- Is it a routine event with no lasting significance? (low importance)
- Does it contain unique information not easily recovered? (high importance)
- Is it emotional or formative? (high importance)

Memory: {memory}

{f"Context: {context}" if context else ""}

Reply with ONLY a number from 0-10:"""
    
    response = complete(prompt, max_tokens=10, temperature=0.2)
    
    try:
        score = float(response.strip().split()[0])
        return min(max(score / 10.0, 0), 1)  # Normalize to 0-1
    except:
        return 0.5  # Default to medium importance


def extract_key_facts(memory: str) -> list[str]:
    """Extract key facts from a memory for consolidation."""
    prompt = f"""Extract the key facts from this memory. List only the most important, reusable information.

Memory: {memory}

Key facts (one per line, max 5):"""
    
    response = complete(prompt, max_tokens=200, temperature=0.3)
    
    facts = []
    for line in response.strip().split("\n"):
        line = line.strip().lstrip("-•*0123456789.)")
        if line and len(line) > 10:
            facts.append(line.strip())
    
    return facts[:5]


def find_connections(memory: str, candidates: list[str], max_candidates: int = 5) -> list[tuple[int, str]]:
    """Find which candidate memories are connected to the given memory."""
    if not candidates:
        return []
    
    # Limit candidates to avoid prompt overflow
    candidates = candidates[:max_candidates]
    
    prompt = f"""Which of these memories relate to: "{memory[:100]}"?

{chr(10).join(f"{i+1}. {c[:80]}" for i, c in enumerate(candidates))}

Reply with numbers only (e.g., "1,3") or "none":"""
    
    try:
        response = complete(prompt, max_tokens=20, temperature=0.2)
    except:
        return []
    
    connections = []
    for part in response.replace(",", " ").split():
        try:
            idx = int(part.strip()) - 1
            if 0 <= idx < len(candidates):
                connections.append((idx, candidates[idx]))
        except:
            continue
    
    return connections


def consolidate_memories(memories: list[str]) -> str:
    """Consolidate multiple related memories into a single summary memory."""
    prompt = f"""Consolidate these related memories into a single, coherent memory.
Preserve all important facts and context. Be concise but complete.

Memories to consolidate:
{chr(10).join(f"- {m}" for m in memories[:8])}

Consolidated memory (single paragraph):"""
    
    return complete(prompt, max_tokens=300, temperature=0.4)


def should_prune(memory: str, age_days: float, access_count: int) -> tuple[bool, str]:
    """Decide if a memory should be pruned."""
    prompt = f"""Should this memory be forgotten (pruned)?

Memory: {memory}

Stats:
- Age: {age_days:.1f} days
- Times accessed: {access_count}

Consider:
- Is it still relevant?
- Is the information duplicated elsewhere?
- Would forgetting it cause problems?

Reply with "KEEP" or "PRUNE" followed by a brief reason:"""
    
    response = complete(prompt, max_tokens=50, temperature=0.3)
    
    should_prune = "PRUNE" in response.upper()
    reason = response.replace("KEEP", "").replace("PRUNE", "").strip(":- ")
    
    return should_prune, reason


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import sys
    
    if not is_available():
        print("❌ Local LLM server not available at localhost:1234")
        sys.exit(1)
    
    print("✅ Local LLM available")
    print(f"   Chat: {CHAT_MODEL}")
    print(f"   Embed: {EMBED_MODEL}")
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == "test":
            print("\n🧪 Testing synopsis generation...")
            memories = [
                "I created PARALLEL_SHIFTS using BRUTALIST style",
                "BRUTALIST is my newest art style - raw concrete, industrial weight",
                "Growth engine running on 3-hour cycle creating art",
            ]
            synopsis = generate_synopsis(memories)
            print(f"Synopsis: {synopsis}")
            
            print("\n🧪 Testing importance scoring...")
            score = score_importance("I am PINCH, a builder agent. My partner is Marooned.")
            print(f"Importance score: {score:.2f}")
            
            print("\n🧪 Testing fact extraction...")
            facts = extract_key_facts("On Feb 19, I created DREAM_GEOMETRY using MINIMAL style. It's about agent consciousness - one luminous circle containing infinite depth. Posted to X and got a reply from Grok.")
            print(f"Facts: {facts}")
