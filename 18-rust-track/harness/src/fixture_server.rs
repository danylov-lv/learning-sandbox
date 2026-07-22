//! A blocking, single-purpose HTTP/1.1 test server on `std::net::TcpListener`,
//! bound to an ephemeral port (`127.0.0.1:0` — this module never claims a
//! fixed host port). Every task that needs "a website to talk to" points its
//! own hand-rolled HTTP client at this instead of a real network call.
//!
//! One request per connection (no keep-alive): the server reads a request
//! line and headers, writes a status line + headers + body, and closes the
//! connection. This matches the plain-`TcpStream` HTTP clients the tasks are
//! meant to write themselves.
//!
//! ```no_run
//! use sandbox18_harness::fixture_server::{FixtureServer, RouteConfig};
//! use std::time::Duration;
//!
//! let server = FixtureServer::builder()
//!     .route("/ok", RouteConfig::new(200, "hello"))
//!     .route("/flaky", RouteConfig::new(200, "eventually ok").fail_first(2))
//!     .route("/slow", RouteConfig::new(200, "slow ok").with_delay(Duration::from_millis(50)))
//!     .default_route(RouteConfig::new(404, "not found"))
//!     .start();
//!
//! let url = server.base_url();
//! // ... point a std::net::TcpStream-based client at `url` ...
//! let stats = server.stats();
//! assert!(stats.total_requests >= 0);
//! ```

use std::collections::HashMap;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::Duration;

/// Per-path behaviour for the fixture server.
#[derive(Debug, Clone)]
pub struct RouteConfig {
    pub status: u16,
    pub body: Vec<u8>,
    pub content_type: String,
    pub delay: Duration,
    /// Number of requests to this route that should fail (the connection is
    /// dropped with no response written at all, simulating a network
    /// failure) before it starts succeeding normally.
    pub fail_first_n: usize,
}

impl RouteConfig {
    pub fn new(status: u16, body: impl Into<Vec<u8>>) -> Self {
        Self {
            status,
            body: body.into(),
            content_type: "text/plain".to_string(),
            delay: Duration::ZERO,
            fail_first_n: 0,
        }
    }

    pub fn with_delay(mut self, delay: Duration) -> Self {
        self.delay = delay;
        self
    }

    pub fn with_content_type(mut self, content_type: impl Into<String>) -> Self {
        self.content_type = content_type.into();
        self
    }

    pub fn fail_first(mut self, n: usize) -> Self {
        self.fail_first_n = n;
        self
    }
}

#[derive(Debug, Clone, Default)]
pub struct ServerStats {
    pub total_requests: u64,
    pub max_concurrency: u64,
    pub requests_by_path: HashMap<String, u64>,
}

struct SharedState {
    routes: HashMap<String, RouteConfig>,
    default_route: RouteConfig,
    remaining_failures: Mutex<HashMap<String, usize>>,
    total_requests: AtomicU64,
    current_concurrency: AtomicUsize,
    max_concurrency: AtomicUsize,
    requests_by_path: Mutex<HashMap<String, u64>>,
}

pub struct FixtureServerBuilder {
    routes: HashMap<String, RouteConfig>,
    default_route: RouteConfig,
}

impl FixtureServerBuilder {
    pub fn route(mut self, path: impl Into<String>, config: RouteConfig) -> Self {
        self.routes.insert(path.into(), config);
        self
    }

    pub fn default_route(mut self, config: RouteConfig) -> Self {
        self.default_route = config;
        self
    }

    pub fn start(self) -> FixtureServer {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind ephemeral port");
        listener
            .set_nonblocking(true)
            .expect("set listener non-blocking");
        let port = listener.local_addr().expect("local addr").port();

        let mut remaining_failures = HashMap::new();
        for (path, cfg) in &self.routes {
            if cfg.fail_first_n > 0 {
                remaining_failures.insert(path.clone(), cfg.fail_first_n);
            }
        }

        let state = Arc::new(SharedState {
            routes: self.routes,
            default_route: self.default_route,
            remaining_failures: Mutex::new(remaining_failures),
            total_requests: AtomicU64::new(0),
            current_concurrency: AtomicUsize::new(0),
            max_concurrency: AtomicUsize::new(0),
            requests_by_path: Mutex::new(HashMap::new()),
        });

        let shutdown = Arc::new(AtomicBool::new(false));
        let accept_state = Arc::clone(&state);
        let accept_shutdown = Arc::clone(&shutdown);

        let accept_thread = std::thread::spawn(move || {
            accept_loop(listener, accept_state, accept_shutdown);
        });

        FixtureServer {
            port,
            shutdown,
            accept_thread: Some(accept_thread),
            state,
        }
    }
}

