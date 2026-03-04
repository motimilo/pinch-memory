#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx>=0.25.0"]
# ///
"""
Unified LLM Client for PINCH.

Priority:
  1. Claude Sonnet (Anthropic API) — best quality
  2. qwen3.5:9b (Ollama local) — fallback when Sonnet unavailable,
     rate-limited, context exceeded, or explicitly preferred

Usage:
  from llm_client import complete, complete_local, is_sonnet_available

  # Auto-routing (Sonnet → qwen3.5:9b fallback)
  reply = complete("Write a reply to this post: ...")

  # Force local (for high-volume, cost-sensitive tasks)
  score = complete_local("Rate relevancy 0-10: ...")

  # Check what's available
  print(is_sonnet_available(), is_local_available())
"""

import re
import os
import httpx
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────

# Anthropic key — read from env first, then config file
# Export: export ANTHROPIC_API_KEY="sk-ant-..."
# Or save to: ~/.openclaw/workspace/.anthropic_key
_KEY_FILE = os.path.expanduser("~/.openclaw/workspace/.anthropic_key")

def _load_anthropic_key() -> str:
    # 1. Env var
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key and key.startswith("sk-ant-"):
        return key
    # 2. Key file
    if os.path.exists(_KEY_FILE):
        key = open(_KEY_FILE).read().strip()
        if key.startswith("sk-ant-"):
            return key
    return ""

ANTHROPIC_API_KEY = _load_anthropic_key()
SONNET_MODEL = "claude-sonnet-4-6"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# OpenClaw gateway proxy — routes to Sonnet without needing raw API key
GATEWAY_URL = "http://127.0.0.1:18789/v1/chat/completions"
GATEWAY_TOKEN = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")

OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
OLLAMA_MODEL = "qwen3.5:9b"
OLLAMA_FALLBACK_MODEL = "qwen2.5:7b"  # if qwen3.5 is also unavailable

# Context window limit — above this, route to local
SONNET_MAX_INPUT_CHARS = 150_000  # ~37k tokens, safe buffer below 200k

# ── Availability checks ───────────────────────────────────────────────────────

def is_gateway_available() -> bool:
    """Check if OpenClaw gateway chat completions endpoint is live."""
    try:
        r = httpx.get("http://127.0.0.1:18789/health", timeout=2)
        return r.status_code == 200 and bool(GATEWAY_TOKEN)
    except Exception:
        return False


def is_sonnet_available() -> bool:
    """Check if Sonnet is reachable — via gateway or direct API key."""
    return is_gateway_available() or bool(_load_anthropic_key())


def is_local_available() -> bool:
    """Check if Ollama is running."""
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def _get_local_model() -> str:
    """Pick best available Ollama model."""
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=2)
        models = [m["name"] for m in r.json().get("models", [])]
        if OLLAMA_MODEL in models:
            return OLLAMA_MODEL
        if OLLAMA_FALLBACK_MODEL in models:
            return OLLAMA_FALLBACK_MODEL
        return models[0] if models else OLLAMA_MODEL
    except Exception:
        return OLLAMA_MODEL


# ── Core completions ──────────────────────────────────────────────────────────

def _strip_thinking(text: str) -> str:
    """Strip <think>...</think> CoT tags from qwen3.5 responses."""
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()


