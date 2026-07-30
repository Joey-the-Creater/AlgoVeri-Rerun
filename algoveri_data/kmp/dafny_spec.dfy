// Following is the block for necessary definitions
// <preamble>
predicate matches_at(haystack: seq<int>, needle: seq<int>, start_index: int) {
    && 0 <= start_index
    && start_index + |needle| <= |haystack|
    && forall i :: 0 <= i < |needle| ==> 
        haystack[start_index + i] == needle[i]
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
method kmp_search(haystack: seq<int>, needle: seq<int>) returns (indices: seq<int>)
    requires |haystack| < 1000000
    requires |needle| < 1000000
    ensures 
        // Type Constraint: Indices must be non-negative (simulating usize)
        forall k :: 0 <= k < |indices| ==> indices[k] >= 0
    ensures
        // Soundness: Every index returned is a valid match
        forall i :: 0 <= i < |indices| ==> 
            matches_at(haystack, needle, indices[i])
    ensures
        // Completeness: Every valid match in the haystack is found
        forall i :: matches_at(haystack, needle, i) ==> 
            exists k :: 0 <= k < |indices| && indices[k] == i
// </spec>
// <code>
{
    // Implement and verify the KMP search algorithm to find a specific pattern in a string
}
// </code>