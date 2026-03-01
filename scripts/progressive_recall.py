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
"""
Progressive Disclosure for PINCH Memory
Inspired by claude-mem's 3-layer pattern.

Layer 1: search() - compact index with IDs (~50 tokens/result)
Layer 2: timeline() - chronological context around a result
Layer 3: get_full() - full memory details (~500 tokens/result)

10x token savings by filtering before fetching details.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))
from memory_graph import recall, get_db, load_graph


def search(query: str, memory_type: str = None, limit: int = 10, days: int = None) -> list:
    """
    Layer 1: Compact search results with IDs.
    Returns minimal info for filtering.
    
    ~50 tokens per result vs ~500 for full details.
    """
    results = recall(query, n=limit * 2, category=memory_type)
    
    compact = []
    for r in results[:limit]:
        # Extract first line as title
        content = r.get('content', '')
        title = content.split('\n')[0][:80] if content else 'untitled'
        
        compact.append({
            'id': r.get('id'),
            'type': r.get('memory_type', 'unknown'),
            'title': title,
            'strength': round(r.get('strength', 0), 2),
            'created': r.get('created_at', '')[:10],  # Just date
            'score': round(r.get('score', 0), 3)
        })
    
    return compact


def timeline(anchor_id: str = None, query: str = None, hours: int = 24) -> list:
    """
    Layer 2: Chronological context around an observation.
    Shows what was happening around a specific time.
    """
    db = get_db()
    if db is None:
        return []
    
    # Get anchor timestamp
    if anchor_id:
        anchor = db.get(anchor_id)
        if anchor:
            anchor_time = anchor.get('created_at', datetime.now().isoformat())
        else:
            return []
    else:
        anchor_time = datetime.now().isoformat()
    
    # Parse timestamp
    try:
        if isinstance(anchor_time, str):
            anchor_dt = datetime.fromisoformat(anchor_time.replace('Z', '+00:00'))
        else:
            anchor_dt = anchor_time
    except:
        anchor_dt = datetime.now()
    
    # Get memories in time range
    start = anchor_dt - timedelta(hours=hours/2)
    end = anchor_dt + timedelta(hours=hours/2)
    
    # Query all memories and filter by time
    results = recall(query or "", k=50)
    
    timeline_items = []
    for r in results:
        created = r.get('created_at', '')
        try:
            if isinstance(created, str):
                created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
            else:
                created_dt = created
            
            if start <= created_dt <= end:
                content = r.get('content', '')
                timeline_items.append({
                    'id': r.get('id'),
                    'type': r.get('memory_type', 'unknown'),
                    'title': content.split('\n')[0][:60],
                    'time': created[:16],  # Date + time
                    'is_anchor': r.get('id') == anchor_id
                })
        except:
            continue
    
    # Sort by time
    timeline_items.sort(key=lambda x: x.get('time', ''))
    
    return timeline_items


def get_full(ids: list) -> list:
    """
    Layer 3: Full memory details for specific IDs.
    Only call after filtering with search() and timeline().
    """
    db = get_db()
    if db is None:
        return []
    
    full_results = []
    for memory_id in ids:
        memory = db.get(memory_id)
        if memory:
            full_results.append({
                'id': memory_id,
                'type': memory.get('memory_type', 'unknown'),
                'content': memory.get('content', ''),
                'strength': memory.get('strength', 0),
                'created_at': memory.get('created_at', ''),
                'bonds': memory.get('bonds', [])[:5]  # Top 5 related
            })
    
    return full_results


def progressive_recall(query: str, auto_expand: bool = False) -> dict:
    """
    Full progressive disclosure workflow.
    
    Returns compact results by default.
    If auto_expand=True, automatically fetches top 3 full results.
    """
    # Layer 1: Search
    compact = search(query, limit=10)
    
    result = {
        'query': query,
        'count': len(compact),
        'compact': compact,
        'token_estimate': len(compact) * 50
    }
    
    if auto_expand and compact:
        # Layer 3: Get top 3 full details
        top_ids = [c['id'] for c in compact[:3] if c.get('id')]
        if top_ids:
            result['expanded'] = get_full(top_ids)
            result['token_estimate'] += len(result['expanded']) * 500
    
    return result


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Progressive memory recall')
    parser.add_argument('query', nargs='?', help='Search query')
    parser.add_argument('--timeline', '-t', help='Get timeline around memory ID')
    parser.add_argument('--get', '-g', nargs='+', help='Get full details for IDs')
    parser.add_argument('--expand', '-e', action='store_true', help='Auto-expand top results')
    parser.add_argument('--json', '-j', action='store_true', help='Output as JSON')
    
    args = parser.parse_args()
    
    if args.get:
        results = get_full(args.get)
    elif args.timeline:
        results = timeline(anchor_id=args.timeline, query=args.query)
    elif args.query:
        results = progressive_recall(args.query, auto_expand=args.expand)
    else:
        parser.print_help()
        sys.exit(1)
    
    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        if isinstance(results, dict):
            print(f"\n🔍 Query: {results.get('query')}")
            print(f"   Found: {results.get('count')} results")
            print(f"   Est. tokens: ~{results.get('token_estimate')}")
            print("\n--- Compact Results ---")
            for r in results.get('compact', []):
                print(f"  [{r['id'][:8]}] {r['type']:10} | {r['title']}")
            
            if 'expanded' in results:
                print("\n--- Expanded (top 3) ---")
                for r in results.get('expanded', []):
                    print(f"\n  [{r['id'][:8]}] {r['type']}")
                    print(f"  {r['content'][:200]}...")
        else:
            for r in results:
                print(f"  [{r.get('id', '?')[:8]}] {r.get('title', r.get('content', '')[:50])}")
