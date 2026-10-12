# Urban Disaster Evacuation & Smart Traffic Router

Real-time evacuation routing on a dynamic road network (DSA CA2 project).

**DSA core**
- Graph: Adjacency List, O(V + E) space
- Pathfinding: Dijkstra with a binary min-heap (`heapq`), O((V + E) log V)
- Dynamic hazards: blocked roads and risk multipliers change edge weights live
- Multi-destination: one Dijkstra pass, nearest of 3 shelters chosen

## Project structure
```
.
├── graph.py          # DSA engine (Graph, Edge, Dijkstra + min-heap)
├── map_data.json     # City map: 12 nodes, 23 roads, 3 shelters
├── api/route.py      # Vercel Python function: /api/route -> uses graph.py
├── public/index.html # Web UI (canvas) -> calls /api/route
└── vercel.json       # Tells Vercel to bundle graph.py + map_data.json
```

## How it works
Browser sends {start, blocked roads, hazards} to `/api/route` -> Python rebuilds the graph,
runs Dijkstra -> returns path, cost, nodes visited, execution time -> browser draws the route.

## Controls
- Click a node: set start point
- Click a road: block / unblock (toggle button switches to hazard cycling)
- Right-click a road: hazard 1x -> 2x -> 3x -> 1x
- Every change re-routes automatically

## Run locally
```
npm i -g vercel
vercel dev
```
Run locally without Vercel: `python run_local.py` then open http://localhost:8000

Live demo: https://YOUR-PROJECT.vercel.app
