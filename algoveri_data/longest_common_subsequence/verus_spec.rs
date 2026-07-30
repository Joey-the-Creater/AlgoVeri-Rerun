use vstd::prelude::*;

verus! {
    // Following is the block for necessary definitions
    // <preamble>
    pub struct Input {
        pub s: Vec<char>,
        pub t: Vec<char>,
    }

    spec fn max(a: int, b: int) -> int {
        if a > b { a } else { b }
    }

    spec fn lcs_spec(s1: Seq<char>, s2: Seq<char>) -> int
        decreases s1.len(), s2.len()
    {
        if s1.len() == 0 || s2.len() == 0 {
            0
        } else {
            let n = s1.len() as int;
            let m = s2.len() as int;
            if s1[n-1] == s2[m-1] {
                1 + lcs_spec(s1.subrange(0, n-1), s2.subrange(0, m-1))
            } else {
                max(
                    lcs_spec(s1.subrange(0, n-1), s2),
                    lcs_spec(s1, s2.subrange(0, m-1))
                )
            }
        }
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
    fn solve_longest_common_subsequence(input: &Input) -> (len: usize)
        requires
            input.s.len() <= 3000,
            input.t.len() <= 3000,
        ensures
            len as int == lcs_spec(input.s@, input.t@),
    // </spec>
    // <code>
    {
        // TODO: Implement the LCS DP algorithm here.
    }
    // </code>

    fn main() {}

} // verus!
