#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "sentence-transformers>=2.2.0",
#     "flask>=3.0.0",
# ]
# ///
"""
PINCH Embedding Server
Keeps the embedding model loaded in memory for fast queries.
Run: uv run embedding_server.py
"""

import json
from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer

app = Flask(__name__)
model = None

def get_model():
    global model
    if model is None:
        print("Loading embedding model...")
        model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        print("Model loaded!")
    return model

@app.route('/embed', methods=['POST'])
def embed():
    data = request.json
    text = data.get('text', '')
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    
    embedding = get_model().encode(text).tolist()
    return jsonify({'embedding': embedding})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'model_loaded': model is not None})

if __name__ == '__main__':
    # Preload model
    get_model()
    print("Starting embedding server on port 5111...")
    app.run(host='127.0.0.1', port=5111, threaded=True)
