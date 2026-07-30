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
        // Added {:trigger} to prevent matching loops in verification
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
    method push(v: int)
        requires is_heap()
        requires len < max_capacity()
        // Ensure there is physical space in the storage sequence
        requires |storage| > len
        modifies this
        ensures is_heap()
        ensures len == old(len) + 1
        ensures view() == old(view()) + multiset{v}
// </spec>
// <code>
    {
        // Implement and verify the push operation for the max-heap here.
    }
// </code>
}