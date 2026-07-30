// Following is the block for necessary definitions
// <preamble>
// Define Option datatype since it is not built-in
datatype Option<T> = Some(value: T) | None

datatype Graph = Graph(adj: seq<seq<int>>)

// Helper predicates/functions for the Graph datatype
ghost predicate well_formed(g: Graph) {
  forall u: int, i: int :: 
    0 <= u < |g.adj| && 0 <= i < |g.adj[u]| 
    ==> 
    0 <= g.adj[u][i] < |g.adj|
}

ghost function size(g: Graph): int {
  |g.adj|
}

// --- Graph Theory Definitions ---

ghost predicate has_edge(g: Graph, u: int, v: int) {
  exists i: int :: 
    0 <= u < |g.adj| 
    && 0 <= i < |g.adj[u]| 
    && g.adj[u][i] == v
}

ghost predicate is_path(g: Graph, p: seq<int>) {
  |p| > 0 &&
  (forall i: int :: 0 <= i < |p| - 1 
      ==> has_edge(g, p[i], p[i+1]))
}

// 3. Reachability
ghost predicate reachable(g: Graph, start: int, end: int) {
  exists p: seq<int> {:trigger is_path(g, p)} :: 
    is_path(g, p) 
    && p[0] == start 
    && p[|p| - 1] == end
}

// 4. Shortest Path
ghost predicate is_shortest_distance(g: Graph, start: int, end: int, d: int) {
  && (exists p: seq<int> {:trigger is_path(g, p)} :: 
        is_path(g, p) 
        && p[0] == start 
        && p[|p| - 1] == end 
        && |p| == d + 1
     )
  && (forall p: seq<int> :: 
        is_path(g, p) && p[0] == start && p[|p| - 1] == end 
        ==> |p| >= d + 1
     )
}
// </preamble>

// Following is the block for potential helper specifications
// <helpers>

// </helpers>

// Following is the block for proofs of lemmas
// <proofs>

// </proofs>

// Following is the block for the main specification
// <spec>
// Breadth First Search (Shortest Path)
method bfs_shortest_path(graph: Graph, start: int, target: int) returns (res: Option<int>)
  requires well_formed(graph)
  requires size(graph) <= 10000
  requires 0 <= start < size(graph)
  requires 0 <= target < size(graph)
  ensures match res {
    case Some(dist) => is_shortest_distance(graph, start, target, dist)
    case None => !reachable(graph, start, target)
  }
// </spec>
// <code>
{
    // Implement and verify the BFS algorithm to find the shortest path in the graph
}
// </code>