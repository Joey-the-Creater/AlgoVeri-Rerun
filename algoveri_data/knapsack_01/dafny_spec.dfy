// Following is the block for necessary definitions
// <preamble>
// Calculates the total weight of the selected items
function total_weight(selected: seq<bool>, weights: seq<int>): int
    requires |selected| <= |weights|
    decreases |selected|
{
    if |selected| == 0 then
        0
    else
        (if selected[0] then weights[0] else 0) + 
        total_weight(selected[1..], weights[1..])
}

// Calculates the total value of the selected items
function total_value(selected: seq<bool>, values: seq<int>): int
    requires |selected| <= |values|
    decreases |selected|
{
    if |selected| == 0 then
        0
    else
        (if selected[0] then values[0] else 0) + 
        total_value(selected[1..], values[1..])
}

// Definition of a valid strategy: 
// 1. Selection length matches items length
// 2. Total weight does not exceed capacity
predicate is_valid_strategy(selected: seq<bool>, weights: seq<int>, capacity: int)
{
    |selected| == |weights| &&
    total_weight(selected, weights) <= capacity
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
method solve_knapsack_01(weights: seq<int>, values: seq<int>, capacity: int) returns (max_val: int)
    requires |weights| == |values|
    requires |weights| <= 100 // Reasonable bound for recursion/verification time
    requires 0 <= capacity <= 1000 // Explicitly constrain non-negative capacity
    requires forall i :: 0 <= i < |weights| ==> 0 <= weights[i] <= 1000 // Explicitly constrain non-negative weights
    requires forall i :: 0 <= i < |values| ==> 0 <= values[i] <= 1000   // Explicitly constrain non-negative values
    ensures max_val >= 0
    ensures
        // 1. Upper Bound
        forall selected: seq<bool> :: 
            is_valid_strategy(selected, weights, capacity)
            ==> total_value(selected, values) <= max_val
    ensures
        // 2. Existence
        exists selected: seq<bool> :: 
            is_valid_strategy(selected, weights, capacity)
            && total_value(selected, values) == max_val
// </spec>
// <code>
{
    // TODO: Implement the 0/1 Knapsack DP algorithm here.
}
// </code>

method Main() {}