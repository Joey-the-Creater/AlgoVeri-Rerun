from pathlib import Path
import sys

from src.verifiers.lean_verifier import LeanVerifier

code = """import Mathlib

structure TopoGraph where
  adj : Array (Array Nat)

def TopoGraph.well_formed (g : TopoGraph) : Prop :=
  ∀ u, u < g.adj.size →
    ∀ v, v ∈ g.adj.getD u #[] → v < g.adj.size

def TopoGraph.size (g : TopoGraph) : Nat :=
  g.adj.size

def TopoGraph.has_edge (g : TopoGraph) (u v : Nat) : Prop :=
  u < g.adj.size ∧
  v ∈ g.adj.getD u #[]

def TopoGraph.is_path (g : TopoGraph) (p : List Nat) : Prop :=
  p.length > 0 ∧
  ∀ i, i + 1 < p.length →
    g.has_edge (p.getD i 0) (p.getD (i + 1) 0)

def TopoGraph.is_cycle (g : TopoGraph) (p : List Nat) : Prop :=
  g.is_path p ∧ p.length > 1 ∧ p.head? = p.getLast?

def TopoGraph.graph_has_cycle (g : TopoGraph) : Prop :=
  ∃ p, g.is_cycle p

def TopoGraph.is_topological_ordering (g : TopoGraph) (order : Array Nat) : Prop :=
  -- Contains all nodes (size check + surjective)
  order.size = g.size ∧
  (∀ n, n < g.size → ∃ k, k < order.size ∧ order.getD k 0 = n) ∧
  -- No duplicates is implied by size check + surjective on finite set, but for completeness:
  (∀ i j, i < order.size → j < order.size → i ≠ j → order.getD i 0 ≠ order.getD j 0) ∧
  -- No back edges (if j < i, no edge order[i] -> order[j])
  (∀ i j, j < i → i < order.size →
     ¬ g.has_edge (order.getD i 0) (order.getD j 0))

-- Precondition definitions
@[reducible, simp]
def topological_sort_precond (graph : TopoGraph) : Prop :=
  -- !benchmark @start precond
  graph.well_formed
  -- !benchmark @end precond

-- !benchmark @start auxcode
-- !benchmark @end auxcode

-- Main function definition
def topological_sort (graph : TopoGraph)
    (h_precond : topological_sort_precond graph) : Option (Array Nat) :=
  -- !benchmark @start code
  sorry
  -- !benchmark @end code

-- Postcondition definitions
@[reducible, simp]
def topological_sort_postcond (graph : TopoGraph) (result : Option (Array Nat))
    (_ : topological_sort_precond graph) : Prop :=
  -- !benchmark @start postcond
  match result with
  | some order =>
      ¬ graph.graph_has_cycle ∧
      graph.is_topological_ordering order
  | none =>
      graph.graph_has_cycle
  -- !benchmark @end postcond

-- !benchmark @start lemma
-- !benchmark @end lemma

-- Proof content
theorem topological_sort_postcond_satisfied (graph : TopoGraph)
    (h_precond : topological_sort_precond graph) :
    topological_sort_postcond graph (topological_sort graph h_precond) h_precond := by
  -- !benchmark @start proof
  sorry
  -- !benchmark @end proof

"""

def test_lean_verifier_writes_file_and_returns_result():
    """Verify that LeanVerifier writes the source file and returns a result dict.

    This test uses `test/config_test.yaml` (created as part of the test suite).
    """
    cfg_path = Path(__file__).resolve().parent / "config_test.yaml"
    verifier = LeanVerifier(config_path=str(cfg_path))

    # If the test is invoked with piped stdin, prefer that content as the
    # sample source. We only read stdin when it's not a TTY to avoid blocking
    # interactive runs.
    stdin_data = None
    try:
        if not sys.stdin.isatty():
            stdin_data = sys.stdin.read()
    except Exception:
        stdin_data = None

    sample_source = stdin_data if (stdin_data is not None and stdin_data.strip() != "") else code
    result = verifier.verify(source=sample_source, spec="dummy-spec", filename="unit_test")

    print(result)

    assert isinstance(result, dict)
    assert "ok" in result and isinstance(result["ok"], bool)
    assert "file" in result

    # The file should have been created on disk
    written = Path(result["file"])
    assert written.exists()
    return
    # cleanup artifact
    try:
        written.unlink()
    except Exception:
        pass

if __name__ == '__main__':
    test_lean_verifier_writes_file_and_returns_result()