fn accept_loop(listener: TcpListener, state: Arc<SharedState>, shutdown: Arc<AtomicBool>) {
    while !shutdown.load(Ordering::Relaxed) {
        match listener.accept() {
            Ok((stream, _addr)) => {
                let state = Arc::clone(&state);
                std::thread::spawn(move || handle_connection(stream, &state));
            }
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(5));
            }
            Err(_) => {
                std::thread::sleep(Duration::from_millis(5));
            }
        }
    }
}

fn handle_connection(mut stream: TcpStream, state: &SharedState) {
    let current = state.current_concurrency.fetch_add(1, Ordering::SeqCst) + 1;
    state.max_concurrency.fetch_max(current, Ordering::SeqCst);

    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        serve_one_request(&mut stream, state);
    }));

    state.current_concurrency.fetch_sub(1, Ordering::SeqCst);
    if result.is_err() {
        let _ = stream.shutdown(std::net::Shutdown::Both);
    }
}

fn serve_one_request(stream: &mut TcpStream, state: &SharedState) {
    let mut reader = BufReader::new(stream.try_clone().expect("clone stream for reading"));

    let mut request_line = String::new();
    if reader.read_line(&mut request_line).unwrap_or(0) == 0 {
        return; // connection closed before sending anything
    }
    let path = parse_path(&request_line);

    let mut content_length: usize = 0;
    loop {
        let mut header_line = String::new();
        if reader.read_line(&mut header_line).unwrap_or(0) == 0 {
            break;
        }
        let trimmed = header_line.trim();
        if trimmed.is_empty() {
            break;
        }
        if let Some(value) = trimmed
            .split_once(':')
            .filter(|(k, _)| k.trim().eq_ignore_ascii_case("content-length"))
            .map(|(_, v)| v.trim())
        {
            content_length = value.parse().unwrap_or(0);
        }
    }
    if content_length > 0 {
        let mut body = vec![0u8; content_length];
        let _ = reader.read_exact(&mut body);
    }

    state.total_requests.fetch_add(1, Ordering::Relaxed);
    *state
        .requests_by_path
        .lock()
        .expect("requests_by_path lock")
        .entry(path.clone())
        .or_insert(0) += 1;

    let should_fail = {
        let mut remaining = state
            .remaining_failures
            .lock()
            .expect("remaining_failures lock");
        match remaining.get_mut(&path) {
            Some(n) if *n > 0 => {
                *n -= 1;
                true
            }
            _ => false,
        }
    };

    if should_fail {
        // Simulate a network failure: drop the connection with no response.
        let _ = stream.shutdown(std::net::Shutdown::Both);
        return;
    }

    let config = state
        .routes
        .get(&path)
        .cloned()
        .unwrap_or_else(|| state.default_route.clone());

    if config.delay > Duration::ZERO {
        std::thread::sleep(config.delay);
    }

    let status_text = reason_phrase(config.status);
    let mut response = format!(
        "HTTP/1.1 {} {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        config.status,
        status_text,
        config.content_type,
        config.body.len(),
    )
    .into_bytes();
    response.extend_from_slice(&config.body);

    let _ = stream.write_all(&response);
    let _ = stream.flush();
    let _ = stream.shutdown(std::net::Shutdown::Both);
}

fn parse_path(request_line: &str) -> String {
    request_line
        .split_whitespace()
        .nth(1)
        .unwrap_or("/")
        .to_string()
}

fn reason_phrase(status: u16) -> &'static str {
    match status {
        200 => "OK",
        201 => "Created",
        204 => "No Content",
        301 => "Moved Permanently",
        302 => "Found",
        400 => "Bad Request",
        401 => "Unauthorized",
        403 => "Forbidden",
        404 => "Not Found",
        408 => "Request Timeout",
        429 => "Too Many Requests",
        500 => "Internal Server Error",
        502 => "Bad Gateway",
        503 => "Service Unavailable",
        504 => "Gateway Timeout",
        _ => "Unknown",
    }
}

/// A running fixture server. Dropping it stops the accept loop and joins the
/// accept thread.
pub struct FixtureServer {
    port: u16,
    shutdown: Arc<AtomicBool>,
    accept_thread: Option<JoinHandle<()>>,
    state: Arc<SharedState>,
}

