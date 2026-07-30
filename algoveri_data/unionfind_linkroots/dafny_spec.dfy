// Following is the block for necessary definitions
// <preamble>
class UnionFind {
    var parent: seq<int>
    var rank: seq<int>

    predicate is_valid()
        reads this
    {
        |parent| == |rank| &&
        // Use {:trigger} to prevent matching loops in quantification
        (forall i {:trigger parent[i]} {:trigger rank[i]} :: 0 <= i < |parent| ==>
            var p := parent[i];
            0 <= p < |parent| &&
            0 <= rank[i] < |parent| &&
            (p != i ==> rank[i] < rank[p])
        )
    }

    function measure(i: int): int
        reads this
    {
        if 0 <= i < |rank| && rank[i] < |parent| then
            |parent| - rank[i]
        else
            0
    }

    function spec_find(i: int): int
        reads this
        decreases measure(i)
    {
        if 0 <= i < |parent| && 0 <= i < |rank| && rank[i] < |parent| then
            var p := parent[i];
            if p != i && 0 <= p < |rank| && rank[p] < |parent| && rank[i] < rank[p] then
                spec_find(p)
            else
                i
        else
            i
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
    method link_roots(root_i: int, root_j: int)
        requires root_i >= 0 && root_j >= 0
        requires is_valid()
        requires root_i < |parent|
        requires root_j < |parent|
        // Input requirement: Both indices must currently be roots
        requires parent[root_i] == root_i
        requires parent[root_j] == root_j
        modifies this
        ensures is_valid()
        ensures |parent| == old(|parent|)
        // Functional Correctness: root_i and root_j are now in the same set
        ensures spec_find(root_i) == spec_find(root_j)
        // Frame Condition: Other roots remain unchanged
        ensures forall k :: 0 <= k < |parent| && k != root_i && k != root_j ==>
            (old(parent)[k] == k ==> parent[k] == k)
// </spec>
// <code>
    {
        // Implement and verify the link_roots operation for union find here.
    }
// </code>
}