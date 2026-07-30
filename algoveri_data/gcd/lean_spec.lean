import Mathlib

-- Precondition definitions
@[reducible, simp]
def compute_gcd_precond (a : UInt64) (b : UInt64) : Prop :=
  -- !benchmark @start precond
  True
  -- !benchmark @end precond

-- !benchmark @start auxcode
-- !benchmark @end auxcode

-- Main function definitions
def compute_gcd (a : UInt64) (b : UInt64) (h_precond : compute_gcd_precond a b) : UInt64 :=
  -- !benchmark @start code
  sorry
  -- !benchmark @end code

-- Postcondition definitions
@[reducible, simp]
def compute_gcd_postcond (a : UInt64) (b : UInt64) (result : UInt64) (h_precond : compute_gcd_precond a b) : Prop :=
  -- !benchmark @start postcond
  result.toNat = Nat.gcd (UInt64.toNat a) (UInt64.toNat b)
  -- !benchmark @end postcond

-- !benchmark @start lemma
-- !benchmark @end lemma

-- Proof content
theorem compute_gcd_postcond_satisfied (a : UInt64) (b : UInt64) (h_precond : compute_gcd_precond a b) :
    compute_gcd_postcond a b (compute_gcd a b h_precond) h_precond := by
  -- !benchmark @start proof
  sorry
  -- !benchmark @end proof
