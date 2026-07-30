// Following is the block for necessary definitions
// <preamble>
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

// --- Basic Graph Definitions ---

ghost predicate has_edge(g: Graph, u: int, v: int) {
  exists i: int :: 
    0 <= u < |g.adj| 
    && 0 <= i < |g.adj[u]| 
    && g.adj[u][i] == v
}

// Bipartite (2-Coloring) Definitions
// A coloring is valid if no two connected nodes share the same color.
// We represent colors as booleans (false=ColorA, true=ColorB).
ghost predicate is_valid_coloring(g: Graph, colors: seq<bool>) {
  && |colors| == size(g)
  && (forall u: int, v: int :: 
        has_edge(g, u, v) 
        ==> 
        // In Dafny, we must ensure indices are within bounds for valid access
        0 <= u < |colors| && 0 <= v < |colors| && colors[u] != colors[v])
}

// Helper to state that a graph IS bipartite (exists some valid coloring)
ghost predicate is_bipartite(g: Graph) {
  exists colors: seq<bool> :: is_valid_coloring(g, colors)
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
// Bipartite Check (2-Coloring)
// Functional Correctness:
// - If Bipartite: Returns Some(colors).
// - If Not: Returns None.
method check_bipartite(graph: Graph) returns (res: Option<seq<bool>>)
  requires well_formed(graph)
  ensures match res {
    case Some(colors) => is_valid_coloring(graph, colors)
    case None => !is_bipartite(graph)
  }
// </spec>
// <code>
{
    // Implement and verify the function to check if a graph is bipartite 
}
// </code>