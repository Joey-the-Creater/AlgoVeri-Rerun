import Mathlib

-- Precondition definitions
@[reducible, simp]
def kmpSearch_precond (haystack : Array UInt8) (needle : Array UInt8) : Prop :=
  -- !benchmark @start precond
  haystack.size < 1000000 ∧ 
  needle.size < 1000000
  -- !benchmark @end precond

-- !benchmark @start auxcode
-- !benchmark @end auxcode

-- Main function definition
def kmpSearch (haystack : Array UInt8) (needle : Array UInt8)
    (_ : kmpSearch_precond haystack needle) : Array Nat :=
  -- !benchmark @start code
  sorry
  -- !benchmark @end code

-- Postcondition auxiliary definitions
def matchesAt (haystack needle : Array UInt8) (i : Nat) : Prop :=
  i + needle.size ≤ haystack.size ∧
  (∀ j, j < needle.size → haystack.getD (i + j) 0 = needle.getD j 0)

-- Postcondition definitions
@[reducible, simp]
def kmpSearch_postcond (haystack : Array UInt8) (needle : Array UInt8)
    (result : Array Nat) (_ : kmpSearch_precond haystack needle) : Prop :=
  -- !benchmark @start postcond
  (∀ i, i < result.size → matchesAt haystack needle (result.getD i 0)) ∧ -- Soundness
  (∀ i, matchesAt haystack needle i → ∃ k, k < result.size ∧ result.getD k 0 = i) -- Completeness
  -- !benchmark @end postcond

-- !benchmark @start lemma
-- !benchmark @end lemma

-- Proof content
theorem kmpSearch_postcond_satisfied (haystack : Array UInt8) (needle : Array UInt8)
    (h_precond : kmpSearch_precond haystack needle) :
    kmpSearch_postcond haystack needle (kmpSearch haystack needle h_precond) h_precond := by
  -- !benchmark @start proof
  sorry
  -- !benchmark @end proof