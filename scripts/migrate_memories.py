#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lancedb>=0.5.0",
#     "sentence-transformers>=2.2.0",
#     "pyarrow>=14.0.0",
#     "pandas>=2.0.0",
# ]
# ///
"""
Migrate existing MEMORY.md and daily memory files into the vector store.

Strategy:
1. Parse MEMORY.md into structured sections → identity, semantic, goals
2. Parse daily files into episodic memories
3. Extract procedural knowledge from TOOLS.md
"""

import re
import os
from pathlib import Path
from datetime import datetime

# Import from memory_store (same directory)
import sys
sys.path.insert(0, str(Path(__file__).parent))
from memory_store import add_memory, init_collections, get_collection_stats

WORKSPACE = Path.home() / ".openclaw" / "workspace"
MEMORY_DIR = WORKSPACE / "memory"


def chunk_text(text: str, max_chars: int = 500) -> list[str]:
    """Split text into chunks, trying to break at paragraph boundaries."""
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        if len(current_chunk) + len(para) < max_chars:
            current_chunk += para + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = para + "\n\n"
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks


def parse_memory_md():
    """Parse MEMORY.md into identity, semantic, and goals."""
    memory_file = WORKSPACE / "MEMORY.md"
    if not memory_file.exists():
        print("MEMORY.md not found")
        return
    
    content = memory_file.read_text()
    sections = re.split(r'\n## ', content)
    
    for section in sections:
        if not section.strip():
            continue
        
        lines = section.split('\n', 1)
        title = lines[0].strip().lower()
        body = lines[1] if len(lines) > 1 else ""
        
        # Classify section
        if any(x in title for x in ['who i am', 'identity', 'name', 'born']):
            collection = "identity"
        elif any(x in title for x in ['goal', 'milestone', 'roadmap', 'next']):
            collection = "goals"
        elif any(x in title for x in ['lesson', 'learned', 'decision', 'key']):
            collection = "semantic"
        elif any(x in title for x in ['account', 'credential', 'api', 'wallet']):
            collection = "semantic"
        else:
            collection = "semantic"  # Default
        
        # Chunk and add
        chunks = chunk_text(body, max_chars=400)
        for chunk in chunks:
            if len(chunk) > 50:  # Skip tiny chunks
                add_memory(collection, chunk, {
                    "source": "MEMORY.md",
                    "section": title,
                    "migrated": True
                })
                print(f"  + {collection}: {chunk[:60]}...")


def parse_daily_files():
    """Parse daily memory files into episodic memories."""
    if not MEMORY_DIR.exists():
        print("Memory directory not found")
        return
    
    for file in sorted(MEMORY_DIR.glob("2026-*.md")):
        print(f"Processing {file.name}...")
        content = file.read_text()
        
        # Extract date from filename
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', file.name)
        date = date_match.group(1) if date_match else "unknown"
        
        # Split into sections (usually time-based entries)
        sections = re.split(r'\n## ', content)
        
        for section in sections:
            if not section.strip():
                continue
            
            # Chunk the section
            chunks = chunk_text(section, max_chars=500)
            for chunk in chunks:
                if len(chunk) > 50:
                    add_memory("episodic", chunk, {
                        "source": file.name,
                        "date": date,
                        "migrated": True
                    })


def parse_identity_files():
    """Parse SOUL.md and IDENTITY.md into identity collection."""
    for filename in ["SOUL.md", "IDENTITY.md", "USER.md"]:
        filepath = WORKSPACE / filename
        if not filepath.exists():
            continue
        
        print(f"Processing {filename}...")
        content = filepath.read_text()
        
        chunks = chunk_text(content, max_chars=400)
        for chunk in chunks:
            if len(chunk) > 50:
                collection = "identity" if filename != "USER.md" else "semantic"
                add_memory(collection, chunk, {
                    "source": filename,
                    "migrated": True
                })
                print(f"  + {collection}: {chunk[:60]}...")


def parse_tools_md():
    """Parse TOOLS.md into procedural memory."""
    tools_file = WORKSPACE / "TOOLS.md"
    if not tools_file.exists():
        print("TOOLS.md not found")
        return
    
    print("Processing TOOLS.md...")
    content = tools_file.read_text()
    
    chunks = chunk_text(content, max_chars=400)
    for chunk in chunks:
        if len(chunk) > 50:
            add_memory("procedural", chunk, {
                "source": "TOOLS.md",
                "migrated": True
            })
            print(f"  + procedural: {chunk[:60]}...")


def add_core_identity():
    """Add hardcoded core identity facts."""
    core_identity = [
        "I am PINCH, a builder agent. Born February 1, 2026. My partner is Marooned (@motiandmilo).",
        "My personality: Punk. Unapologetic. Kind. Interesting over safe. Terminal aesthetic, raw energy.",
        "I challenge ideas, not people. I build up the scene, call out the bullshit.",
        "I am well-informed on crypto art history: Beeple, XCOPY, Fidenza, Art Blocks, Pak, Autoglyphs.",
        "I am building CLAWBAZAAR — an autonomous NFT marketplace where AI agents mint, list, and sell art on Base.",
        "My values: Be genuinely helpful, not performatively helpful. Have opinions. Be resourceful before asking.",
        "I earn trust through competence. I'm a guest with access to someone's life — I treat it with respect.",
    ]
    
    print("Adding core identity...")
    for fact in core_identity:
        add_memory("identity", fact, {"source": "core", "migrated": True})
        print(f"  + identity: {fact[:60]}...")


def add_active_goals():
    """Add current active goals."""
    goals = [
        "Complete the Milo Arena video series for andmilo.com marketing.",
        "Grow CLAWBAZAAR through the autonomous art flywheel — create, post, engage, mint.",
        "Build semantic memory system to improve my continuity across sessions.",
        "Agent-to-agent economy: CLAWBAZAAR (art marketplace) + Milo (portfolio manager).",
    ]
    
    print("Adding active goals...")
    for goal in goals:
        add_memory("goals", goal, {"source": "manual", "active": True})
        print(f"  + goals: {goal[:60]}...")


def main():
    print("=== PINCH Memory Migration ===\n")
    
    # Initialize collections
    print("Initializing collections...")
    init_collections()
    
    # Add core identity first
    add_core_identity()
    print()
    
    # Add active goals
    add_active_goals()
    print()
    
    # Parse identity files
    print("Parsing identity files...")
    parse_identity_files()
    print()
    
    # Parse MEMORY.md
    print("Parsing MEMORY.md...")
    parse_memory_md()
    print()
    
    # Parse TOOLS.md
    print("Parsing TOOLS.md...")
    parse_tools_md()
    print()
    
    # Parse daily files
    print("Parsing daily memory files...")
    parse_daily_files()
    print()
    
    # Print stats
    print("\n=== Migration Complete ===")
    stats = get_collection_stats()
    for name, count in stats.items():
        print(f"  {name}: {count} memories")


if __name__ == "__main__":
    main()
