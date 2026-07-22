//! Close the store, reopen the same directory, and prove persistence
//! actually happened. An in-memory-only `HashMap` wrapper with no real
//! disk I/O fails this test immediately, even though it would pass every
//! test in basic.rs.

use t05_bitcask_kv_store::Store;

#[test]
fn reopen_preserves_live_keys_and_forgets_deleted_keys() {
    let dir = tempfile::tempdir().expect("create temp dir");

    {
        let mut store = Store::open(dir.path()).expect("open store");
        store.put(b"alpha".to_vec(), b"1".to_vec()).expect("put alpha");
        store.put(b"beta".to_vec(), b"2".to_vec()).expect("put beta");
        store.put(b"gamma".to_vec(), b"3".to_vec()).expect("put gamma");
        store.delete(b"beta").expect("delete beta");
        store.flush().expect("flush before close");
        // store dropped here: this is the "close" half of close/reopen.
    }

    let store = Store::open(dir.path()).expect("reopen store on the same directory");

    assert_eq!(
        store.get(b"alpha").expect("get alpha"),
        Some(b"1".to_vec()),
        "alpha was live before close and must survive a reopen"
    );
    assert_eq!(
        store.get(b"gamma").expect("get gamma"),
        Some(b"3".to_vec()),
        "gamma was live before close and must survive a reopen"
    );
    assert_eq!(
        store.get(b"beta").expect("get beta"),
        None,
        "beta was deleted before close and must stay deleted after a reopen \
         (a keydir rebuilt purely from replay must still see and apply the tombstone)"
    );
    assert_eq!(
        store.len(),
        2,
        "a reopened store must report exactly the keys that were live at close time"
    );
}

#[test]
fn reopen_survives_many_records_across_overwrites() {
    let dir = tempfile::tempdir().expect("create temp dir");

    {
        let mut store = Store::open(dir.path()).expect("open store");
        for i in 0..200u32 {
            let key = format!("key-{i}").into_bytes();
            store.put(key.clone(), b"first".to_vec()).expect("initial put");
            store.put(key, format!("value-{i}").into_bytes()).expect("overwrite put");
        }
        store.flush().expect("flush before close");
    }

    let store = Store::open(dir.path()).expect("reopen store");
    for i in 0..200u32 {
        let key = format!("key-{i}").into_bytes();
        let expected = format!("value-{i}").into_bytes();
        assert_eq!(
            store.get(&key).expect("get after reopen"),
            Some(expected),
            "key-{i} must read back its last-written value after reopen, not the first one \
             written before it was overwritten"
        );
    }
    assert_eq!(
        store.len(),
        200,
        "all 200 distinct keys must still be counted as live after reopen"
    );
}
