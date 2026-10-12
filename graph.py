"""
graph.py
========
Core Data Structures & Algorithms Engine for the Urban Disaster
Evacuation & Smart Traffic Router.

DSA CONCEPTS DEMONSTRATED (for examiner reference)
---------------------------------------------------
1. GRAPH REPRESENTATION -> Adjacency List
   - The road network is a weighted, undirected graph G = (V, E).
   - We store it as a dictionary mapping each node -> list of Edge objects.
   - Space Complexity: O(V + E)  (one list-slot per vertex, one Edge per
     endpoint of every edge, i.e. 2E entries for an undirected graph).
   - This is chosen over an Adjacency MATRIX (O(V^2) space) because real
     road networks are SPARSE (each intersection connects to only a
     handful of others), so V + E << V^2 for realistic city maps.

2. PATHFINDING ENGINE -> Dijkstra's Algorithm with a Binary Min-Heap
   - We use Python's `heapq` module as a Priority Queue (binary min-heap).
   - Time Complexity: O((V + E) log V)
     * Each vertex is popped from the heap once:      O(V log V)
     * Each edge can trigger one heap push (relax):   O(E log V)
     * Total: O((V + E) log V)
   - This beats the naive O(V^2) array-based Dijkstra for sparse graphs
     (which is exactly the topology of a road network).

3. DYNAMIC HAZARD ADJUSTMENTS
   - Each Edge stores a `base_weight`, a `blocked` flag, and a
     `hazard_multiplier`. The EFFECTIVE weight used by Dijkstra is
     computed on the fly: effective_weight = base_weight * hazard_multiplier
     (or math.inf if blocked). This means hazard injection does NOT
     require rebuilding the graph -- only recomputation of the shortest
     path tree, which is exactly what real-time re-routing needs.

4. MULTI-DESTINATION ROUTING
   - Rather than running Dijkstra once per shelter (O(k * (V+E) log V)),
     we run a SINGLE Dijkstra pass from the start node across the whole
     graph, then simply pick the minimum-cost shelter from the resulting
     distance table. This is O((V+E) log V) regardless of shelter count.
"""

import heapq
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Edge:
    """
    Represents one directed link in the adjacency list.
    An undirected road is modeled as TWO Edge objects (one per direction),
    both sharing the same `edge_id` so the UI can toggle them together.
    """
    edge_id: str          # shared id for both directions of a road, e.g. "A-B"
    to_node: str           # destination intersection id
    base_weight: float     # nominal travel time / distance (minutes)
    blocked: bool = False          # hard blockage (impassable)
    hazard_multiplier: float = 1.0  # >1.0 = risk penalty (flood, fire, debris)

    def effective_weight(self) -> float:
        """
        Returns the LIVE cost of traversing this road right now.
        This is the single function that makes the router 'dynamic':
        Dijkstra always calls this instead of reading base_weight directly.
        """
        if self.blocked:
            return math.inf
        return self.base_weight * self.hazard_multiplier


