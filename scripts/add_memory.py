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
"""Add a memory to PINCH graph. Usage: uv run add_memory.py --type semantic --content "..." [--tags a,b,c]"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from memory_graph import add_memory, load_graph

def main():
    parser = argparse.ArgumentParser(description='Add memory to PINCH')
    parser.add_argument('--content', '-c', required=True, help='Memory content')
    parser.add_argument('--category', '-t', default='episodic', choices=['episodic', 'semantic', 'identity', 'procedural'], help='Memory category')
    parser.add_argument('--tier', default='short', choices=['short', 'long', 'core'], help='Memory tier')
    parser.add_argument('--source', '-s', default='agent', help='Memory source')
    args = parser.parse_args()
    
    memory_id = add_memory(
        content=args.content,
        category=args.category,
        tier=args.tier,
        source=args.source
    )
    
    if memory_id:
        G = load_graph()
        print(f'✅ Memory added: {memory_id}')
        print(f'📊 Total: {len(G.nodes())} memories')
    else:
        print('⚠️ Memory skipped (low value content)')

if __name__ == '__main__':
    main()
