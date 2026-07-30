// Following is the block for necessary definitions
// <preamble>
datatype Tree = Empty | Node(val: int, left: Tree, right: Tree)

function view(tree: Tree): set<int>
    decreases tree
{
    match tree
    case Empty => {}
    case Node(val, left, right) => view(left) + view(right) + {val}
}

predicate is_bst(tree: Tree)
    decreases tree
{
    match tree
    case Empty => true
    case Node(val, left, right) =>
        (forall x :: x in view(left) ==> x < val) &&
        is_bst(left) &&
        (forall x :: x in view(right) ==> x > val) &&
        is_bst(right)
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
method insert(tree: Tree, v: int) returns (res: Tree)
    requires v >= 0 
    requires is_bst(tree)
    ensures is_bst(res)
    ensures view(res) == view(tree) + {v}
// </spec>
// <code>
{
    // Implement and verify the insert operation for BSTs
}
// </code>