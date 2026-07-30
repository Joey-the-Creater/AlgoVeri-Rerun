// Following is the block for necessary definitions
// <preamble>
predicate is_sorted(s: seq<int>) {
    forall i, j {:trigger s[i], s[j]} :: 
        0 <= i <= j < |s| ==> s[i] <= s[j]
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
method binary_search_lower_bound(s: seq<int>, target: int) returns (result: int)
    requires |s| <= 0x7FFFFFFF
    requires is_sorted(s)
    ensures result >= 0
    ensures result <= |s|
    ensures forall i {:trigger s[i]} :: 0 <= i < result ==> s[i] < target
    ensures forall i {:trigger s[i]} :: result <= i < |s| ==> s[i] >= target
// </spec>
// <code>
{
    // Implement and verify the binary search for lower bound here.
}
// </code>

method main() {}