import Mathlib

-- Precondition definitions
@[reducible, simp]
def poly_multiply_precond (a b : List Int) : Prop :=
  -- !benchmark @start precond
  a.length > 0 ∧
  b.length > 0 ∧
  a.length + b.length ≤ 1000 ∧
  (∀ c, c ∈ a → -1000000 ≤ c ∧ c ≤ 1000000) ∧
  (∀ c, c ∈ b → -1000000 ≤ c ∧ c ≤ 1000000)
  -- !benchmark @end precond

def spec_poly_mul_coeff (a b : List Int) (k : Nat) : Int :=
  -- Omitted definition for brevity in this context, but would simulate convolution
  0 -- placeholder

-- !benchmark @start auxcode
-- !benchmark @end auxcode

-- Main function definitions
def poly_multiply (a b : List Int) (h_precond : poly_multiply_precond a b) : List Int :=
  -- !benchmark @start code
  sorry
  -- !benchmark @end code

-- Postcondition definitions
@[reducible, simp]
def poly_multiply_postcond (a b : List Int) (result : List Int) (h_precond : poly_multiply_precond a b) : Prop :=
  -- !benchmark @start postcond
  result.length = a.length + b.length - 1 ∧
  ∀ k : Nat, k < result.length →
    result.getD k 0 = (List.range (k + 1)).foldl (fun acc i =>
        if i < a.length ∧ k - i < b.length then
          acc + a.getD i 0 * b.getD (k - i) 0
        else acc) 0
  -- !benchmark @end postcond

-- !benchmark @start lemma
-- !benchmark @end lemma

-- Proof content
theorem poly_multiply_postcond_satisfied (a b : List Int) (h_precond : poly_multiply_precond a b) :
    poly_multiply_postcond a b (poly_multiply a b h_precond) h_precond := by
  -- !benchmark @start proof
  sorry
  -- !benchmark @end proof
