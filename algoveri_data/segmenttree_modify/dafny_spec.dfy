// Following is the block for necessary definitions
// <preamble>
datatype Option<T> = Some(value: T) | None

datatype Node = Node(
    val: int,            // Stores the Max value for the current range (u64)
    low: int,            // Range lower bound (inclusive)
    high: int,           // Range upper bound (exclusive)
    left: Option<Node>,
    right: Option<Node>
) {
    // The view returns a Map from index -> value
    ghost function view(): map<int, int>
        decreases this
    {
        var left_view := match this.left {
            case Some(l) => l.view()
            case None => map[]
        };
        var right_view := match this.right {
            case Some(r) => r.view()
            case None => map[]
        };
        
        // Leaf logic: if no children, we represent the point 'low'.
        if left.None? && right.None? then
            map[low := val]
        else
            // Union of disjoint domains
            left_view + right_view
    }

    // Checks structural integrity and the Max property
    ghost predicate is_segment_tree()
        decreases this
    {
        // 1. Basic Range Validity (and u64 constraints)
        && 0 <= this.low < this.high
        && 0 <= this.val
        
        // 2. Structural Recursion
        && (match (this.left, this.right) {
            case (Some(l), Some(r)) => 
                // Internal Node
                var mid := (this.low + this.high) / 2;
                
                // Child ranges must line up exactly
                && l.low == this.low && l.high == mid
                && r.low == mid && r.high == this.high
                
                // Recursive validity
                && l.is_segment_tree()
                && r.is_segment_tree()
                
                // The Max Property: Node val must be max of children
                && this.val == (if l.val > r.val then l.val else r.val)

            case (None, None) => 
                // Leaf Node
                // Must represent a single point
                && this.high == this.low + 1
                // Implicitly, val is the value of this leaf
                && true

            case _ => false // Segment trees are full binary trees (0 or 2 children)
        })
        
        // 3. View Consistency (The view domain matches the range)
        && (forall k :: k in this.view() <==> this.low <= k < this.high)
        // 4. Value Consistency (The stored val is >= all items in view)
        && (forall k :: k in this.view() ==> this.view()[k] <= this.val)
    }
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
// Renamed 'modify' to 'update' to avoid keyword collision in Dafny
method update(node: Node, idx: int, v: int) returns (res: Node)
    // Constraint: unsigned integers
    requires v >= 0
    requires node.is_segment_tree()
    requires node.low <= idx < node.high
    ensures 
        && res.is_segment_tree()
        && res.low == node.low
        && res.high == node.high
        // Functional Correctness & Frame Preservation:
        // The view matches the old view, but with the specific key updated
        && res.view() == node.view()[idx := v]
// </spec>
// <code>
{
    // Implement and verify the update (modify) function for segment tree
}
// </code>

method main() {}