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
method splay(tree: Tree, v: int) returns (res: Tree)
    // tree is Box<Node>, so it cannot be Empty
    requires tree.Node?
    requires is_bst(tree)
    // res is Box<Node>, so it cannot be Empty
    ensures res.Node?
    ensures is_bst(res)
    ensures view(res) == view(tree)
    // Postcondition: If v was in the tree, it is now at the root.
    ensures v in view(tree) ==> res.val == v
    // Postcondition: If v was NOT in the tree, the new root is 
    // the last node accessed (implicitly true if res.Node?, but kept for fidelity)
    ensures v !in view(tree) ==> res.val in view(res)
// </spec>
// <code>
{
    // Implement and verify the splay operation for the splay tree here.
}
// </code>