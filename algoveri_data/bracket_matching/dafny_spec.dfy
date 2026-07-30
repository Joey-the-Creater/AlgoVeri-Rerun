// <preamble>
// Assigns a mathematical weight to characters:
// '(' (ASCII 40) adds 1 (opening a scope)
// ')' (ASCII 41) subtracts 1 (closing a scope)
// All other characters are neutral (0).
function char_weight(c: int): int {
    if c == 40 then      // ASCII for '('
        1
    else if c == 41 then // ASCII for ')'
        -1
    else
        0
}

// Recursively calculates the total balance of the sequence.
// A balanced string must result in a total weight of 0.
function total_weight(s: seq<int>): int
    decreases |s|
{
    if |s| == 0 then
        0
    else
        char_weight(s[0]) + total_weight(s[1..])
}

// Checks the Prefix Property:
// At no point in the string (index i) should the closing brackets exceed opening brackets.
// If this is violated (weight < 0), the string is invalid immediately.
predicate valid_prefix_weights(s: seq<int>) {
    forall i :: 0 <= i <= |s| ==> total_weight(s[0..i]) >= 0
}

// The high-level correctness predicate for bracket matching.
predicate is_matched(s: seq<int>) {
    && total_weight(s) == 0       // Must end with closed pairs
    && valid_prefix_weights(s)    // Must never close a non-existent pair
}
// </preamble>

// <helpers>

// </helpers>

// <proofs>

// </proofs>

// <spec>
method bracket_match(s: seq<int>) returns (res: bool)
    requires
        // CONSTRAINT: Hard limit of 1,000,000 ensures no integer overflow
        // when counting or indexing.
        |s| <= 1000000
    ensures
        res == is_matched(s)
// </spec>
// <code>
{
    // TODO: Implement and verify the bracket matching logic here.
}
// </code>