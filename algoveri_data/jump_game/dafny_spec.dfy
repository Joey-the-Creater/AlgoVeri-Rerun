// Following is the block for necessary definitions
// <preamble>
// Definition of a valid jump path (sequence of indices)
// path[0] == 0
// path[last] == target_index
// path[k+1] is reachable from path[k]
predicate is_valid_jump_path(path: seq<int>, nums: seq<int>) {
    if |path| < 1 then
        false
    else
        // Start at 0
        path[0] == 0 &&
        // End at the last index of nums
        path[|path|-1] == |nums| - 1 &&
        // All indices in bounds
        (forall i: int :: 0 <= i < |path| ==> 0 <= path[i] < |nums|) &&
        // Valid jumps between steps
        (forall i: int :: 0 <= i < |path| - 1 ==> 
            path[i+1] > path[i] && // Progress forward
            path[i+1] <= path[i] + nums[path[i]])
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
method can_jump(nums: seq<int>) returns (reachable: bool)
    requires |nums| > 0
    requires |nums| <= 10000
    // From u64 constraint
    requires forall i: int :: 0 <= i < |nums| ==> nums[i] >= 0
    requires forall i: int :: 0 <= i < |nums| ==> nums[i] <= 10000
    ensures
        // reachable <==> exists path
        reachable <==> exists path: seq<int> :: is_valid_jump_path(path, nums)
// </spec>
// <code>
{
    // Implement and verify Jump Game greedy algorithm here.
}
// </code>
