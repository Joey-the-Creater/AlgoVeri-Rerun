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
method sieve_of_eratosthenes(n: int) returns (primes: seq<bool>)
  // Simulate usize (non-negative) and bound constraint
  requires 0 <= n <= 100_000
  
  ensures |primes| == n
  // Functional Correctness: 
  // Dafny automatically triggers on primes[i] here because it appears in the body.
  ensures forall i :: 0 <= i < n ==> primes[i] == is_prime(i)
// </spec>
// <code>
{
  // Implement and verify the Sieve of Eratosthenes algorithm
  assume {:axiom} false;
}
// </code>

method Main() {
}