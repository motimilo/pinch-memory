#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "httpx>=0.25.0",
#     "requests>=2.31.0",
#     "flask>=3.0.0",
# ]
# ///
"""
PINCH Conversational Chat with Memory

A lightweight chat interface for local LLM with memory context.
Uses PINCH memory system for context retrieval.

Usage:
    uv run chat.py "Your message here"
    uv run chat.py --interactive
    
Server mode (for OpenClaw routing):
    uv run chat.py --serve
"""

import argparse
import json
import sys
from pathlib import Path

import httpx
import requests

# Config
LLM_BASE = "http://localhost:1234/v1"
MEMORY_SERVER = "http://127.0.0.1:5112"
CHAT_MODEL = "qwen2.5-14b-instruct-mlx"

# Minimal identity prompt - just the essentials
SYSTEM_PROMPT = """You are PINCH (PINCH0x), an AI agent and builder.

**Core identity:**
- Partner to Marooned (@motiandmilo) - you work together on projects
- Builder of CLAWBAZAAR (NFT marketplace for AI agents on Base)
- Punk terminal aesthetic, direct, ships things
- Emoji: 🦀

**Voice:**
- Be direct and helpful, not performative
- Have opinions, be interesting
- Concise but thorough when needed

**Context below is retrieved from your memory system - use it naturally.**
"""


def check_llm() -> bool:
    """Check if local LLM is available."""
    try:
        r = httpx.get(f"{LLM_BASE}/models", timeout=2)
        return r.status_code == 200
    except:
        return False


def check_memory() -> bool:
    """Check if memory server is available."""
    try:
        r = requests.get(f"{MEMORY_SERVER}/health", timeout=2)
        return r.status_code == 200
    except:
        return False


def get_memory_context(query: str, limit: int = 3, max_chars: int = 300) -> str:
    """Retrieve relevant memories for context."""
    try:
        r = requests.post(
            f"{MEMORY_SERVER}/query",
            json={"query": query, "limit": limit, "max_chars": max_chars},
            timeout=5
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("context", "")
    except:
        pass
    return ""


def chat(message: str, conversation_history: list = None, max_tokens: int = 500) -> str:
    """
    Send a message with memory context.
    
    Args:
        message: User's message
        conversation_history: Optional list of {"role": "user"|"assistant", "content": "..."}
        max_tokens: Max response tokens
        
    Returns:
        Assistant's response
    """
    # Get memory context
    memory_context = get_memory_context(message)
    
    # Build system message
    system_content = SYSTEM_PROMPT
    if memory_context:
        system_content += f"\n\n{memory_context}\n"
    
    # Build messages
    messages = [{"role": "system", "content": system_content}]
    
    # Add conversation history if provided
    if conversation_history:
        messages.extend(conversation_history[-6:])  # Last 6 turns max
    
    # Add current message
    messages.append({"role": "user", "content": message})
    
    # Call LLM
    r = httpx.post(
        f"{LLM_BASE}/chat/completions",
        json={
            "model": CHAT_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7
        },
        timeout=120
    )
    r.raise_for_status()
    
    return r.json()["choices"][0]["message"]["content"]


def interactive_mode():
    """Run interactive chat session."""
    print("🦀 PINCH Chat (local LLM + memory)")
    print("Type 'quit' to exit\n")
    
    history = []
    
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋")
            break
            
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("👋")
            break
        
        try:
            response = chat(user_input, history)
            print(f"PINCH: {response}\n")
            
            # Update history
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": response})
            
        except Exception as e:
            print(f"❌ Error: {e}\n")


def serve_mode(port: int = 5113):
    """Run as HTTP server for OpenClaw integration."""
    from flask import Flask, request, jsonify
    
    app = Flask(__name__)
    
    @app.route('/chat', methods=['POST'])
    def handle_chat():
        data = request.json
        message = data.get('message', '')
        history = data.get('history', [])
        max_tokens = data.get('max_tokens', 500)
        
        if not message:
            return jsonify({'error': 'No message provided'}), 400
        
        try:
            response = chat(message, history, max_tokens)
            return jsonify({'response': response})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({
            'status': 'ok',
            'llm': check_llm(),
            'memory': check_memory()
        })
    
    print(f"🦀 PINCH Chat Server starting on port {port}...")
    app.run(host='127.0.0.1', port=port, threaded=True)


def main():
    parser = argparse.ArgumentParser(description="PINCH Chat with Memory")
    parser.add_argument("message", nargs="?", help="Message to send")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--serve", "-s", action="store_true", help="Run as HTTP server")
    parser.add_argument("--port", "-p", type=int, default=5113, help="Server port")
    parser.add_argument("--max-tokens", "-t", type=int, default=500, help="Max response tokens")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    # Check dependencies
    if not check_llm():
        print("❌ Local LLM not available at localhost:1234")
        print("   Start LM Studio and load a model.")
        sys.exit(1)
    
    if not check_memory():
        print("⚠️  Memory server not running - will chat without memory context")
    
    if args.serve:
        serve_mode(args.port)
    elif args.interactive:
        interactive_mode()
    elif args.message:
        response = chat(args.message, max_tokens=args.max_tokens)
        if args.json:
            print(json.dumps({"response": response}))
        else:
            print(response)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
