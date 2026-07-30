// Following is the block for necessary definitions
// <preamble>
predicate divides(d: int, n: int)
  requires d != 0
{
  n % d == 0
}

predicate is_prime(n: int)
{
  n > 1 &&
  forall d :: 1 < d < n ==> !divides(d, n)
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
method check_prime(n: int) returns (res: bool)
  // Simulate u64: input is non-negative
  requires n >= 0
  ensures res == is_prime(n)
// </spec>
// <code>
{
  // Implement and verify the algorithm to check for primality by naively testing divisibility for all integers from 2 to n-1
}
// </code>

method Main() {
}