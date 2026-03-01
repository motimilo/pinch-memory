#!/usr/bin/env python3
"""
PINCH Memory Web Viewer (API-based)
Uses the memory server API at 5112 instead of loading model directly.
"""

import json
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
from string import Template

MEMORY_API = "http://127.0.0.1:5112"

HTML_TEMPLATE = Template("""
<!DOCTYPE html>
<html>
<head>
    <title>PINCH Memory Viewer</title>
    <meta charset="utf-8">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
            background: #0a0a0a;
            color: #00ff88;
            padding: 20px;
            line-height: 1.6;
        }
        .header { border-bottom: 1px solid #00ff88; padding-bottom: 10px; margin-bottom: 20px; }
        .header h1 { font-size: 24px; }
        .header .stats { font-size: 12px; color: #888; margin-top: 5px; }
        .search { margin-bottom: 20px; }
        .search input {
            background: #1a1a1a; border: 1px solid #333; color: #00ff88;
            padding: 10px; width: 100%; max-width: 400px; font-family: inherit;
        }
        .search input:focus { outline: none; border-color: #00ff88; }
        .nav { margin-bottom: 20px; }
        .nav a { color: #00ff88; text-decoration: none; margin-right: 15px; padding: 5px 10px; border: 1px solid #333; }
        .nav a:hover, .nav a.active { background: #00ff88; color: #0a0a0a; }
        .memory-list { display: grid; gap: 10px; }
        .memory-item {
            background: #111; border: 1px solid #222; padding: 15px;
            cursor: pointer; transition: all 0.2s;
        }
        .memory-item:hover { border-color: #00ff88; }
        .memory-item .meta { font-size: 11px; color: #666; margin-bottom: 5px; }
        .memory-item .type {
            display: inline-block; padding: 2px 6px; background: #222;
            border-radius: 3px; font-size: 10px; text-transform: uppercase;
        }
        .memory-item .type.episodic { background: #1a3a1a; }
        .memory-item .type.semantic { background: #1a1a3a; }
        .memory-item .type.identity { background: #3a1a1a; }
        .memory-item .title { font-size: 14px; margin: 5px 0; }
        .memory-item .preview { font-size: 12px; color: #888; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .memory-detail { background: #111; border: 1px solid #00ff88; padding: 20px; max-width: 800px; }
        .memory-detail h2 { margin-bottom: 15px; font-size: 16px; }
        .memory-detail .content {
            white-space: pre-wrap; font-size: 13px; background: #0a0a0a;
            padding: 15px; border: 1px solid #222; max-height: 400px; overflow-y: auto;
        }
        .timeline { border-left: 2px solid #333; padding-left: 20px; margin-left: 10px; }
        .timeline-item { position: relative; padding-bottom: 20px; }
        .timeline-item::before {
            content: ''; position: absolute; left: -25px; top: 5px;
            width: 10px; height: 10px; background: #00ff88; border-radius: 50%;
        }
        .timeline-item .time { font-size: 11px; color: #666; }
        footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #222; font-size: 11px; color: #444; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🧠 PINCH Memory</h1>
        <div class="stats">$stats</div>
    </div>
    <div class="nav">
        <a href="/" class="$home_active">All</a>
        <a href="/?type=episodic" class="$episodic_active">Episodic</a>
        <a href="/?type=semantic" class="$semantic_active">Semantic</a>
        <a href="/?type=identity" class="$identity_active">Identity</a>
        <a href="/timeline" class="$timeline_active">Timeline</a>
        <a href="/graph" class="$graph_active">3D Graph</a>
    </div>
    <div class="search">
        <form method="GET" action="/">
            <input type="text" name="q" placeholder="Search memories..." value="$query">
        </form>
    </div>
    <div class="content">$content</div>
    <footer>PINCH Memory | $memory_count memories | $bond_count bonds</footer>
</body>
</html>
""")


