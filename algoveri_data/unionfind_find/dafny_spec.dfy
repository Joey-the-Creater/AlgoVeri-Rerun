// Following is the block for necessary definitions
// <preamble>
class UnionFind {
    var parent: seq<int>
    var rank: seq<int>

    predicate is_valid()
        reads this
    {
        |parent| == |rank| &&
        // Use {:trigger} to prevent matching loops
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
    method find(i: int) returns (root: int)
        requires i >= 0
        requires is_valid()
        requires i < |parent|
        modifies this
        ensures is_valid()
        ensures root == spec_find(i)
        // Verify logical stability: representatives remain the same for all nodes
        ensures forall j :: 0 <= j < |parent| ==>
            spec_find(j) == old(spec_find(j))
        ensures |parent| == old(|parent|)
        ensures rank == old(rank)
// </spec>
// <code>
    {
        // Implement and verify the find operation with path compression for union find data structure here.
    }
// </code>
}