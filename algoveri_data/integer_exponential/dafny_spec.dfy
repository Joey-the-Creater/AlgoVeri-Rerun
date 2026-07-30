// Following is the block for necessary definitions
// <preamble>
// Pure mathematical definition of power
function spec_pow(b: nat, e: nat): nat
  decreases e
{
  if e == 0 then
    1
  else
    b * spec_pow(b, e - 1)
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
method exponentiation(b: int, e: int) returns (res: int)
  // Simulate u64 types (non-negative)
  requires b >= 0 
  requires e >= 0
  // Precondition: Result fits in u64 (0xffff_ffff_ffff_ffff)
  requires spec_pow(b, e) <= 0xffff_ffff_ffff_ffff
  
  ensures res == spec_pow(b, e)
  // Ensure return value preserves non-negativity
  ensures res >= 0
// </spec>
// <code>
{
  // Implement and verify the algorithm to compute the exponential
}
// </code>

method Main() {
  // Empty main
}