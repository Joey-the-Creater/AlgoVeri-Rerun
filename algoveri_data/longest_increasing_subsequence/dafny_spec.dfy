// Following is the block for necessary definitions
// <preamble>
ghost predicate is_valid_is(s: seq<int>, indices: seq<int>) {
    (forall k: int, m: int :: 
        0 <= k < m < |indices| ==> indices[k] < indices[m])
    && 
    (forall k: int :: 
        0 <= k < |indices| ==> 0 <= indices[k] < |s|)
    && 
    (forall k: int, m: int :: 
        0 <= k < m < |indices| ==> s[indices[k]] < s[indices[m]])
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
method longest_increasing_subsequence(s: seq<int>) returns (result: int)
    requires |s| <= 0x7FFFFFFFFFFFFFFF
    ensures result >= 0
    ensures
        forall sub: seq<int> :: is_valid_is(s, sub) && |sub| > 0 ==> |sub| <= result
    ensures
        exists sub: seq<int> :: is_valid_is(s, sub) && |sub| == result
// </spec>
// <code>
{
    // Implement and verify the LIS algorithm here.
}
// </code>
