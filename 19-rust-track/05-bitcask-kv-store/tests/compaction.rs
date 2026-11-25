//! A workload of heavy overwrites and deletes, then `compact()`. Checks
//! both that the file shrinks to the *exact* size the pinned format
//! implies for the surviving live records, and that every surviving key
//! still reads back correctly. Either check alone can be cheated: a
//! `compact` that drops half the live keys along with the dead space
//! would pass a size-only check; a `compact` that does nothing at all
//! would pass a correctness-only check.

use std::collections::HashMap;
use t05_bitcask_kv_store::Store;

fn record_size(key: &[u8], value: &[u8]) -> u64 {
    12 + key.len() as u64 + value.len() as u64
}

#[test]
fn compaction_shrinks_file_to_exact_live_size_and_preserves_reads() {
    let dir = tempfile::tempdir().expect("create temp dir");
    let data_path = dir.path().join(t05_bitcask_kv_store::DATA_FILE_NAME);

    let mut store = Store::open(dir.path()).expect("open store");
    let mut oracle: HashMap<Vec<u8>, Vec<u8>> = HashMap::new();

    for i in 0..40u32 {
        let key = format!("k-{i}").into_bytes();
        // heavy overwrite churn: each key written 4 times before settling.
        for round in 0..4u32 {
            let value = format!("v-{i}-round-{round}-padding-to-make-this-longer").into_bytes();
            store.put(key.clone(), value.clone()).expect("put during churn");
            oracle.insert(key.clone(), value);
        }
    }
    // delete every third key.
    for i in (0..40u32).step_by(3) {
        let key = format!("k-{i}").into_bytes();
        store.delete(&key).expect("delete during churn");
        oracle.remove(&key);
    }
    store.flush().expect("flush the churned workload before measuring size");

    let size_before = std::fs::metadata(&data_path)
        .expect("stat data file before compaction")
        .len();

    store.compact().expect("compact should succeed");

    let size_after = std::fs::metadata(&data_path)
        .expect("stat data file after compaction")
        .len();

    let expected_size: u64 = oracle.iter().map(|(k, v)| record_size(k, v)).sum();

    assert_eq!(
        size_after, expected_size,
        "after compaction the data file must be exactly the sum of the pinned record framing \
         (12 + key_len + value_len) over the surviving live records - not smaller (a live key \
         got dropped) and not larger (dead space or old tombstones survived compaction)"
    );
    assert!(
        size_after < size_before,
        "compaction over a workload with heavy overwrites and deletes must shrink the file \
         (before: {size_before} bytes, after: {size_after} bytes) - a no-op compact would \
         leave the size unchanged"
    );

    assert_eq!(
        store.len(),
        oracle.len(),
        "the number of live keys must be unchanged by compaction"
    );
    for (key, expected_value) in &oracle {
        assert_eq!(
            store.get(key).expect("get after compaction"),
            Some(expected_value.clone()),
            "every key that was live before compaction must read back its correct, most \
             recent value after compaction"
        );
    }
    for i in (0..40u32).step_by(3) {
        let key = format!("k-{i}").into_bytes();
        assert_eq!(
            store.get(&key).expect("get deleted key after compaction"),
            None,
            "a key deleted before compaction must stay deleted after compaction, not \
             reappear because its tombstone got dropped without also dropping the key"
        );
    }
}