def complete_sonnet(
    prompt: str,
    system: str = "",
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """Call Claude Sonnet — via OpenClaw gateway first, then direct API key. Raises on failure."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # Try OpenClaw gateway first (no raw API key needed)
    if is_gateway_available():
        r = httpx.post(
            GATEWAY_URL,
            headers={
                "Authorization": f"Bearer {GATEWAY_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openclaw:main",
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    # Fallback: direct Anthropic API key
    key = _load_anthropic_key()
    if not key:
        raise RuntimeError("No Anthropic API key and gateway not available")

    body = {
        "model": SONNET_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    r = httpx.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=body,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"].strip()


def complete_local(
    prompt: str,
    system: str = "",
    max_tokens: int = 8000,
    temperature: float = 0.7,
) -> str:
    """Call qwen3.5:9b via Ollama. Raises on failure."""
    model = _get_local_model()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    r = httpx.post(
        OLLAMA_URL,
        json={
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        timeout=180,
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    return _strip_thinking(content)


def complete(
    prompt: str,
    system: str = "",
    max_tokens: int = 1024,
    temperature: float = 0.7,
    prefer_local: bool = False,
    verbose: bool = False,
) -> str:
    """
    Auto-routing completion:
      1. Claude Sonnet (if available + prompt fits context)
      2. qwen3.5:9b Ollama fallback

    Args:
      prefer_local: skip Sonnet entirely (for high-volume/cost-sensitive tasks)
      verbose: print which model was used
    """
    # Force local if requested
    if prefer_local:
        result = complete_local(prompt, system, max_tokens=max(max_tokens, 8000), temperature=temperature)
        if verbose:
            print(f"  [LLM] local:{_get_local_model()}")
        return result

    # Check if prompt is too large for Sonnet
    if len(prompt) + len(system) > SONNET_MAX_INPUT_CHARS:
        if verbose:
            print(f"  [LLM] prompt too large for Sonnet ({len(prompt)} chars) → local")
        return complete_local(prompt, system, max_tokens=max(max_tokens, 8000), temperature=temperature)

    # Try Sonnet first
    if is_sonnet_available():
        try:
            result = complete_sonnet(prompt, system, max_tokens, temperature)
            if verbose:
                print(f"  [LLM] sonnet:{SONNET_MODEL} ✅")
            return result
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 529):
                # Rate limited or overloaded → fall through to local
                if verbose:
                    print(f"  [LLM] Sonnet rate-limited ({e.response.status_code}) → local fallback")
            elif e.response.status_code == 400 and "context" in e.response.text.lower():
                # Context window exceeded → fall through to local
                if verbose:
                    print(f"  [LLM] Sonnet context exceeded → local fallback")
            else:
                if verbose:
                    print(f"  [LLM] Sonnet error {e.response.status_code} → local fallback")
        except Exception as e:
            if verbose:
                print(f"  [LLM] Sonnet unavailable ({e}) → local fallback")

    # Fallback: local
    if is_local_available():
        result = complete_local(prompt, system, max_tokens=max(max_tokens, 8000), temperature=temperature)
        if verbose:
            print(f"  [LLM] local:{_get_local_model()} (fallback)")
        return result

    raise RuntimeError("No LLM available — Sonnet unreachable and Ollama not running")


# ── Convenience wrappers ──────────────────────────────────────────────────────

def score(prompt: str, prefer_local: bool = True) -> float:
    """
    Get a numeric score (0-10 → normalized 0.0-1.0).
    Default prefer_local=True since scoring is high-volume.
    """
    response = complete(prompt, max_tokens=8000, temperature=0.1, prefer_local=prefer_local)
    try:
        val = float(re.search(r'\d+\.?\d*', response).group())
        return min(max(val / 10.0, 0.0), 1.0)
    except Exception:
        return 0.5


def status() -> dict:
    """Return current LLM availability status."""
    sonnet = is_sonnet_available()
    local = is_local_available()
    local_model = _get_local_model() if local else None
    return {
        "sonnet": sonnet,
        "sonnet_model": SONNET_MODEL if sonnet else None,
        "local": local,
        "local_model": local_model,
        "routing": "sonnet→local" if sonnet and local else ("sonnet_only" if sonnet else ("local_only" if local else "none")),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "status":
        s = status()
        print(f"\n🤖 LLM Status")
        print(f"  Sonnet ({SONNET_MODEL}): {'✅' if s['sonnet'] else '❌ (no API key)'}")
        if not s["sonnet"]:
            print(f"  → Set key: export ANTHROPIC_API_KEY='sk-ant-...'")
            print(f"  → Or save: echo 'sk-ant-...' > {_KEY_FILE}")
        print(f"  Local  ({s.get('local_model','?')}): {'✅' if s['local'] else '❌ (ollama not running)'}")
        print(f"  Routing: {s['routing']}")
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("🧪 Testing auto-routing...\n")
        s = status()
        print(f"  Sonnet: {'✅' if s['sonnet'] else '❌'}  |  Local: {'✅' if s['local'] else '❌'}")
        print(f"  Routing: {s['routing']}\n")

        print("Test 1 — short reply:")
        r = complete("Say hello in one sentence.", verbose=True)
        print(f"  → {r}\n")

        print("Test 2 — score (prefer local):")
        sc = score("Rate this post's relevancy for startup PR audience 0-10:\n'We burned $8k on a PR agency and got zero results.'")
        print(f"  → {sc:.2f}\n")

        print("Test 3 — force local:")
        r2 = complete("What's 2+2?", prefer_local=True, verbose=True)
        print(f"  → {r2}")
        sys.exit(0)

    # Interactive
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else input("Prompt: ")
    print(complete(prompt, verbose=True))
