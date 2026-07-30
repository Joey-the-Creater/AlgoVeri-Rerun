import Mathlib

inductive Color
| Red
| Black
deriving Inhabited, BEq

inductive Node
| Empty : Node
| Tree  (color : Color) (val : Int) (left : Node) (right : Node) : Node
deriving Inhabited

def view (t : Node) : Set Int :=
  match t with
  | Node.Empty => ∅
  | Node.Tree _ v l r => view l ∪ view r ∪ {v}

def is_red (t : Node) : Bool :=
  match t with
  | Node.Tree Color.Red _ _ _ => true
  | _ => false

def is_bst (t : Node) : Prop :=
  match t with
  | Node.Empty => True
  | Node.Tree _ v l r =>
    (∀ x ∈ view l, x < v) ∧
    is_bst l ∧
    (∀ x ∈ view r, x > v) ∧
    is_bst r

-- Black Height: Returns -1 if invalid
def black_height (t : Node) : Int :=
  match t with
  | Node.Empty => 1
  | Node.Tree c _ l r =>
    let lh := black_height l
    let rh := black_height r
    if lh ≠ -1 ∧ rh ≠ -1 ∧ lh = rh then
      if c == Color.Black then lh + 1 else lh
    else
      -1

def satisfies_red_props (t : Node) : Prop :=
  match t with
  | Node.Empty => True
  | Node.Tree c _ l r =>
    satisfies_red_props l ∧
    satisfies_red_props r ∧
    -- Rule 1: No Right-Leaning Red (Matches Dafny)
    (if is_red r then False else True) ∧
    -- Rule 2: No Double Red on Left (Matches Dafny)
    -- Check: If Left is Red, then Left.Left must NOT be Red.
    -- This applies regardless of 'c' (current color).
    (match l with
     | Node.Tree Color.Red _ ll _ => 
       (match ll with | Node.Tree Color.Red _ _ _ => False | _ => True)
     | _ => True)

-- This definition is tricky because LLRBT insert allows the root to be red temporarily or permanently if it's the root of the whole tree (though usually root is black).
-- However, the recursive step needs a weaker invariant.
-- Dafny spec says: "This allows the root to be Red or Black"
def is_llrbt (t : Node) : Prop :=
  is_bst t ∧
  black_height t ≠ -1 ∧
  -- We need to check red properties. Dafny's satisfies_red_props handles recursive checks.
  -- But wait, Dafny's `satisfies_red_props` seems to strictly forbid right-leaning reds everywhere?
  -- Let's re-read Dafny carefully.
  -- satisfy_red_props:
  --   left_ok && right_ok && right_is_black && no_double_red
  --   Right is black: if right is red -> false.
  --   No double red on left: if left is red, left.left cannot be red? No, `l.is_red` then `l.left` check?
  --   Dafny: `match this.left { case Some(l) => if l.is_red then match l.left { case Some(ll) => !ll.is_red ...`
  --   This means: If I am any node, my right child cannot be red. And if my left child is red, IT'S left child cannot be red (no consecutive reds on left edge).
  --   What about Me being Red and Left being Red? Dafny spec doesn't explicitly ban `this.is_red && this.left.is_red` in `satisfies_red_props` itself?
  --   Ah, `no_double_red` checks `this.left` (l) and `l.left` (ll).
  --   So it prevents `Red -> Red` on the left edge.
  satisfies_red_props t



-- Precondition definitions
@[reducible, simp]
def insert_precond (t : Node) : Prop :=
  -- !benchmark @start precond
  is_llrbt t
  -- !benchmark @end precond

-- !benchmark @start auxcode
-- !benchmark @end auxcode

-- Main function definition
def insert (t : Node) (v : Int)
    (h_precond : insert_precond t) : Node :=
  -- !benchmark @start code
  sorry
  -- !benchmark @end code

-- Postcondition definitions
@[reducible, simp]
def insert_postcond (t : Node) (v : Int) (result : Node)
    (_ : insert_precond t) : Prop :=
  -- !benchmark @start postcond
  is_llrbt result ∧
  view result = view t ∪ {v}
  -- !benchmark @end postcond

-- !benchmark @start lemma
-- !benchmark @end lemma

-- Proof content
theorem insert_postcond_satisfied (t : Node) (v : Int)
    (h_precond : insert_precond t) :
    insert_postcond t v (insert t v h_precond) h_precond := by
  -- !benchmark @start proof
  sorry
  -- !benchmark @end proof
