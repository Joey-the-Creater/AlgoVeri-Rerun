// <preamble>
class VerifiableQueue<T> {
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
    // Push to the back of the queue
    method enqueue(value: T)
        requires is_valid()
        modifies this
        ensures is_valid()
        ensures view() == old(view()) + [value]
// </spec>
// <code>
    {
        // Implement and verify the enqueue operation for the queue here.
    }
// </code>
}