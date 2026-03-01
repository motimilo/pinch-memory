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
from memory_graph import get_db, set_strength, init_strength_db

init_strength_db()
db = get_db()
if 'memories' in db.table_names():
    table = db.open_table('memories')
    df = table.to_pandas()
    df = df[df['id'] != '__init__']
    
    synced = 0
    for _, row in df.iterrows():
        set_strength(row['id'], row.get('strength', 0.95), row.get('tier', 'short'), row.get('access_count', 0))
        synced += 1
    
    print(f'✅ Synced {synced} memories to strength tracker')