class Graph:
    """
    Weighted graph stored as an Adjacency List: Dict[node_id -> List[Edge]].
    """

    def __init__(self) -> None:
        self.adjacency: Dict[str, List[Edge]] = {}
        self.node_meta: Dict[str, dict] = {}   # x, y, label, type (normal/shelter)

    # ---------------------------------------------------------------
    # Graph construction
    # ---------------------------------------------------------------
    def add_node(self, node_id: str, **meta) -> None:
        if node_id not in self.adjacency:
            self.adjacency[node_id] = []
        self.node_meta[node_id] = meta

    def add_edge(self, node_a: str, node_b: str, weight: float,
                 edge_id: Optional[str] = None) -> str:
        """
        Adds an undirected road between node_a and node_b by inserting
        two Edge objects (a->b and b->a) that share one edge_id, so the
        UI can toggle 'blocked' on the road as a single logical unit.
        """
        if edge_id is None:
            edge_id = f"{node_a}-{node_b}"
        self.adjacency.setdefault(node_a, []).append(
            Edge(edge_id=edge_id, to_node=node_b, base_weight=weight))
        self.adjacency.setdefault(node_b, []).append(
            Edge(edge_id=edge_id, to_node=node_a, base_weight=weight))
        return edge_id

    def edges_for(self, edge_id: str) -> List[Edge]:
        """Return both directional Edge objects that make up one road."""
        result = []
        for edges in self.adjacency.values():
            for e in edges:
                if e.edge_id == edge_id:
                    result.append(e)
        return result

    def set_blocked(self, edge_id: str, blocked: bool) -> None:
        for e in self.edges_for(edge_id):
            e.blocked = blocked

    def set_hazard(self, edge_id: str, multiplier: float) -> None:
        for e in self.edges_for(edge_id):
            e.hazard_multiplier = multiplier

    def all_edge_ids(self) -> List[str]:
        seen = set()
        for edges in self.adjacency.values():
            for e in edges:
                seen.add(e.edge_id)
        return sorted(seen)

    # ---------------------------------------------------------------
    # DIJKSTRA'S ALGORITHM (Priority Queue / Min-Heap implementation)
    # ---------------------------------------------------------------
    def dijkstra(self, start: str) -> Tuple[Dict[str, float], Dict[str, Optional[str]], int, float]:
        """
        Single-source shortest path using a binary min-heap priority queue.

        Returns:
            distances    : Dict[node_id -> shortest cost from start]
            predecessors : Dict[node_id -> previous node on shortest path]
            visited_count: number of nodes POPPED (finalized) from the heap
                           -- this is the metric shown on the Analytics Panel
            elapsed_ms   : wall-clock execution time in milliseconds

        ALGORITHM WALKTHROUGH:
        1. Initialize dist[start] = 0, all others = infinity.
        2. Push (0, start) onto the min-heap.
        3. While heap is not empty:
             a. Pop the node with the SMALLEST tentative distance -> O(log V)
             b. If we've already finalized it (stale heap entry), skip.
             c. "Relax" every outgoing edge: if going through the current
                node gives a shorter path to a neighbor, update it and
                push the neighbor back onto the heap -> O(log V) per push.
        4. When the heap empties, `distances` holds the true shortest cost
           to every reachable node, and `predecessors` lets us reconstruct
           the actual path by walking backwards from any destination.
        """
        start_time = time.perf_counter()

        distances: Dict[str, float] = {node: math.inf for node in self.adjacency}
        predecessors: Dict[str, Optional[str]] = {node: None for node in self.adjacency}
        distances[start] = 0.0

        # The Min-Heap (Priority Queue). Each entry: (tentative_distance, node_id)
        # heapq is a BINARY HEAP -> pop-min and push are both O(log n).
        min_heap: List[Tuple[float, str]] = [(0.0, start)]
        finalized = set()
        visited_count = 0  # number of nodes we pop-and-finalize (for the demo/report)

        while min_heap:
            current_dist, current_node = heapq.heappop(min_heap)

            if current_node in finalized:
                # Stale entry (we already found a better path earlier) -> skip.
                continue
            finalized.add(current_node)
            visited_count += 1

            # Relax every edge leaving current_node using its LIVE effective weight
            for edge in self.adjacency.get(current_node, []):
                weight = edge.effective_weight()
                if weight == math.inf:
                    continue  # road is blocked -- cannot traverse
                candidate = current_dist + weight
                if candidate < distances[edge.to_node]:
                    distances[edge.to_node] = candidate
                    predecessors[edge.to_node] = current_node
                    heapq.heappush(min_heap, (candidate, edge.to_node))

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return distances, predecessors, visited_count, elapsed_ms

    def shortest_path_to_nearest_shelter(
        self, start: str, shelters: List[str]
    ) -> Tuple[Optional[List[str]], float, int, float]:
        """
        Multi-destination routing: one Dijkstra pass from `start`, then pick
        the cheapest reachable shelter. This is the O((V+E) log V) approach
        described in the module docstring (point 4).

        Returns: (path_as_list_of_nodes, total_cost, visited_count, elapsed_ms)
                 path is None if no shelter is reachable.
        """
        distances, predecessors, visited_count, elapsed_ms = self.dijkstra(start)

        best_shelter, best_cost = None, math.inf
        for shelter in shelters:
            d = distances.get(shelter, math.inf)
            if d < best_cost:
                best_cost, best_shelter = d, shelter

        if best_shelter is None or best_cost == math.inf:
            return None, math.inf, visited_count, elapsed_ms

        # Reconstruct path by walking predecessors backwards from the shelter.
        path = []
        node = best_shelter
        while node is not None:
            path.append(node)
            node = predecessors[node]
        path.reverse()

        return path, best_cost, visited_count, elapsed_ms


def load_graph_from_json(data: dict) -> Graph:
    """Builds a Graph object from the parsed map_data.json structure."""
    g = Graph()
    for node in data["nodes"]:
        g.add_node(node["id"], x=node["x"], y=node["y"],
                   label=node.get("label", node["id"]),
                   type=node.get("type", "normal"))
    for edge in data["edges"]:
        g.add_edge(edge["from"], edge["to"], edge["weight"])
    return g