def api_get(endpoint):
    """Call memory server API."""
    try:
        with urllib.request.urlopen(f"{MEMORY_API}{endpoint}", timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def api_search(query, category=None, limit=50):
    """Search memories via API (POST /query)."""
    try:
        data = json.dumps({"query": query or "recent memories and events", "limit": limit}).encode()
        req = urllib.request.Request(
            f"{MEMORY_API}/query",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            return result.get("memories", [])
    except Exception as e:
        return {"error": str(e)}


class ViewerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        query = params.get('q', [''])[0]
        memory_type = params.get('type', [None])[0]
        memory_id = params.get('id', [None])[0]
        
        # Get stats
        health = api_get("/health")
        stats_str = f"{health.get('memories', '?')} memories | {health.get('bonds', '?')} bonds"
        
        if memory_id:
            content = self.render_memory_detail(memory_id)
        elif parsed.path == '/timeline':
            content = self.render_timeline()
        elif parsed.path == '/graph':
            content = self.render_graph()
        else:
            content = self.render_memory_list(query, memory_type)
        
        html = HTML_TEMPLATE.substitute(
            stats=stats_str,
            query=query or '',
            content=content,
            memory_count=health.get('memories', '?'),
            bond_count=health.get('bonds', '?'),
            home_active='active' if not memory_type and parsed.path == '/' else '',
            episodic_active='active' if memory_type == 'episodic' else '',
            semantic_active='active' if memory_type == 'semantic' else '',
            identity_active='active' if memory_type == 'identity' else '',
            timeline_active='active' if parsed.path == '/timeline' else '',
            graph_active='active' if parsed.path == '/graph' else ''
        )
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode())
    
    def render_memory_list(self, query: str, memory_type: str) -> str:
        if query:
            # Use search for queries
            results = api_search(query, limit=100)
            if memory_type and isinstance(results, list):
                results = [r for r in results if r.get('memory_type', r.get('category', '')) == memory_type]
        else:
            # Use /list endpoint for browsing
            params = f"?limit=100"
            if memory_type:
                params += f"&type={memory_type}"
            data = api_get(f"/list{params}")
            if isinstance(data, dict) and 'error' in data:
                return f'<p>Error: {data["error"]}</p>'
            results = data.get('memories', [])
        
        if isinstance(results, dict) and 'error' in results:
            return f'<p>Error: {results["error"]}</p>'
        
        if not results:
            return '<p>No memories found.</p>'
        
        items = []
        for r in results:
            content = r.get('content', '')
            title = content.split('\n')[0][:60] if content else 'untitled'
            preview = ' '.join(content.split('\n')[1:3])[:100] if content else ''
            mtype = r.get('memory_type', r.get('category', 'unknown'))
            mid = r.get('id', '')
            
            items.append(f'''
            <div class="memory-item" onclick="location.href='/?id={mid}'">
                <div class="meta">
                    <span class="type {mtype}">{mtype}</span>
                    <span>strength: {r.get('strength', 0):.2f}</span>
                </div>
                <div class="title">{self.escape(title)}</div>
                <div class="preview">{self.escape(preview)}</div>
            </div>''')
        
        return f'<div class="memory-list">{"".join(items)}</div>'
    
    def render_memory_detail(self, memory_id: str) -> str:
        # Search for memory by content since we don't have direct ID lookup
        results = api_search('', limit=100)
        
        memory = None
        for r in results if isinstance(results, list) else []:
            if r.get('id') == memory_id:
                memory = r
                break
        
        if not memory:
            return '<p>Memory not found</p>'
        
        content = memory.get('content', '')
        mtype = memory.get('memory_type', memory.get('category', 'unknown'))
        
        return f'''
        <div class="memory-detail">
            <a href="/">← Back</a>
            <h2><span class="type {mtype}">{mtype}</span> {memory_id[:12]}...</h2>
            <div class="content">{self.escape(content)}</div>
        </div>'''
    
    def render_timeline(self) -> str:
        results = api_search('', limit=30)
        
        if isinstance(results, dict) and 'error' in results:
            return f'<p>Error: {results["error"]}</p>'
        
        if not results:
            return '<p>No memories found.</p>'
        
        # Sort by created_at
        results.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        items = []
        for r in results:
            content = r.get('content', '')
            title = content.split('\n')[0][:50] if content else 'untitled'
            mid = r.get('id', '')
            
            items.append(f'''
            <div class="timeline-item">
                <div class="time">{r.get('created_at', '')[:16]}</div>
                <div class="title"><a href="/?id={mid}">{self.escape(title)}</a></div>
            </div>''')
        
        return f'<div class="timeline">{"".join(items)}</div>'
    
    def render_graph(self) -> str:
        return '''
        <div style="width: 100%; height: calc(100vh - 200px); min-height: 500px;">
            <iframe src="http://localhost:5116/pinch_graph.html" 
                    style="width: 100%; height: 100%; border: 1px solid #333; border-radius: 8px;"
                    allowfullscreen></iframe>
        </div>
        <p style="margin-top: 10px; font-size: 11px; color: #666;">
            Click and drag to rotate • Scroll to zoom • Click a node to focus
        </p>'''
    
    def escape(self, text: str) -> str:
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    def log_message(self, format, *args):
        pass


def run_viewer(port: int = 5115):
    server = HTTPServer(('127.0.0.1', port), ViewerHandler)
    print(f"🧠 PINCH Memory Viewer running at http://localhost:{port}")
    server.serve_forever()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='PINCH Memory Web Viewer')
    parser.add_argument('--port', '-p', type=int, default=5115)
    args = parser.parse_args()
    run_viewer(args.port)
