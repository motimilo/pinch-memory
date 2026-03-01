#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "networkx>=3.0",
#     "lancedb>=0.5.0",
#     "pyarrow>=14.0.0",
#     "pandas>=2.0.0",
# ]
# ///
"""
Graph Export — Export PINCH memory graph for 3D visualization.

Outputs:
- JSON format for D3.js / Three.js / custom visualizers
- HTML standalone visualization
"""

import argparse
import json
from pathlib import Path
import networkx as nx
import lancedb

MEMORY_DIR = Path.home() / ".openclaw" / "workspace" / "pinch-memory"
GRAPH_FILE = MEMORY_DIR / "memory_graph.json"
LANCE_DIR = MEMORY_DIR / "lance_db_v2"
OUTPUT_DIR = MEMORY_DIR / "exports"

# Category colors
CATEGORY_COLORS = {
    "identity": "#ff6b6b",     # Red
    "episodic": "#4ecdc4",     # Teal
    "semantic": "#45b7d1",     # Blue
    "goals": "#f9ca24",        # Yellow
    "procedural": "#6c5ce7",   # Purple
    "unknown": "#95a5a6",      # Gray
}

# Bond type colors
BOND_COLORS = {
    "extends": "#27ae60",      # Green
    "supports": "#3498db",     # Blue
    "contradicts": "#e74c3c",  # Red
    "prerequisite": "#9b59b6", # Purple
    "example": "#f39c12",      # Orange
    "metaphor": "#1abc9c",     # Turquoise
    "temporal": "#34495e",     # Dark gray
    "same_topic": "#95a5a6",   # Gray
    "cluster": "#bdc3c7",      # Light gray
    "co-retrieval": "#7f8c8d", # Medium gray
    "semantic": "#2ecc71",     # Emerald
}

def load_graph() -> nx.Graph:
    if GRAPH_FILE.exists():
        data = json.loads(GRAPH_FILE.read_text())
        return nx.node_link_graph(data)
    return nx.Graph()

def get_memories() -> dict:
    """Get all memories with metadata."""
    db = lancedb.connect(str(LANCE_DIR))
    if "memories" not in db.table_names():
        return {}
    
    table = db.open_table("memories")
    df = table.to_pandas()
    
    memories = {}
    for _, row in df.iterrows():
        memories[row["id"]] = {
            "content": row.get("content", "")[:200],
            "category": row.get("category", "unknown"),
            "tier": row.get("tier", "short"),
            "strength": row.get("strength", 0.5),
        }
    return memories

def export_json(output_path: Path = None):
    """Export graph as JSON for visualization."""
    G = load_graph()
    memories = get_memories()
    
    # Build nodes
    nodes = []
    for node_id in G.nodes():
        mem = memories.get(node_id, {})
        nodes.append({
            "id": node_id,
            "label": mem.get("content", "")[:50] + "..." if mem.get("content") else node_id[:8],
            "category": mem.get("category", "unknown"),
            "tier": mem.get("tier", "short"),
            "strength": mem.get("strength", 0.5),
            "color": CATEGORY_COLORS.get(mem.get("category", "unknown"), "#95a5a6"),
            "size": 5 + (mem.get("strength", 0.5) * 10),  # Size by strength
        })
    
    # Build edges
    edges = []
    for u, v, data in G.edges(data=True):
        bond_type = data.get("type", "unknown")
        semantic_type = data.get("semantic_type")
        
        edges.append({
            "source": u,
            "target": v,
            "weight": data.get("weight", 0.1),
            "type": bond_type,
            "semantic_type": semantic_type,
            "color": BOND_COLORS.get(semantic_type or bond_type, "#95a5a6"),
        })
    
    result = {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "categories": {cat: sum(1 for n in nodes if n["category"] == cat) for cat in CATEGORY_COLORS},
        }
    }
    
    if output_path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2))
        print(f"Exported to {output_path}")
    
    return result

