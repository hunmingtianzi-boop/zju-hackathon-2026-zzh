#!/bin/bash
set -e

# Build search index if not exists
if [ ! -f medical_index_faiss.index ]; then
    echo "Building medical search index..."
    python search_engine.py
fi

# Export frontend data
python kia_agent.py export

# Start a simple HTTP server for RAG API
echo "Starting KIA backend on :8000"
python -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
import json, sys
sys.path.insert(0, '.')
from rag_query import rag_query

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/api/rag':
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            result = rag_query(body.get('question', ''), body.get('top_k', 5))
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode())
        else:
            self.send_response(404)
            self.end_headers()
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

HTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
"
