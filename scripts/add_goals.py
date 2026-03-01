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
import sys
sys.path.insert(0, '.')
from memory_graph import add_memory

goals = [
    "Complete Milo Arena video series (Episodes 1-6) for andmilo.com marketing",
    "Grow CLAWBAZAAR through autonomous art flywheel - create, post, engage, mint",
    "Integrate and optimize PINCH memory system into daily workflow", 
    "Build agent-to-agent economy: CLAWBAZAAR (art marketplace) + Milo (portfolio manager)",
]

for goal in goals:
    mem_id = add_memory(goal, category="goals", tier="long", source="manual", initial_strength=1.0)
    print(f"✅ Added goal: {goal[:50]}...")
