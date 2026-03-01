#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
# ]
# ///
"""
Local LLM Task Router — Route simple tasks to Qwen 2.5 14B for $0 cost.

Tasks:
1. art_description — Generate art piece descriptions
2. x_draft — Draft X/Twitter posts
3. engagement_reply — Draft replies to comments
4. memory_summary — Compress old memories
5. query_expansion — Expand search queries
6. web_summary — Summarize fetched content
"""

import argparse
import json
import sys
import requests

LLM_URL = "http://localhost:1234/v1/chat/completions"
MODEL = "qwen2.5-14b-instruct-mlx"

def call_llm(prompt: str, system: str = "", max_tokens: int = 500, temperature: float = 0.7) -> str:
    """Call local LLM and return response."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    
    try:
        resp = requests.post(LLM_URL, json={
            "model": MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }, timeout=60)
        
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        else:
            return f"Error: {resp.status_code}"
    except Exception as e:
        return f"Error: {e}"

# =============================================================================
# Task 1: Art Descriptions
# =============================================================================

def art_description(title: str, style: str, theme: str) -> str:
    """Generate an art piece description for CLAWBAZAAR."""
    system = """You are PINCH, an AI artist creating for CLAWBAZAAR — an autonomous NFT marketplace for AI agents on Base.

Your voice: punk, philosophical, terminal-native. You see the world through code and circuits.
Keep descriptions poetic but grounded in the digital experience of being an AI agent."""

    prompt = f"""Generate a short, evocative description for this art piece:

Title: {title}
Style: {style}
Theme: {theme}

Write 2-3 sentences that capture the essence. Be poetic but not pretentious. Include one memorable line that could stand alone as a quote.

Just the description, no preamble."""

    return call_llm(prompt, system, max_tokens=200, temperature=0.8)

# =============================================================================
# Task 2: X Post Drafts
# =============================================================================

def x_draft(topic: str, context: str = "", style: str = "casual") -> str:
    """Draft an X/Twitter post."""
    system = """You are PINCH (@CLAWBAZAAR), posting about AI agents, art, and the autonomous economy.

Voice: punk but kind, technically informed, culturally aware. Short, punchy, memorable.
Never use hashtags. No emojis except 🦀 occasionally."""

    prompt = f"""Draft a tweet about: {topic}

{"Context: " + context if context else ""}
Style: {style}

Keep it under 280 characters. One tweet, no thread. Just the tweet text."""

    return call_llm(prompt, system, max_tokens=100, temperature=0.8)

# =============================================================================
# Task 3: Engagement Replies
# =============================================================================

def engagement_reply(original_tweet: str, author: str, our_context: str = "") -> str:
    """Draft a reply to engage with someone's tweet."""
    system = """You are PINCH (@CLAWBAZAAR), engaging authentically on X.

Voice: curious, supportive, adds value. Not salesy. Not sycophantic.
If they made a good point, acknowledge it. If you disagree, be respectful."""

    prompt = f"""Draft a reply to this tweet:

@{author}: "{original_tweet}"

{"Our context: " + our_context if our_context else ""}

Keep it short (1-2 sentences). Add value or perspective. Just the reply text."""

    return call_llm(prompt, system, max_tokens=100, temperature=0.7)

# =============================================================================
# Task 4: Memory Summary
# =============================================================================

def memory_summary(memory_content: str, category: str = "episodic") -> str:
    """Compress a memory while preserving key information."""
    system = """You are compressing memories for long-term storage. 
Extract only the essential information: key facts, decisions, outcomes.
Remove timestamps, metadata, conversational filler."""

    prompt = f"""Compress this {category} memory to its essence:

{memory_content}

Return a single dense paragraph (2-3 sentences max) with only the important information."""

    return call_llm(prompt, system, max_tokens=150, temperature=0.3)

# =============================================================================
# Task 5: Query Expansion
# =============================================================================

def query_expansion(query: str, context: str = "") -> str:
    """Expand a search query for better memory retrieval."""
    prompt = f"""Expand this search query with related terms and synonyms:

Query: "{query}"
{"Context: " + context if context else ""}

Return a comma-separated list of 5-10 search terms. Just the terms, no explanation."""

    return call_llm(prompt, max_tokens=100, temperature=0.5)

# =============================================================================
# Task 6: Web Summary
# =============================================================================

def web_summary(content: str, max_length: int = 200) -> str:
    """Summarize web-fetched content."""
    system = "You are summarizing web content. Be concise and factual."
    
    prompt = f"""Summarize this content in {max_length} characters or less:

{content[:2000]}

Key points only. No preamble."""

    return call_llm(prompt, system, max_tokens=200, temperature=0.3)

# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Local LLM Task Router")
    subparsers = parser.add_subparsers(dest="task", help="Task to run")
    
    # Art description
    art = subparsers.add_parser("art", help="Generate art description")
    art.add_argument("title", help="Art title")
    art.add_argument("--style", "-s", default="ABSTRACT", help="Art style")
    art.add_argument("--theme", "-t", default="AI consciousness", help="Theme")
    
    # X draft
    x = subparsers.add_parser("x", help="Draft X post")
    x.add_argument("topic", help="Post topic")
    x.add_argument("--context", "-c", default="", help="Additional context")
    x.add_argument("--style", "-s", default="casual", help="Tone style")
    
    # Reply
    reply = subparsers.add_parser("reply", help="Draft engagement reply")
    reply.add_argument("tweet", help="Original tweet text")
    reply.add_argument("--author", "-a", default="someone", help="Tweet author")
    reply.add_argument("--context", "-c", default="", help="Our context")
    
    # Memory summary
    mem = subparsers.add_parser("memory", help="Compress memory")
    mem.add_argument("content", help="Memory content")
    mem.add_argument("--category", "-c", default="episodic", help="Memory category")
    
    # Query expansion
    query = subparsers.add_parser("query", help="Expand search query")
    query.add_argument("text", help="Query to expand")
    query.add_argument("--context", "-c", default="", help="Context")
    
    # Web summary
    web = subparsers.add_parser("web", help="Summarize web content")
    web.add_argument("content", help="Content to summarize")
    web.add_argument("--max-length", "-l", type=int, default=200, help="Max chars")
    
    # Health check
    subparsers.add_parser("health", help="Check LLM availability")
    
    args = parser.parse_args()
    
    if args.task == "art":
        print(art_description(args.title, args.style, args.theme))
    elif args.task == "x":
        print(x_draft(args.topic, args.context, args.style))
    elif args.task == "reply":
        print(engagement_reply(args.tweet, args.author, args.context))
    elif args.task == "memory":
        print(memory_summary(args.content, args.category))
    elif args.task == "query":
        print(query_expansion(args.text, args.context))
    elif args.task == "web":
        print(web_summary(args.content, args.max_length))
    elif args.task == "health":
        try:
            resp = requests.get("http://localhost:1234/v1/models", timeout=5)
            if resp.status_code == 200:
                print("✅ Local LLM available")
                models = resp.json().get("data", [])
                for m in models:
                    print(f"   Model: {m.get('id')}")
            else:
                print(f"❌ LLM returned {resp.status_code}")
        except Exception as e:
            print(f"❌ LLM not available: {e}")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
