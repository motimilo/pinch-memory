#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "networkx>=3.0",
#     "lancedb>=0.5.0",
#     "pyarrow>=14.0.0",
#     "scipy>=1.11.0",
# ]
# ///
"""
Core Concepts — Find the central ideas in PINCH memory using graph centrality.

Uses multiple algorithms:
- PageRank: What does everything flow toward?
- Betweenness: What bridges different clusters?
- Degree: What has the most connections?
- Eigenvector: What's connected to important things?
"""

import json
import argparse
from pathlib import Path
import networkx as nx
import lancedb

MEMORY_DIR = Path.home() / ".openclaw" / "workspace" / "pinch-memory"
GRAPH_FILE = MEMORY_DIR / "memory_graph.json"
LANCE_DIR = MEMORY_DIR / "lance_db_v2"

def load_graph() -> nx.Graph:
    if GRAPH_FILE.exists():
        data = json.loads(GRAPH_FILE.read_text())
        return nx.node_link_graph(data)
    return nx.Graph()

def get_memory_content(mem_id: str) -> dict:
    """Get memory content and metadata from LanceDB."""
    db = lancedb.connect(str(LANCE_DIR))
    if "memories" not in db.table_names():
        return {"content": "", "category": "unknown"}
    table = db.open_table("memories")
    results = table.search().where(f"id = '{mem_id}'").limit(1).to_list()
    if results:
        return {
            "content": results[0].get("content", "")[:200],
            "category": results[0].get("category", "unknown")
        }
    return {"content": "", "category": "unknown"}

def analyze_centrality(top_n: int = 10) -> dict:
    """Analyze graph centrality using multiple algorithms."""
    G = load_graph()
    
    if G.number_of_nodes() == 0:
        return {"error": "No nodes in graph"}
    
    results = {}
    
    # PageRank - what does everything flow toward?
    try:
        pagerank = nx.pagerank(G, weight="weight")
        results["pagerank"] = sorted(pagerank.items(), key=lambda x: -x[1])[:top_n]
    except:
        results["pagerank"] = []
    
    # Betweenness - what bridges clusters?
    try:
        betweenness = nx.betweenness_centrality(G, weight="weight")
        results["betweenness"] = sorted(betweenness.items(), key=lambda x: -x[1])[:top_n]
    except:
        results["betweenness"] = []
    
    # Degree centrality - what has most connections?
    try:
        degree = nx.degree_centrality(G)
        results["degree"] = sorted(degree.items(), key=lambda x: -x[1])[:top_n]
    except:
        results["degree"] = []
    
    # Eigenvector - connected to important things?
    try:
        eigen = nx.eigenvector_centrality(G, weight="weight", max_iter=500)
        results["eigenvector"] = sorted(eigen.items(), key=lambda x: -x[1])[:top_n]
    except:
        results["eigenvector"] = []
    
    return results

def find_core_concepts(top_n: int = 5) -> list[dict]:
    """Find the core concepts using combined centrality scores."""
    centrality = analyze_centrality(top_n=20)
    
    # Combine scores (normalize and average)
    combined_scores = {}
    
    for metric, scores in centrality.items():
        if not scores:
            continue
        max_score = max(s for _, s in scores) if scores else 1
        for mem_id, score in scores:
            if mem_id not in combined_scores:
                combined_scores[mem_id] = {"scores": {}, "total": 0}
            normalized = score / max_score if max_score > 0 else 0
            combined_scores[mem_id]["scores"][metric] = normalized
            combined_scores[mem_id]["total"] += normalized
    
    # Sort by combined score
    ranked = sorted(combined_scores.items(), key=lambda x: -x[1]["total"])[:top_n]
    
    # Enrich with memory content
    core_concepts = []
    for mem_id, data in ranked:
        mem = get_memory_content(mem_id)
        core_concepts.append({
            "id": mem_id,
            "content": mem["content"],
            "category": mem["category"],
            "combined_score": round(data["total"], 3),
            "scores": {k: round(v, 3) for k, v in data["scores"].items()}
        })
    
    return core_concepts

def print_core_concepts(concepts: list[dict]):
    """Pretty print core concepts."""
    print("=" * 60)
    print("CORE CONCEPTS — What Your Mind Orbits")
    print("=" * 60)
    print()
    
    for i, c in enumerate(concepts, 1):
        print(f"{i}. [{c['category'].upper()}] (score: {c['combined_score']:.2f})")
        print(f"   {c['content'][:150]}...")
        print(f"   Scores: {c['scores']}")
        print()

def get_cluster_cores(top_per_cluster: int = 2) -> dict:
    """Find core concepts within each semantic cluster using connected components."""
    G = load_graph()
    
    # Get cluster edges only
    cluster_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("type") == "cluster"]
    
    if not cluster_edges:
        return {}
    
    # Build subgraph and find connected components
    cluster_graph = G.edge_subgraph(cluster_edges)
    components = list(nx.connected_components(cluster_graph))
    
    # For each cluster, find central nodes
    cluster_cores = {}
    for i, nodes in enumerate(sorted(components, key=len, reverse=True)):
        if len(nodes) < 3:
            continue
        
        subgraph = G.subgraph(nodes)
        try:
            pagerank = nx.pagerank(subgraph, weight="weight")
            top_nodes = sorted(pagerank.items(), key=lambda x: -x[1])[:top_per_cluster]
            
            cluster_cores[f"cluster_{i+1}"] = {
                "size": len(nodes),
                "cores": [
                    {
                        "id": node_id,
                        "content": get_memory_content(node_id)["content"][:150],
                        "category": get_memory_content(node_id)["category"],
                        "score": round(score, 3)
                    }
                    for node_id, score in top_nodes
                ]
            }
        except:
            continue
    
    return cluster_cores

def main():
    parser = argparse.ArgumentParser(description="Find core concepts in PINCH memory")
    parser.add_argument("--top", "-n", type=int, default=5, help="Top N concepts")
    parser.add_argument("--clusters", "-c", action="store_true", help="Show cluster cores")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument("--raw", "-r", action="store_true", help="Show raw centrality scores")
    
    args = parser.parse_args()
    
    if args.raw:
        centrality = analyze_centrality(args.top)
        if args.json:
            print(json.dumps(centrality, indent=2))
        else:
            for metric, scores in centrality.items():
                print(f"\n{metric.upper()}:")
                for mem_id, score in scores[:5]:
                    mem = get_memory_content(mem_id)
                    print(f"  {score:.4f} [{mem['category']}] {mem['content'][:60]}...")
    elif args.clusters:
        cores = get_cluster_cores()
        if args.json:
            print(json.dumps(cores, indent=2))
        else:
            print(f"Found {len(cores)} clusters with cores\n")
            for cluster_id, data in list(cores.items())[:10]:
                print(f"📦 {cluster_id} (size: {data['size']})")
                for node in data["cores"]:
                    print(f"   [{node['category']}] {node['content'][:80]}...")
                print()
    else:
        concepts = find_core_concepts(args.top)
        if args.json:
            print(json.dumps(concepts, indent=2))
        else:
            print_core_concepts(concepts)

if __name__ == "__main__":
    main()
