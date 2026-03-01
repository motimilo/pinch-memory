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
Auto-Capture for PINCH Memory
Inspired by claude-mem's lifecycle hooks.

Automatically logs:
- Tool usage and results
- Session events (start, end)
- Significant outputs
- Errors and failures

Run as background service or call directly.
"""

import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

# Import memory_graph functions
try:
    from memory_graph import store, recall, get_stats
    HAS_MEMORY = True
except ImportError:
    HAS_MEMORY = False
    print("Warning: memory_graph not available", file=sys.stderr)


def hash_content(content: str) -> str:
    """Generate short hash for deduplication."""
    return hashlib.md5(content.encode()).hexdigest()[:8]


def capture_tool_use(tool_name: str, params: dict, result: str, 
                     success: bool = True, duration_ms: int = None) -> Optional[str]:
    """
    Capture a tool usage observation.
    
    Returns memory ID if stored, None if deduplicated/skipped.
    """
    if not HAS_MEMORY:
        return None
    
    # Skip noisy tools
    skip_tools = {'process', 'poll', 'list'}
    if tool_name.lower() in skip_tools:
        return None
    
    # Build observation
    timestamp = datetime.now().isoformat()
    status = "✓" if success else "✗"
    
    content = f"""[TOOL:{tool_name}] {status}
Params: {json.dumps(params, default=str)[:200]}
Result: {result[:500]}
Duration: {duration_ms}ms""" if duration_ms else f"""[TOOL:{tool_name}] {status}
Params: {json.dumps(params, default=str)[:200]}
Result: {result[:500]}"""
    
    # Check for recent duplicate
    content_hash = hash_content(f"{tool_name}:{json.dumps(params)}")
    recent = recall(tool_name, n=5, category='tool_use')
    
    for r in recent:
        if hash_content(r.get('content', ''))[:8] == content_hash[:8]:
            return None  # Skip duplicate
    
    # Store observation
    memory_id = store(
        content=content,
        category='tool_use',
        tags=[tool_name, 'auto_capture'],
        strength=0.3  # Start low, reinforce if accessed
    )
    
    return memory_id


def capture_session_event(event_type: str, details: dict = None) -> Optional[str]:
    """
    Capture session lifecycle events.
    
    Events: session_start, session_end, error, milestone
    """
    if not HAS_MEMORY:
        return None
    
    timestamp = datetime.now().isoformat()
    
    content = f"""[SESSION:{event_type.upper()}] {timestamp}
{json.dumps(details, indent=2, default=str) if details else ''}"""
    
    memory_id = store(
        content=content,
        memory_type='session_event',
        tags=[event_type, 'auto_capture'],
        strength=0.5 if event_type in ['error', 'milestone'] else 0.2
    )
    
    return memory_id


def capture_output(output_type: str, content: str, source: str = None) -> Optional[str]:
    """
    Capture significant outputs (PRs, commits, deployments, etc.)
    """
    if not HAS_MEMORY:
        return None
    
    if len(content) < 50:
        return None  # Skip trivial outputs
    
    timestamp = datetime.now().isoformat()
    
    memory_content = f"""[OUTPUT:{output_type.upper()}] {timestamp}
Source: {source or 'unknown'}
---
{content[:1000]}"""
    
    memory_id = store(
        content=memory_content,
        memory_type='output',
        tags=[output_type, 'auto_capture'],
        strength=0.6
    )
    
    return memory_id


def capture_error(error_type: str, message: str, context: dict = None) -> Optional[str]:
    """
    Capture errors for learning from failures.
    """
    if not HAS_MEMORY:
        return None
    
    timestamp = datetime.now().isoformat()
    
    content = f"""[ERROR:{error_type.upper()}] {timestamp}
Message: {message}
Context: {json.dumps(context, default=str)[:300] if context else 'none'}"""
    
    memory_id = store(
        content=content,
        memory_type='error',
        tags=[error_type, 'auto_capture', 'learn_from'],
        strength=0.8  # Errors are important to remember
    )
    
    return memory_id


def get_capture_stats() -> dict:
    """Get statistics on auto-captured memories."""
    if not HAS_MEMORY:
        return {'error': 'memory not available'}
    
    stats = get_stats()
    
    # Count by auto_capture tag
    # This is a simplified version - would need tag indexing for efficiency
    return {
        'total_memories': stats.get('total_memories', 0),
        'total_bonds': stats.get('total_bonds', 0),
        'capture_active': True
    }


# HTTP API for integration
def run_api(port: int = 5114):
    """Run simple HTTP API for auto-capture."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import urllib.parse
    
    class CaptureHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode()
            
            try:
                data = json.loads(body)
            except:
                self.send_error(400, 'Invalid JSON')
                return
            
            path = self.path.strip('/')
            result = None
            
            if path == 'tool':
                result = capture_tool_use(
                    data.get('tool'),
                    data.get('params', {}),
                    data.get('result', ''),
                    data.get('success', True),
                    data.get('duration_ms')
                )
            elif path == 'session':
                result = capture_session_event(
                    data.get('event'),
                    data.get('details')
                )
            elif path == 'output':
                result = capture_output(
                    data.get('type'),
                    data.get('content'),
                    data.get('source')
                )
            elif path == 'error':
                result = capture_error(
                    data.get('type'),
                    data.get('message'),
                    data.get('context')
                )
            else:
                self.send_error(404, 'Unknown endpoint')
                return
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'captured': result is not None,
                'memory_id': result
            }).encode())
        
        def do_GET(self):
            if self.path == '/health':
                stats = get_capture_stats()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(stats).encode())
            else:
                self.send_error(404)
        
        def log_message(self, format, *args):
            pass  # Suppress logging
    
    server = HTTPServer(('127.0.0.1', port), CaptureHandler)
    print(f"Auto-capture API running on http://127.0.0.1:{port}")
    print("Endpoints: POST /tool, /session, /output, /error | GET /health")
    server.serve_forever()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='PINCH Auto-Capture')
    parser.add_argument('--serve', action='store_true', help='Run HTTP API')
    parser.add_argument('--port', type=int, default=5114, help='API port')
    parser.add_argument('--tool', help='Capture tool usage')
    parser.add_argument('--event', help='Capture session event')
    parser.add_argument('--output', help='Capture output')
    parser.add_argument('--error', help='Capture error')
    parser.add_argument('--message', '-m', help='Content/message')
    
    args = parser.parse_args()
    
    if args.serve:
        run_api(args.port)
    elif args.tool:
        result = capture_tool_use(args.tool, {}, args.message or '', True)
        print(f"Captured: {result}")
    elif args.event:
        result = capture_session_event(args.event, {'message': args.message})
        print(f"Captured: {result}")
    elif args.output:
        result = capture_output(args.output, args.message or '')
        print(f"Captured: {result}")
    elif args.error:
        result = capture_error(args.error, args.message or '')
        print(f"Captured: {result}")
    else:
        parser.print_help()
