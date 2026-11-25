//! A minimal scoped temp-directory helper. Deliberately hand-rolled (not the
//! `tempfile` crate) so the harness itself stays dependency-light; tasks 05
//! and 08 use `tempfile` directly as a dev-dependency for their own tests.

use std::io;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

static COUNTER: AtomicU64 = AtomicU64::new(0);

/// A directory under the OS temp root that is removed (best-effort) when
/// this handle is dropped.
#[derive(Debug)]
pub struct TempDir {
    path: PathBuf,
}

impl TempDir {
    /// Creates a fresh, uniquely-named directory: `<tmp>/<prefix>-<pid>-<n>-<counter>`.
    pub fn new(prefix: &str) -> io::Result<Self> {
        let pid = std::process::id();
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0);
        let n = COUNTER.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!("{prefix}-{pid}-{nanos}-{n}"));
        std::fs::create_dir_all(&path)?;
        Ok(Self { path })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.path);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn creates_and_cleans_up() {
        let path;
        {
            let dir = TempDir::new("sandbox18-test").expect("create temp dir");
            path = dir.path().to_path_buf();
            assert!(path.is_dir(), "temp dir should exist while handle is alive");
        }
        assert!(!path.exists(), "temp dir should be removed after drop");
    }

    #[test]
    fn distinct_instances_get_distinct_paths() {
        let a = TempDir::new("sandbox18-test").unwrap();
        let b = TempDir::new("sandbox18-test").unwrap();
        assert_ne!(a.path(), b.path());
    }
}
