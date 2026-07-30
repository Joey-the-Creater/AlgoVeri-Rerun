// Following is the block for necessary definitions
// <preamble>
class RingBuffer<T> {
    var data: seq<T>
    var head: int
    var len: int
    var capacity: int

    // View function: models the ring buffer as a linear sequence
    function view(): seq<T>
        reads this
        requires capacity > 0
        requires len >= 0
        // Explicitly tell Dafny the data buffer is large enough for the modulo ops
        requires |data| == capacity 
    {
        // Capture fields to local variables for the lambda
        var d := data;
        var h := head;
        var c := capacity;
        
        seq(len, i => d[(h + i) % c])
    }

    predicate is_valid()
        reads this
    {
        capacity > 0 &&
        |data| == capacity &&
        0 <= len <= capacity &&
        0 <= head < capacity
    }

    constructor(cap: int, fill_value: T)
        requires cap > 0
        ensures is_valid()
        ensures |view()| == 0
        ensures capacity == cap
    {
        var d := [];
        var i := 0;
        while i < cap
            invariant |d| == i
            invariant i <= cap
        {
            d := d + [fill_value];
            i := i + 1;
        }
        data := d;
        head := 0;
        len := 0;
        capacity := cap;
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
    // Enqueue with Overwrite
    method enqueue(value: T)
        requires is_valid()
        modifies this
        ensures is_valid()
        ensures capacity == old(capacity)
        // Case 1: If it wasn't full, it's like a normal push
        ensures old(len) < old(capacity) ==> 
            view() == old(view()) + [value]
        // Case 2: If it was full, we drop the first (oldest) and then push
        ensures old(len) == old(capacity) ==> 
            view() == old(view())[1..] + [value]
// </spec>
// <code>
    {
        // Implement and verify the enqueue with overwrite operation for the ring buffer here.
    }
// </code>
}