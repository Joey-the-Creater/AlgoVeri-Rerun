import Mathlib

-- Precondition definitions
@[reducible, simp]
def binary_search_lower_bound_precond (seq : Array Int) (target : Int) : Prop :=
  -- !benchmark @start precond
  seq.size ≤ 0x7FFFFFFF ∧
  (∀ i j : Nat, i < j ∧ j < seq.size → seq.getD i 0 ≤ seq.getD j 0)
  -- !benchmark @end precond

-- !benchmark @start auxcode
-- !benchmark @end auxcode

-- Main function definitions
def binary_search_lower_bound (seq : Array Int) (target : Int) (h_precond : binary_search_lower_bound_precond seq target) : Nat :=
  -- !benchmark @start code
  sorry
  -- !benchmark @end code

-- Postcondition definitions
@[reducible, simp]
def binary_search_lower_bound_postcond (seq : Array Int) (target : Int) (result : Nat) (h_precond : binary_search_lower_bound_precond seq target) : Prop :=
  -- !benchmark @start postcond
  result ≤ seq.size ∧
  (∀ i : Nat, i < result → seq.getD i 0 < target) ∧
  (∀ i : Nat, result ≤ i ∧ i < seq.size → seq.getD i 0 ≥ target)
  -- !benchmark @end postcond

-- !benchmark @start lemma
-- !benchmark @end lemma

-- Proof content
theorem binary_search_lower_bound_postcond_satisfied (seq : Array Int) (target : Int) (h_precond : binary_search_lower_bound_precond seq target) :
    binary_search_lower_bound_postcond seq target (binary_search_lower_bound seq target h_precond) h_precond := by
  -- !benchmark @start proof
  sorry
  -- !benchmark @end proof
