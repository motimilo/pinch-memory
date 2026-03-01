#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["lancedb>=0.5.0", "pandas>=2.0.0"]
# ///
import sys
sys.path.insert(0, '.')
from memory_graph import get_db

db = get_db()
table = db.open_table('memories')
df = table.to_pandas()
goals = df[df['category'] == 'goals']
print(f'Goals in DB: {len(goals)}')
for _, row in goals.iterrows():
    print(f'  - {row["content"][:70]}...')
