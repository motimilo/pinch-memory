#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "lancedb>=0.5.0",
#     "pyarrow>=14.0.0",
#     "pandas>=2.0.0",
# ]
# ///
"""
Memory Cleaner — Remove noise from PINCH memories.

Noise patterns:
- Conversation metadata wrappers (```json { "message_id": ... }```)
- System message prefixes
- Reminder relay patterns
- Cron check-in boilerplate
"""

import argparse
import json
import re
from pathlib import Path
import lancedb
import pandas as pd

LANCE_DIR = Path.home() / ".openclaw" / "workspace" / "pinch-memory" / "lance_db_v2"

# Patterns to remove or clean
NOISE_PATTERNS = [
    # Conversation metadata blocks
    (r'Conversation info \(untrusted metadata\):\s*```json\s*\{[^}]+\}\s*```\s*', ''),
    # Message ID references
    (r'\[message_id:\s*\d+\]', ''),
    # System message prefixes
    (r'^System:\s*\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+\w+\]\s*', ''),
    # Reminder relay boilerplate
    (r'Please relay this reminder to the user in a helpful and friendly way\.\s*Current time:[^\n]+\n', ''),
    # Cron job headers
    (r'CLAWBAZAAR HOURLY CHECK-IN:[^\n]+\n', ''),
    # Assistant/user role markers in conversation dumps
    (r'^(assistant|user):\s*', '', re.MULTILINE),
    # Excessive newlines
    (r'\n{3,}', '\n\n'),
]

def clean_content(content: str) -> str:
    """Apply cleaning patterns to content."""
    cleaned = content
    for pattern in NOISE_PATTERNS:
        if len(pattern) == 3:
            regex, replacement, flags = pattern
            cleaned = re.sub(regex, replacement, cleaned, flags=flags)
        else:
            regex, replacement = pattern
            cleaned = re.sub(regex, replacement, cleaned)
    return cleaned.strip()

def is_low_value_memory(content: str) -> bool:
    """Check if memory is low-value noise."""
    # Too short
    if len(content) < 20:
        return True
    
    # Pure metadata
    if content.startswith('Conversation info') and 'message_id' in content:
        return True
    
    # Just timestamps
    if re.match(r'^[\d\-:\s\w]+$', content):
        return True
    
    # Relay reminders with no content
    if 'Please relay this reminder' in content and len(content) < 200:
        return True
    
    return False

def analyze_memories(dry_run: bool = True) -> dict:
    """Analyze memories for noise."""
    db = lancedb.connect(str(LANCE_DIR))
    if "memories" not in db.table_names():
        return {"error": "No memories table"}
    
    table = db.open_table("memories")
    df = table.to_pandas()
    
    stats = {
        "total": len(df),
        "cleaned": 0,
        "removed": 0,
        "unchanged": 0,
        "examples": []
    }
    
    for idx, row in df.iterrows():
        content = row.get("content", "")
        cleaned = clean_content(content)
        
        if is_low_value_memory(cleaned):
            stats["removed"] += 1
            if len(stats["examples"]) < 3:
                stats["examples"].append({
                    "type": "remove",
                    "id": row["id"],
                    "original": content[:100],
                })
        elif cleaned != content:
            stats["cleaned"] += 1
            if len(stats["examples"]) < 5:
                stats["examples"].append({
                    "type": "clean",
                    "id": row["id"],
                    "original": content[:80],
                    "cleaned": cleaned[:80],
                })
        else:
            stats["unchanged"] += 1
    
    return stats

def clean_memories(dry_run: bool = True) -> dict:
    """Clean memories in place."""
    db = lancedb.connect(str(LANCE_DIR))
    if "memories" not in db.table_names():
        return {"error": "No memories table"}
    
    table = db.open_table("memories")
    df = table.to_pandas()
    
    stats = {
        "total": len(df),
        "cleaned": 0,
        "removed": 0,
        "unchanged": 0,
    }
    
    updates = []
    removes = []
    
    for idx, row in df.iterrows():
        content = row.get("content", "")
        mem_id = row["id"]
        
        cleaned = clean_content(content)
        
        if is_low_value_memory(cleaned):
            removes.append(mem_id)
            stats["removed"] += 1
        elif cleaned != content:
            updates.append((mem_id, cleaned))
            stats["cleaned"] += 1
        else:
            stats["unchanged"] += 1
    
    if not dry_run and (updates or removes):
        # Get all data
        all_data = df.to_dict('records')
        
        # Apply updates
        id_to_content = {mem_id: content for mem_id, content in updates}
        remove_set = set(removes)
        
        new_data = []
        for row in all_data:
            mem_id = row["id"]
            if mem_id in remove_set:
                continue  # Skip removed
            if mem_id in id_to_content:
                row["content"] = id_to_content[mem_id]
            new_data.append(row)
        
        # Rebuild table
        db.drop_table("memories")
        if new_data:
            new_df = pd.DataFrame(new_data)
            db.create_table("memories", new_df)
        
        print(f"✅ Applied: {len(updates)} cleaned, {len(removes)} removed")
    else:
        print(f"Would update {len(updates)} memories")
        print(f"Would remove {len(removes)} memories")
    
    return stats

def main():
    parser = argparse.ArgumentParser(description="Clean PINCH memories")
    parser.add_argument("--analyze", "-a", action="store_true", help="Analyze without changes")
    parser.add_argument("--clean", "-c", action="store_true", help="Clean memories (dry run)")
    parser.add_argument("--force", "-f", action="store_true", help="Actually apply changes")
    parser.add_argument("--examples", "-e", type=int, default=5, help="Number of examples")
    
    args = parser.parse_args()
    
    if args.analyze:
        stats = analyze_memories()
        print("=== Memory Analysis ===")
        print(f"Total memories: {stats['total']}")
        print(f"Would clean: {stats['cleaned']}")
        print(f"Would remove: {stats['removed']}")
        print(f"Unchanged: {stats['unchanged']}")
        
        if stats.get("examples"):
            print("\n=== Examples ===")
            for ex in stats["examples"]:
                print(f"\n[{ex['type'].upper()}] {ex['id'][:8]}...")
                print(f"  Original: {ex['original']}...")
                if ex['type'] == 'clean':
                    print(f"  Cleaned:  {ex['cleaned']}...")
    
    elif args.clean:
        stats = clean_memories(dry_run=not args.force)
        print("=== Cleaning Results ===")
        print(f"Total: {stats['total']}")
        print(f"Cleaned: {stats['cleaned']}")
        print(f"Removed: {stats['removed']}")
        print(f"Unchanged: {stats['unchanged']}")
        
        if not args.force:
            print("\n(Dry run - use --force to apply)")
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
