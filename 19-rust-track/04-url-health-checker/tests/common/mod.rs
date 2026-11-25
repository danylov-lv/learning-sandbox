use std::net::TcpListener;

/// Binds an ephemeral port and immediately drops the listener, freeing the
/// port while leaving nothing listening on it. Connecting there afterward
/// should fail with "connection refused" essentially immediately -- no real
/// network involved, and no fixed port claimed.
pub fn closed_port() -> u16 {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind ephemeral port");
    let port = listener.local_addr().expect("read local addr").port();
    drop(listener);
    port
}
