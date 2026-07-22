//! A small deterministic PRNG (xorshift64*) so `datagen` and task tests get
//! reproducible pseudo-randomness without pulling in the `rand` crate —
//! determinism across `rand` versions/algorithm changes is not guaranteed,
//! byte-identical regeneration is a hard requirement here.

/// xorshift64* generator. Not cryptographically secure, not intended to be —
/// only deterministic and reasonably well distributed.
#[derive(Debug, Clone)]
pub struct Xorshift64 {
    state: u64,
}

impl Xorshift64 {
    pub fn new(seed: u64) -> Self {
        // xorshift is undefined at state 0; substitute a fixed non-zero seed.
        Self {
            state: if seed == 0 { 0x9E37_79B9_7F4A_7C15 } else { seed },
        }
    }

    /// Next raw 64-bit output.
    pub fn next_u64(&mut self) -> u64 {
        let mut x = self.state;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.state = x;
        x.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }

    pub fn next_u32(&mut self) -> u32 {
        (self.next_u64() >> 32) as u32
    }

    /// Uniform float in `[0, 1)`.
    pub fn next_f64(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 * (1.0 / (1u64 << 53) as f64)
    }

    /// Uniform integer in `[lo, hi)`. Panics if `hi <= lo`.
    pub fn gen_range(&mut self, lo: u64, hi: u64) -> u64 {
        assert!(hi > lo, "gen_range: empty range [{lo}, {hi})");
        lo + self.next_u64() % (hi - lo)
    }

    /// Standard normal sample via Box-Muller, for building log-normal-ish
    /// distributions: `exp(mu + sigma * z)`.
    pub fn next_standard_normal(&mut self) -> f64 {
        let u1 = self.next_f64().max(f64::MIN_POSITIVE);
        let u2 = self.next_f64();
        (-2.0 * u1.ln()).sqrt() * (std::f64::consts::TAU * u2).cos()
    }

    /// Samples a rank in `[0, n)` from a Zipf-like distribution with
    /// exponent `s` (higher = more skewed toward rank 0), via inverse CDF
    /// over a precomputed cumulative weight table. `n` should be small
    /// enough to afford an O(n) table (a path/category popularity list is
    /// fine; this is not meant for huge n).
    pub fn zipf_rank(&mut self, n: usize, s: f64) -> usize {
        assert!(n > 0, "zipf_rank: n must be positive");
        let mut cumulative = Vec::with_capacity(n);
        let mut total = 0.0f64;
        for rank in 1..=n {
            total += 1.0 / (rank as f64).powf(s);
            cumulative.push(total);
        }
        let target = self.next_f64() * total;
        match cumulative
            .iter()
            .position(|&c| c >= target)
        {
            Some(idx) => idx,
            None => n - 1,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn deterministic_for_same_seed() {
        let mut a = Xorshift64::new(42);
        let mut b = Xorshift64::new(42);
        let seq_a: Vec<u64> = (0..100).map(|_| a.next_u64()).collect();
        let seq_b: Vec<u64> = (0..100).map(|_| b.next_u64()).collect();
        assert_eq!(seq_a, seq_b, "same seed must produce identical sequences");
    }

    #[test]
    fn different_seeds_diverge() {
        let mut a = Xorshift64::new(1);
        let mut b = Xorshift64::new(2);
        assert_ne!(a.next_u64(), b.next_u64());
    }

    #[test]
    fn f64_stays_in_unit_range() {
        let mut rng = Xorshift64::new(7);
        for _ in 0..1000 {
            let v = rng.next_f64();
            assert!((0.0..1.0).contains(&v), "next_f64 out of range: {v}");
        }
    }

    #[test]
    fn zipf_favors_low_ranks() {
        let mut rng = Xorshift64::new(123);
        let mut counts = [0u64; 10];
        for _ in 0..20_000 {
            counts[rng.zipf_rank(10, 1.2)] += 1;
        }
        assert!(
            counts[0] > counts[9] * 3,
            "rank 0 should dominate rank 9 under a skewed zipf distribution: {counts:?}"
        );
    }
}
