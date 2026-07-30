import Mathlib

-- Precondition definitions
@[reducible, simp]
def matrix_multiply_precond (A B : List (List Nat)) : Prop :=
  -- !benchmark @start precond
  A.length > 0 ∧
  A.length ≤ 10 ∧ -- Aligned with Dafny/Verus (10)
  (∀ row, row ∈ A → row.length > 0) ∧
  (∀ row, row ∈ A → row.length ≤ 10) ∧
  (∀ i j, i < A.length → j < A.length → (A.getD i []).length = (A.getD j []).length) ∧
  
  -- Value Bounds (ADDED to match references)
  (∀ row, row ∈ A → ∀ val, val ∈ row → val ≤ 100) ∧
  (∀ row, row ∈ B → ∀ val, val ∈ row → val ≤ 100) ∧

  B.length > 0 ∧
  B.length ≤ 10 ∧
  (∀ row, row ∈ B → row.length > 0) ∧
  (∀ row, row ∈ B → row.length ≤ 10) ∧
  (∀ i j, i < B.length → j < B.length → (B.getD i []).length = (B.getD j []).length) ∧
  (A.getD 0 []).length = B.length
  -- !benchmark @end precond

-- !benchmark @start auxcode
-- !benchmark @end auxcode

-- Main function definitions
def matrix_multiply (A B : List (List Nat)) (h_precond : matrix_multiply_precond A B) : List (List Nat) :=
  -- !benchmark @start code
  sorry
  -- !benchmark @end code

def inner_product (row : List Nat) (col_idx : Nat) (B : List (List Nat)) : Nat :=
  (List.range row.length).foldl (fun acc k => acc + (row.getD k 0) * ((B.getD k []).getD col_idx 0)) 0

-- Postcondition definitions
@[reducible, simp]
def matrix_multiply_postcond (A B : List (List Nat)) (result : List (List Nat)) (h_precond : matrix_multiply_precond A B) : Prop :=
  -- !benchmark @start postcond
  result.length = A.length ∧
  (∀ row, row ∈ result → row.length = (B.getD 0 []).length) ∧
  (∀ i j, i < result.length → j < (result.getD 0 []).length →
    (result.getD i []).getD j 0 = inner_product (A.getD i []) j B)
  -- !benchmark @end postcond

-- !benchmark @start lemma
-- !benchmark @end lemma

-- Proof content
theorem matrix_multiply_postcond_satisfied (A B : List (List Nat))
    (h_precond : matrix_multiply_precond A B) :
    matrix_multiply_postcond A B (matrix_multiply A B h_precond) h_precond := by
  -- !benchmark @start proof
  sorry
  -- !benchmark @end proof