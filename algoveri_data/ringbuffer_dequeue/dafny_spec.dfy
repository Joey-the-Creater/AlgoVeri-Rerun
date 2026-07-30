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
        // Explicitly require data length matches capacity for well-defined indexing
        requires |data| == capacity 
    {
        // Capture fields to local variables to satisfy lambda read requirements
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
    // Pop the oldest element from the buffer
    method dequeue() returns (val: T)
        requires is_valid()
        requires len > 0
        modifies this
        ensures is_valid()
        // The value returned is the first element of the old sequence
        ensures val == old(view())[0]
        // The new sequence is the old sequence minus the first element
        ensures view() == old(view())[1..]
// </spec>
// <code>
    {
        // Implement and verify the dequeue operation for the ring buffer here.
    }
// </code>
}