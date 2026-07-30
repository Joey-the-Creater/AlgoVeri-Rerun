// Following is the block for necessary definitions
// <preamble>
predicate matches_at(haystack: seq<int>, needle: seq<int>, start_index: int) {
    && 0 <= start_index
    && start_index + |needle| <= |haystack|
    && forall i :: 0 <= i < |needle| ==> 
        haystack[start_index + i] == needle[i]
}

function patterns_view(patterns: seq<seq<int>>): seq<seq<int>> {
    patterns 
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
method ac_automata_search(haystack: seq<int>, patterns: seq<seq<int>>) returns (results: seq<(int, int)>)
    requires |patterns| > 0
    requires |haystack| < 1000000
    requires |patterns| < 1000000
    requires forall i :: 0 <= i < |patterns| ==> |patterns[i]| < 1000000
    ensures
        // Soundness: Every result returned is a valid match
        forall i :: 0 <= i < |results| ==>
            var (pid, idx) := results[i];
            
            // Check bounds BEFORE accessing patterns[pid]
            && pid >= 0 && idx >= 0 
            && 0 <= pid < |patterns|
            && matches_at(haystack, patterns[pid], idx)

    ensures
        // Completeness: Every valid match for any pattern is contained in the results
        forall pid, idx ::
            0 <= pid < |patterns| && matches_at(haystack, patterns[pid], idx) ==>
            exists k :: 0 <= k < |results| && results[k] == (pid, idx)
// </spec>
// <code>
{
    // Implement and verify the Aho-Corasick algorithm here.
}
// </code>