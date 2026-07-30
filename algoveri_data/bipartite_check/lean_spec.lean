import Mathlib

structure BipartiteGraph where
  adj : Array (Array Nat)

def BipartiteGraph.well_formed (g : BipartiteGraph) : Prop :=
  ∀ u, u < g.adj.size →
    ∀ v, v ∈ g.adj.getD u #[] → v < g.adj.size

def BipartiteGraph.size (g : BipartiteGraph) : Nat :=
  g.adj.size

def BipartiteGraph.has_edge (g : BipartiteGraph) (u v : Nat) : Prop :=
  u < g.adj.size ∧
  v ∈ g.adj.getD u #[]

def BipartiteGraph.is_valid_coloring (g : BipartiteGraph) (colors : Array Bool) : Prop :=
  colors.size = g.size ∧
  ∀ u v, g.has_edge u v →
    u < colors.size → v < colors.size → colors.getD u false ≠ colors.getD v false

def BipartiteGraph.is_bipartite (g : BipartiteGraph) : Prop :=
  ∃ colors, g.is_valid_coloring colors

-- Precondition definitions
@[reducible, simp]
def check_bipartite_precond (graph : BipartiteGraph) : Prop :=
  -- !benchmark @start precond
  graph.well_formed
  -- !benchmark @end precond

-- !benchmark @start auxcode
-- !benchmark @end auxcode

-- Main function definition
def check_bipartite (graph : BipartiteGraph)
    (h_precond : check_bipartite_precond graph) : Option (Array Bool) :=
  -- !benchmark @start code
  sorry
  -- !benchmark @end code

-- Postcondition definitions
@[reducible, simp]
def check_bipartite_postcond (graph : BipartiteGraph) (result : Option (Array Bool))
    (_ : check_bipartite_precond graph) : Prop :=
  -- !benchmark @start postcond
  match result with
  | some colors => graph.is_valid_coloring colors
  | none => ¬ graph.is_bipartite
  -- !benchmark @end postcond

-- !benchmark @start lemma
-- !benchmark @end lemma

-- Proof content
theorem check_bipartite_postcond_satisfied (graph : BipartiteGraph)
    (h_precond : check_bipartite_precond graph) :
    check_bipartite_postcond graph (check_bipartite graph h_precond) h_precond := by
  -- !benchmark @start proof
  sorry
  -- !benchmark @end proof
