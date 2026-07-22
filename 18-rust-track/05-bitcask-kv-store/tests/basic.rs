//! Basic put/get/overwrite/delete semantics, key listing, and one exact
//! on-disk size check derived from the pinned record format.

use t05_bitcask_kv_store::Store;

#[test]
fn put_then_get_returns_value() {
    let dir = tempfile::tempdir().expect("create temp dir");
    let mut store = Store::open(dir.path()).expect("open store");

    store
        .put(b"lang".to_vec(), b"rust".to_vec())
        .expect("put should succeed");

    assert_eq!(
        store.get(b"lang").expect("get should succeed"),
        Some(b"rust".to_vec()),
        "get must return the value that was just put for the same key"
    );
}

#[test]
fn get_missing_key_returns_none() {
    let dir = tempfile::tempdir().expect("create temp dir");
    let store = Store::open(dir.path()).expect("open store");

    assert_eq!(
        store.get(b"never-written").expect("get should succeed"),
        None,
        "get on a key that was never put must return None, not an error"
    );
}

#[test]
fn overwrite_replaces_value() {
    let dir = tempfile::tempdir().expect("create temp dir");
    let mut store = Store::open(dir.path()).expect("open store");

    store.put(b"k".to_vec(), b"first".to_vec()).expect("first put");
    store.put(b"k".to_vec(), b"second".to_vec()).expect("overwrite put");

    assert_eq!(
        store.get(b"k").expect("get should succeed"),
        Some(b"second".to_vec()),
        "get must return the most recently put value, not the first one written"
    );
}

#[test]
fn delete_removes_key() {
    let dir = tempfile::tempdir().expect("create temp dir");
    let mut store = Store::open(dir.path()).expect("open store");

    store.put(b"k".to_vec(), b"v".to_vec()).expect("put");
    store.delete(b"k").expect("delete should succeed");

    assert_eq!(
        store.get(b"k").expect("get should succeed"),
        None,
        "get on a deleted key must return None"
    );
}

#[test]
fn delete_missing_key_is_not_an_error() {
    let dir = tempfile::tempdir().expect("create temp dir");
    let mut store = Store::open(dir.path()).expect("open store");

    store
        .delete(b"never-existed")
        .expect("deleting an absent key must not be an error");
}

#[test]
fn keys_lists_only_live_keys() {
    let dir = tempfile::tempdir().expect("create temp dir");
    let mut store = Store::open(dir.path()).expect("open store");

    store.put(b"a".to_vec(), b"1".to_vec()).expect("put a");
    store.put(b"b".to_vec(), b"2".to_vec()).expect("put b");
    store.put(b"c".to_vec(), b"3".to_vec()).expect("put c");
    store.delete(b"b").expect("delete b");

    let mut keys = store.keys();
    keys.sort();

    assert_eq!(
        keys,
        vec![b"a".to_vec(), b"c".to_vec()],
        "keys() must list exactly the still-live keys (a, c) and not the deleted one (b)"
    );
    assert_eq!(
        store.len(),
        2,
        "len() must match the number of live keys reported by keys()"
    );
    assert!(!store.is_empty(), "store with two live keys must not report is_empty()");
}

#[test]
fn empty_store_is_empty() {
    let dir = tempfile::tempdir().expect("create temp dir");
    let store = Store::open(dir.path()).expect("open store");

    assert!(
        store.is_empty(),
        "a freshly opened store with no puts yet must report is_empty()"
    );
    assert_eq!(store.len(), 0, "a freshly opened store must report len() == 0");
}

#[test]
fn record_framing_matches_pinned_format() {
    let dir = tempfile::tempdir().expect("create temp dir");
    let mut store = Store::open(dir.path()).expect("open store");

    let key = b"exact-size-key".to_vec();
    let value = b"exact-size-value-payload".to_vec();
    let key_len = key.len();
    let value_len = value.len();

    store.put(key, value).expect("put");
    store.flush().expect("flush must durably write the record");

    let data_path = dir.path().join(t05_bitcask_kv_store::DATA_FILE_NAME);
    let on_disk_len = std::fs::metadata(&data_path)
        .expect("data file must exist after a put + flush")
        .len();

    let expected_len = 12u64 + key_len as u64 + value_len as u64;
    assert_eq!(
        on_disk_len, expected_len,
        "a single put's record must be exactly 12 (header) + key_len + value_len bytes, \
         per the pinned format in the README — got a different size, meaning the framing \
         doesn't match the spec byte for byte"
    );
}
