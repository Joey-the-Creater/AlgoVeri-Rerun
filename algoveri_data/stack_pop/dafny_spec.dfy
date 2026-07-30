// Following is the block for necessary definitions
// <preamble>
class VerifiableStack<T> {
    var data: seq<T>

    function view(): seq<T>
        reads this
    {
        data
    }

    predicate is_valid()
        reads this
    {
        true
    }

    constructor()
        ensures is_valid()
        ensures |view()| == 0
    {
        data := [];
    }

    method len() returns (l: int)
        requires is_valid()
        ensures l == |view()|
        ensures l >= 0
    {
        l := |data|;
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
    method pop() returns (val: T)
        requires is_valid()
        requires |view()| > 0
        modifies this
        ensures is_valid()
        ensures val == old(view())[|old(view())| - 1]
        ensures view() == old(view())[..|old(view())| - 1]
// </spec>
// <code>
    {
        // Implement and verify the pop operation for the stack here.
    }
// </code>
}