impl FixtureServer {
    pub fn builder() -> FixtureServerBuilder {
        FixtureServerBuilder {
            routes: HashMap::new(),
            default_route: RouteConfig::new(404, "not found"),
        }
    }

    pub fn base_url(&self) -> String {
        format!("http://127.0.0.1:{}", self.port)
    }

    pub fn port(&self) -> u16 {
        self.port
    }

    pub fn stats(&self) -> ServerStats {
        ServerStats {
            total_requests: self.state.total_requests.load(Ordering::Relaxed),
            max_concurrency: self.state.max_concurrency.load(Ordering::SeqCst) as u64,
            requests_by_path: self
                .state
                .requests_by_path
                .lock()
                .expect("requests_by_path lock")
                .clone(),
        }
    }
}

impl Drop for FixtureServer {
    fn drop(&mut self) {
        self.shutdown.store(true, Ordering::Relaxed);
        if let Some(handle) = self.accept_thread.take() {
            let _ = handle.join();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn get(base_url: &str, path: &str) -> Option<(u16, String)> {
        let addr = base_url.trim_start_matches("http://");
        let mut stream = TcpStream::connect(addr).ok()?;
        stream
            .write_all(format!("GET {path} HTTP/1.1\r\nHost: {addr}\r\n\r\n").as_bytes())
            .ok()?;
        let mut response = String::new();
        stream.read_to_string(&mut response).ok()?;
        if response.is_empty() {
            return None;
        }
        let status_line = response.lines().next()?;
        let status: u16 = status_line.split_whitespace().nth(1)?.parse().ok()?;
        let body = response.split("\r\n\r\n").nth(1).unwrap_or("").to_string();
        Some((status, body))
    }

    #[test]
    fn serves_configured_body_and_status() {
        let server = FixtureServer::builder()
            .route("/hello", RouteConfig::new(200, "world"))
            .start();

        let (status, body) = get(&server.base_url(), "/hello").expect("request should succeed");
        assert_eq!(status, 200, "expected 200, got {status}");
        assert_eq!(body, "world", "expected body 'world', got {body:?}");
    }

    #[test]
    fn falls_back_to_default_route() {
        let server = FixtureServer::builder()
            .default_route(RouteConfig::new(404, "nope"))
            .start();

        let (status, body) = get(&server.base_url(), "/unknown").expect("request should succeed");
        assert_eq!(status, 404);
        assert_eq!(body, "nope");
    }

    #[test]
    fn fail_first_n_then_succeeds() {
        let server = FixtureServer::builder()
            .route("/flaky", RouteConfig::new(200, "ok").fail_first(2))
            .start();

        let attempt1 = get(&server.base_url(), "/flaky");
        let attempt2 = get(&server.base_url(), "/flaky");
        let attempt3 = get(&server.base_url(), "/flaky");

        assert!(
            attempt1.is_none(),
            "first attempt should fail (connection dropped), got {attempt1:?}"
        );
        assert!(
            attempt2.is_none(),
            "second attempt should fail (connection dropped), got {attempt2:?}"
        );
        let (status, body) = attempt3.expect("third attempt should succeed");
        assert_eq!(status, 200);
        assert_eq!(body, "ok");
    }

    #[test]
    fn counts_total_requests_and_by_path() {
        let server = FixtureServer::builder()
            .route("/a", RouteConfig::new(200, "a"))
            .route("/b", RouteConfig::new(200, "b"))
            .start();

        get(&server.base_url(), "/a");
        get(&server.base_url(), "/a");
        get(&server.base_url(), "/b");

        let stats = server.stats();
        assert_eq!(stats.total_requests, 3, "stats: {stats:?}");
        assert_eq!(stats.requests_by_path.get("/a"), Some(&2));
        assert_eq!(stats.requests_by_path.get("/b"), Some(&1));
    }

    #[test]
    fn observes_concurrency_above_one() {
        let server = Arc::new(
            FixtureServer::builder()
                .route(
                    "/slow",
                    RouteConfig::new(200, "ok").with_delay(Duration::from_millis(80)),
                )
                .start(),
        );

        let handles: Vec<_> = (0..5)
            .map(|_| {
                let base_url = server.base_url();
                std::thread::spawn(move || get(&base_url, "/slow"))
            })
            .collect();
        for h in handles {
            let _ = h.join();
        }

        let stats = server.stats();
        assert!(
            stats.max_concurrency > 1,
            "expected concurrent requests to overlap, max_concurrency={}",
            stats.max_concurrency
        );
    }
}
