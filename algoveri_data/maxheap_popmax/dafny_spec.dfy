// Following is the block for necessary definitions
// <preamble>
class BinaryMaxHeap {
    var storage: seq<int>
    var len: int

    function max_capacity(): int { 1023 }

    predicate is_heap()
        reads this
    {
        len <= max_capacity() &&
        0 <= len <= |storage| &&
        // Heap Property: Child <= Parent
        // Parent index of i is (i - 1) / 2
        // Fix: Added {:trigger storage[i]} to suppress matching loop warning
        (forall i {:trigger storage[i]} :: 1 <= i < len ==> storage[i] <= storage[(i - 1) / 2])
    }

    function view(): multiset<int>
        reads this
        requires 0 <= len <= |storage|
    {
        multiset(storage[..len])
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
    method pop_max() returns (max: int)
        requires is_heap()
        requires len > 0
        modifies this
        ensures is_heap()
        ensures len == old(len) - 1
        // (1) Functional Correctness: Returns the maximum
        ensures forall x :: x in old(view()) ==> max >= x
        // (2) Multiset Consistency: One instance of max is removed
        ensures view() == old(view()) - multiset{max}
// </spec>
// <code>
    {
        // Implement and verify the pop_max operation for the max-heap here.
    }
// </code>
}