// Following is the block for necessary definitions
// <preamble>
// Calculates total loot: sum of nums[i] for all i in 'houses'
function total_loot(houses: seq<int>, nums: seq<int>): int
    decreases |houses|
{
    if |houses| == 0 then
        0
    else
        // Safe indexing check: if houses[0] in bounds, take value, else 0
        (if 0 <= houses[0] < |nums| then nums[houses[0]] else 0) +
        total_loot(houses[1..], nums)
}

// Definition of a valid robbery plan:
// 1. All indices are chosen from valid range [0, nums.len())
// 2. No duplicates in choices
// 3. No two indices are adjacent (|h1 - h2| > 1)
predicate is_valid_robbery(houses: seq<int>, nums_len: int) {
    // We enforce the sequence of chosen houses to be sorted strictly increasing
    // This simplifies "no duplicates" and "no adjacent" checking.
    // E.g. [0, 2, 5] is valid. [0, 1] is invalid (adj). [2, 0] invalid (not sorted).
    
    // 1. All indices valid
    (forall i: int :: 0 <= i < |houses| ==> 0 <= houses[i] < nums_len) &&
    // 2 & 3. Gap constraint: next house must be at least current + 2
    (forall i: int :: 0 <= i < |houses| - 1 ==> houses[i+1] >= houses[i] + 2)
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
method rob(nums: seq<int>) returns (max_amount: int)
    requires |nums| <= 100
    // Constraints matching Verus u64
    requires forall i: int :: 0 <= i < |nums| ==> nums[i] >= 0
    requires forall i: int :: 0 <= i < |nums| ==> nums[i] <= 10000
    ensures max_amount >= 0
    // 1. Upper Bound
    ensures forall houses: seq<int> :: (is_valid_robbery(houses, |nums|) 
            ==> total_loot(houses, nums) <= max_amount)
    // 2. Existence
    ensures exists houses: seq<int> :: (is_valid_robbery(houses, |nums|) 
            && total_loot(houses, nums) == max_amount)
// </spec>
// <code>
{
    // Implement and verify House Robber DP here.
}
// </code>
