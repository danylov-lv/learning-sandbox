//! Randomized model test: a deterministic sequence of put/delete/get
//! operations (driven by the harness's `Xorshift64` PRNG, so the sequence
//! is reproducible run to run) is applied to both the store and a
//! `HashMap` oracle. The two must agree at a reopen partway through the
//! sequence and again at the end.

use sandbox18_harness::prng::Xorshift64;
use std::collections::HashMap;
use t05_bitcask_kv_store::Store;

const NUM_KEYS: u64 = 24;
const NUM_OPS: usize = 400;

fn key_for(idx: u64) -> Vec<u8> {
    format!("model-key-{idx}").into_bytes()
}

fn value_for(rng: &mut Xorshift64) -> Vec<u8> {
    let len = 1 + rng.gen_range(0, 40) as usize;
    (0..len).map(|_| (rng.next_u64() % 256) as u8).collect()
}

fn assert_store_matches_oracle(store: &Store, oracle: &HashMap<Vec<u8>, Vec<u8>>, point: &str) {
    for idx in 0..NUM_KEYS {
        let key = key_for(idx);
        let expected = oracle.get(&key).cloned();
        let actual = store.get(&key).expect("get during model agreement check");
        assert_eq!(
            actual,
            expected,
            "store and oracle disagree on key {:?} at {point}",
            String::from_utf8_lossy(&key)
        );
    }

    let mut store_keys = store.keys();
    store_keys.sort();
    let mut oracle_keys: Vec<Vec<u8>> = oracle.keys().cloned().collect();
    oracle_keys.sort();
    assert_eq!(
        store_keys, oracle_keys,
        "store's live key set must match the oracle's live key set at {point}"
    );
}

#[test]
fn randomized_op_sequence_matches_hashmap_oracle_across_a_reopen() {
    let dir = tempfile::tempdir().expect("create temp dir");
    let mut rng = Xorshift64::new(0xB17C_A5E5_D06E_5EED);
    let mut oracle: HashMap<Vec<u8>, Vec<u8>> = HashMap::new();

    let mut store = Store::open(dir.path()).expect("open store");
    let mid = NUM_OPS / 2;

    for step in 0..NUM_OPS {
        let key_idx = rng.gen_range(0, NUM_KEYS);
        let key = key_for(key_idx);

        match rng.gen_range(0, 3) {
            0 => {
                let value = value_for(&mut rng);
                store.put(key.clone(), value.clone()).expect("model put");
                oracle.insert(key, value);
            }
            1 => {
                store.delete(&key).expect("model delete");
                oracle.remove(&key);
            }
            _ => {
                let expected = oracle.get(&key).cloned();
                let actual = store.get(&key).expect("model get");
                assert_eq!(
                    actual,
                    expected,
                    "store and oracle disagree on key {:?} right after op {step}",
                    String::from_utf8_lossy(&key)
                );
            }
        }

        if step == mid {
            store.flush().expect("flush before the mid-sequence reopen");
            drop(store);
            store = Store::open(dir.path()).expect("reopen store mid-sequence");
            assert_store_matches_oracle(&store, &oracle, "the mid-sequence reopen");
        }
    }

    store.flush().expect("flush before the final check");
    assert_store_matches_oracle(&store, &oracle, "the end of the op sequence");
}