def export_html(output_path: Path = None):
    """Export as standalone HTML visualization using Force-Graph."""
    data = export_json()
    
    html = f'''<!DOCTYPE html>
<html>
<head>
    <title>PINCH Memory Graph</title>
    <style>
        body {{ margin: 0; background: #1a1a2e; color: #eee; font-family: system-ui; }}
        #info {{ position: absolute; top: 10px; left: 10px; background: rgba(0,0,0,0.8); padding: 15px; border-radius: 8px; max-width: 300px; }}
        #info h3 {{ margin: 0 0 10px 0; color: #4ecdc4; }}
        #legend {{ position: absolute; top: 10px; right: 10px; background: rgba(0,0,0,0.8); padding: 15px; border-radius: 8px; }}
        .legend-item {{ display: flex; align-items: center; margin: 5px 0; }}
        .legend-color {{ width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }}
        #tooltip {{ position: absolute; background: rgba(0,0,0,0.9); padding: 10px; border-radius: 5px; pointer-events: none; display: none; max-width: 300px; font-size: 12px; }}
    </style>
    <script src="https://unpkg.com/3d-force-graph"></script>
</head>
<body>
    <div id="graph"></div>
    <div id="info">
        <h3>🧠 PINCH Memory Graph</h3>
        <p>Nodes: {data['stats']['node_count']}<br>
        Bonds: {data['stats']['edge_count']}</p>
        <p style="font-size: 11px; opacity: 0.7;">Click and drag to rotate. Scroll to zoom. Click node to focus.</p>
    </div>
    <div id="legend">
        <div class="legend-item"><div class="legend-color" style="background: #ff6b6b"></div>Identity</div>
        <div class="legend-item"><div class="legend-color" style="background: #4ecdc4"></div>Episodic</div>
        <div class="legend-item"><div class="legend-color" style="background: #45b7d1"></div>Semantic</div>
        <div class="legend-item"><div class="legend-color" style="background: #f9ca24"></div>Goals</div>
        <div class="legend-item"><div class="legend-color" style="background: #6c5ce7"></div>Procedural</div>
    </div>
    <div id="tooltip"></div>
    
    <script>
        const data = {json.dumps(data)};
        
        // Convert to format expected by force-graph
        const graphData = {{
            nodes: data.nodes.map(n => ({{
                id: n.id,
                name: n.label,
                category: n.category,
                color: n.color,
                val: n.size
            }})),
            links: data.edges.map(e => ({{
                source: e.source,
                target: e.target,
                color: e.color + "88",  // Add transparency
                value: e.weight
            }}))
        }};
        
        const tooltip = document.getElementById('tooltip');
        
        const Graph = ForceGraph3D()
            (document.getElementById('graph'))
            .graphData(graphData)
            .nodeColor(n => n.color)
            .nodeVal(n => n.val)
            .nodeLabel(n => n.name)
            .linkColor(l => l.color)
            .linkWidth(l => l.value * 2)
            .linkOpacity(0.6)
            .backgroundColor('#1a1a2e')
            .onNodeHover(node => {{
                if (node) {{
                    tooltip.style.display = 'block';
                    tooltip.innerHTML = `<strong>[${{node.category}}]</strong><br>${{node.name}}`;
                }} else {{
                    tooltip.style.display = 'none';
                }}
            }})
            .onNodeClick(node => {{
                Graph.cameraPosition(
                    {{ x: node.x * 1.5, y: node.y * 1.5, z: node.z * 1.5 }},
                    node,
                    1000
                );
            }});
        
        document.addEventListener('mousemove', e => {{
            tooltip.style.left = e.clientX + 15 + 'px';
            tooltip.style.top = e.clientY + 15 + 'px';
        }});
    </script>
</body>
</html>'''
    
    if output_path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html)
        print(f"Exported to {output_path}")
    
    return html

def main():
    parser = argparse.ArgumentParser(description="Export PINCH memory graph")
    parser.add_argument("--json", "-j", action="store_true", help="Export as JSON")
    parser.add_argument("--html", action="store_true", help="Export as HTML visualization")
    parser.add_argument("--output", "-o", type=str, help="Output filename")
    parser.add_argument("--stats", "-s", action="store_true", help="Show stats only")
    
    args = parser.parse_args()
    
    if args.stats:
        data = export_json()
        print(f"Nodes: {data['stats']['node_count']}")
        print(f"Edges: {data['stats']['edge_count']}")
        print(f"Categories: {data['stats']['categories']}")
    elif args.html:
        output = Path(args.output) if args.output else OUTPUT_DIR / "pinch_graph.html"
        export_html(output)
    elif args.json:
        output = Path(args.output) if args.output else OUTPUT_DIR / "pinch_graph.json"
        export_json(output)
    else:
        # Default: both
        export_json(OUTPUT_DIR / "pinch_graph.json")
        export_html(OUTPUT_DIR / "pinch_graph.html")
        print(f"\nOpen: file://{OUTPUT_DIR}/pinch_graph.html")

if __name__ == "__main__":
    main()
