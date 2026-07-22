//! Simulates a crash mid-write by truncating the data file directly
//! (through a raw `std::fs::File`, never through `Store`) so that a
//! well-formed record is cut in half, then confirms recovery keeps
//! everything before the cut and drops the torn record without erroring.

use t05_bitcask_kv_store::Store;

fn record_size(key: &[u8], value: &[u8]) -> u64 {
    12 + key.len() as u64 + value.len() as u64
}

#[test]
fn torn_trailing_record_is_dropped_on_reopen() {
    let dir = tempfile::tempdir().expect("create temp dir");
    let data_path = dir.path().join(t05_bitcask_kv_store::DATA_FILE_NAME);

    let good: Vec<(Vec<u8>, Vec<u8>)> = (0..5)
        .map(|i| {
            (
                format!("good-{i}").into_bytes(),
                format!("value-{i}").into_bytes(),
            )
        })
        .collect();
    let torn_key = b"torn-record-key".to_vec();
    let torn_value = b"this-value-will-be-cut-in-half-by-truncation".to_vec();

    let good_end;
    {
        let mut store = Store::open(dir.path()).expect("open store");
        for (k, v) in &good {
            store.put(k.clone(), v.clone()).expect("put good record");
        }
        store.flush().expect("flush good records so they are durable");
        good_end = std::fs::metadata(&data_path)
            .expect("stat data file after good records")
            .len();

        store
            .put(torn_key.clone(), torn_value.clone())
            .expect("put record that will be torn");
        store
            .flush()
            .expect("flush torn record so it is actually on disk to truncate");
    } // store dropped here: releases the file handle before we truncate it directly.

    let torn_record_len = record_size(&torn_key, &torn_value);
    let full_end = good_end + torn_record_len;
    assert!(
        torn_value.len() > 4,
        "test setup: torn value must be long enough to cut cleanly mid-payload"
    );
    let cut_at = good_end + 12 + torn_key.len() as u64 + (torn_value.len() as u64 / 2);
    assert!(
        cut_at > good_end && cut_at < full_end,
        "test setup: cut point must land strictly inside the torn record's bytes"
    );

    {
        let file = std::fs::OpenOptions::new()
            .write(true)
            .open(&data_path)
            .expect("open data file directly, bypassing Store, to simulate a crash mid-write");
        file.set_len(cut_at)
            .expect("truncate data file to cut the trailing record in half");
    }

    let mut store = Store::open(dir.path()).expect(
        "reopening a store whose data file ends in a torn trailing record must not return Err",
    );

    for (k, v) in &good {
        assert_eq!(
            store.get(k).expect("get a good record after recovery"),
            Some(v.clone()),
            "every record fully written and flushed before the torn one must survive recovery"
        );
    }
    assert_eq!(
        store.get(&torn_key).expect("get the torn record after recovery"),
        None,
        "the torn record must be entirely absent after recovery - not present as a corrupted \
         value, just gone, as if it had never been appended"
    );
    assert_eq!(
        store.len(),
        good.len(),
        "recovery must keep exactly the fully-written records and nothing from the torn tail"
    );

    // The recovered store must still be writable — this catches an implementation
    // that recovers reads correctly but forgets to truncate the file down to the
    // last valid offset, leaving new appends after a gap of leftover torn bytes.
    store
        .put(b"after-recovery".to_vec(), b"still-works".to_vec())
        .expect("a store recovered from a torn tail must still accept new writes");
    store.flush().expect("flush the post-recovery write");
    assert_eq!(
        store.get(b"after-recovery").expect("get the post-recovery write"),
        Some(b"still-works".to_vec()),
        "a write made after recovering from a torn tail must read back correctly"
    );
}
