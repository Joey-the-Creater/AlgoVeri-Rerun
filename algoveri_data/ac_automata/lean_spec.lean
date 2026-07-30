import Mathlib

-- Precondition definitions
@[reducible, simp]
def ac_automata_search_precond (haystack : Array UInt8) (patterns : Array (Array UInt8)) : Prop :=
  -- !benchmark @start precond
  haystack.size < 1000000 ∧
  patterns.size > 0 ∧
  patterns.size < 1000000 ∧
  (∀ i : Nat, i < patterns.size → 
    let p := patterns.getD i #[]
    p.size < 1000000)
  -- !benchmark @end precond

-- !benchmark @start auxcode
-- !benchmark @end auxcode

-- Main function definitions
def ac_automata_search (haystack : Array UInt8) (patterns : Array (Array UInt8))
    (_ : ac_automata_search_precond haystack patterns) :
    Array (Nat × Nat) :=
  -- !benchmark @start code
  sorry
  -- !benchmark @end code

-- Postcondition auxiliary definitions
def matches_at (haystack : Array UInt8) (needle : Array UInt8) (start : Nat) : Prop :=
  start + needle.size ≤ haystack.size ∧
  (∀ i : Nat, i < needle.size → haystack.getD (start + i) 0 = needle.getD i 0)

-- Postcondition definitions
@[reducible, simp]
def ac_automata_search_postcond (haystack : Array UInt8) (patterns : Array (Array UInt8))
    (result : Array (Nat × Nat)) (_ : ac_automata_search_precond haystack patterns) : Prop :=
  -- !benchmark @start postcond
  (∀ i : Nat, i < result.size →
      let pair := result.getD i (0, 0)
      let pid := pair.fst
      let idx := pair.snd
      pid < patterns.size ∧
      -- Removed duplicate `pid < patterns.size` check
      matches_at haystack (patterns.getD pid #[]) idx) ∧
  (∀ pid idx : Nat,
      pid < patterns.size →
      matches_at haystack (patterns.getD pid #[]) idx →
      ∃ k : Nat, k < result.size ∧ result.getD k (0, 0) = (pid, idx))
  -- !benchmark @end postcond

-- !benchmark @start lemma
-- !benchmark @end lemma

-- Proof content
theorem ac_automata_search_postcond_satisfied (haystack : Array UInt8) (patterns : Array (Array UInt8))
    (h_precond : ac_automata_search_precond haystack patterns) :
    ac_automata_search_postcond haystack patterns
      (ac_automata_search haystack patterns h_precond) h_precond := by
  -- !benchmark @start proof
  sorry
  -- !benchmark @end proof