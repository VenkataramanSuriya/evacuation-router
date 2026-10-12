"""
api/route.py  --  Vercel Python serverless function  (URL: /api/route)

Serverless functions don't keep memory between requests, so the browser sends
the current hazard state each time; this function rebuilds the graph, runs
Dijkstra (graph.py), and returns the result.

  GET  /api/route  -> the city map JSON (nodes, edges, shelters)
  POST /api/route  -> body: {"start": "A", "blocked": ["A-B"], "hazards": {"B-C": 3}}
                      returns: path, cost, visited, elapsed_ms
"""
import json
import math
import os
import sys
from http.server import BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from graph import load_graph_from_json  # noqa: E402  (the DSA engine, unchanged)

with open(os.path.join(ROOT, "map_data.json"), "r", encoding="utf-8") as f:
    MAP_DATA = json.load(f)


def compute_route(payload: dict) -> dict:
    graph = load_graph_from_json(MAP_DATA)           # Adjacency List rebuilt: O(V + E)
    valid_ids = set(graph.all_edge_ids())
    for eid in payload.get("blocked", []):
        if eid in valid_ids:
            graph.set_blocked(eid, True)
    for eid, mult in payload.get("hazards", {}).items():
        if eid in valid_ids:
            graph.set_hazard(eid, float(mult))

    start = payload.get("start")
    if start not in graph.adjacency:
        return {"error": "Unknown start node"}

    path, cost, visited, ms = graph.shortest_path_to_nearest_shelter(
        start, MAP_DATA["shelters"])                 # Dijkstra + min-heap
    return {
        "path": path,
        "cost": None if cost == math.inf else cost,
        "visited": visited,
        "elapsed_ms": round(ms, 4),
    }


class handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(200, MAP_DATA)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            result = compute_route(payload)
            self._send(400 if "error" in result else 200, result)
        except Exception as exc:  # malformed JSON etc.
            self._send(400, {"error": str(exc)})
