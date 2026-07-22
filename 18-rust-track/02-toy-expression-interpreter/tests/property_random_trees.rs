//! Property-style anti-cheat gate: random well-formed arithmetic trees are
//! generated with a deterministic PRNG (`sandbox18_harness::prng::
//! Xorshift64`, fixed seeds so a failure is reproducible), rendered to
//! source text, parsed and evaluated by the crate under test, and checked
//! against a value computed directly from the generated tree by
//! `tests/common/mod.rs` -- code that never calls into
//! `t02_toy_expression_interpreter` at all. Memorizing this suite's fixed
//! example expressions elsewhere in `tests/` cannot make these pass.

mod common;

use std::collections::HashMap;
use t02_toy_expression_interpreter::{Value, eval_source};

fn run_property_batch(seed: u64, count: usize, max_depth: u32) {
    let mut rng = sandbox18_harness::prng::Xorshift64::new(seed);
    let env: HashMap<String, Value> = HashMap::new();

    for i in 0..count {
        let tree = common::gen_node(&mut rng, max_depth);
        let source = common::render(&tree);
        let expected = common::eval_node_as_value(&tree);

        match eval_source(&source, &env) {
            Ok(actual) => assert!(
                common::values_match(&actual, &expected),
                "seed {seed} iteration {i}: `{source}` should evaluate to {expected:?} (computed \
                 independently from the generated tree, not by calling this crate), got {actual:?}"
            ),
            Err(e) => panic!(
                "seed {seed} iteration {i}: `{source}` is a well-formed generated expression \
                 (expected {expected:?}) but failed to evaluate at all: {e:?}"
            ),
        }
    }
}

#[test]
fn random_arithmetic_trees_seed_a() {
    run_property_batch(0xF00D_CAFE_1234_5678, 300, 3);
}

#[test]
fn random_arithmetic_trees_seed_b() {
    // A second, differently-seeded batch: a fix tuned to pass exactly the
    // first seed's cases (e.g. a lookup table) still has to survive an
    // entirely different set of generated expressions here.
    run_property_batch(0x1357_9BDF_2468_ACE0, 300, 3);
}

#[test]
fn random_arithmetic_trees_shallow_but_many() {
    // Shallow trees (depth 1-2) generated in bulk skew toward exercising
    // plain int-vs-float promotion and division-always-promotes on the
    // most common small shapes.
    run_property_batch(0x0BAD_F00D_DEAD_BEEF, 500, 2);
}
