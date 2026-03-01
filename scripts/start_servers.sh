#!/bin/bash
# PINCH Memory Servers Startup Script
# Starts embedding server (5111) and memory server (5112) if not running

LOG_DIR="$HOME/.openclaw/logs"
SCRIPT_DIR="$HOME/.openclaw/workspace/pinch-memory/scripts"

mkdir -p "$LOG_DIR"

# Check and start embedding server
if ! curl -s http://127.0.0.1:5111/health > /dev/null 2>&1; then
    echo "Starting embedding server..."
    cd "$SCRIPT_DIR" && nohup uv run embedding_server.py > "$LOG_DIR/embedding-server.log" 2>&1 &
    echo "Embedding server started (pid: $!)"
else
    echo "Embedding server already running"
fi

# Check and start memory server
if ! curl -s http://127.0.0.1:5112/health > /dev/null 2>&1; then
    echo "Starting memory server..."
    cd "$SCRIPT_DIR" && nohup uv run memory_server.py > "$LOG_DIR/memory-server.log" 2>&1 &
    echo "Memory server started (pid: $!)"
else
    echo "Memory server already running"
fi

# Check and start chat server (local LLM with memory)
if ! curl -s http://127.0.0.1:5113/health > /dev/null 2>&1; then
    echo "Starting chat server..."
    cd "$SCRIPT_DIR" && nohup uv run chat.py --serve > "$LOG_DIR/chat-server.log" 2>&1 &
    echo "Chat server started (pid: $!)"
else
    echo "Chat server already running"
fi

# Check and start auto-capture API
if ! curl -s http://127.0.0.1:5114/health > /dev/null 2>&1; then
    echo "Starting auto-capture API..."
    cd "$SCRIPT_DIR" && nohup uv run auto_capture.py --serve > "$LOG_DIR/auto-capture.log" 2>&1 &
    echo "Auto-capture API started (pid: $!)"
else
    echo "Auto-capture API already running"
fi

# Check and start web viewer
if ! curl -s http://127.0.0.1:5115 > /dev/null 2>&1; then
    echo "Starting web viewer..."
    cd "$SCRIPT_DIR" && nohup uv run web_viewer.py > "$LOG_DIR/web-viewer.log" 2>&1 &
    echo "Web viewer started (pid: $!)"
else
    echo "Web viewer already running"
fi

# Check and start 3D graph server
if ! curl -s http://127.0.0.1:5116 > /dev/null 2>&1; then
    echo "Starting 3D graph server..."
    EXPORT_DIR="$HOME/.openclaw/workspace/pinch-memory/exports"
    mkdir -p "$EXPORT_DIR"
    # Export fresh graph
    cd "$SCRIPT_DIR" && uv run graph_export.py --html > /dev/null 2>&1
    # Serve it
    cd "$EXPORT_DIR" && nohup python3 -m http.server 5116 > "$LOG_DIR/graph-server.log" 2>&1 &
    echo "3D graph server started (pid: $!)"
else
    echo "3D graph server already running"
fi

# Wait and verify
sleep 5

echo ""
echo "=== Server Status ==="
if curl -s http://127.0.0.1:5111/health > /dev/null 2>&1; then
    echo "✅ Embedding server: running"
else
    echo "❌ Embedding server: not responding"
fi

if curl -s http://127.0.0.1:5112/health > /dev/null 2>&1; then
    curl -s http://127.0.0.1:5112/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'✅ Memory server: {d[\"memories\"]} memories, {d[\"bonds\"]} bonds')"
else
    echo "❌ Memory server: not responding"
fi

if curl -s http://127.0.0.1:5113/health > /dev/null 2>&1; then
    curl -s http://127.0.0.1:5113/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'✅ Chat server: LLM={d[\"llm\"]}, Memory={d[\"memory\"]}')"
else
    echo "❌ Chat server: not responding (requires LM Studio running)"
fi

if curl -s http://127.0.0.1:5114/health > /dev/null 2>&1; then
    echo "✅ Auto-capture API: running"
else
    echo "❌ Auto-capture API: not responding"
fi

if curl -s http://127.0.0.1:5115 > /dev/null 2>&1; then
    echo "✅ Web viewer: http://localhost:5115"
else
    echo "❌ Web viewer: not responding"
fi

if curl -s http://127.0.0.1:5116 > /dev/null 2>&1; then
    echo "✅ 3D Graph: http://localhost:5116/pinch_graph.html"
else
    echo "❌ 3D Graph: not responding"
fi
