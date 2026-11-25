//! The `tokio`-based counterpart of [`crate::fixture_server`], for tasks 07
//! and 08. Same route configuration and stats shape, same "one request per
//! connection, ephemeral port" behaviour — only the I/O is async. Gated
//! behind the `async` feature so std-only tasks never compile tokio.

use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Duration;

use tokio::io::{AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{oneshot, Mutex};

pub use crate::fixture_server::{RouteConfig, ServerStats};

struct SharedState {
    routes: HashMap<String, RouteConfig>,
    default_route: RouteConfig,
    remaining_failures: Mutex<HashMap<String, usize>>,
    total_requests: AtomicU64,
    current_concurrency: AtomicUsize,
    max_concurrency: AtomicUsize,
    requests_by_path: Mutex<HashMap<String, u64>>,
}

pub struct AsyncFixtureServerBuilder {
    routes: HashMap<String, RouteConfig>,
    default_route: RouteConfig,
}

impl AsyncFixtureServerBuilder {
    pub fn route(mut self, path: impl Into<String>, config: RouteConfig) -> Self {
        self.routes.insert(path.into(), config);
        self
    }

    pub fn default_route(mut self, config: RouteConfig) -> Self {
        self.default_route = config;
        self
    }

    pub async fn start(self) -> AsyncFixtureServer {
        let listener = TcpListener::bind("127.0.0.1:0")
            .await
            .expect("bind ephemeral port");
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

        let (shutdown_tx, mut shutdown_rx) = oneshot::channel::<()>();
        let accept_state = Arc::clone(&state);

        let join_handle = tokio::spawn(async move {
            loop {
                tokio::select! {
                    _ = &mut shutdown_rx => break,
                    accepted = listener.accept() => {
                        if let Ok((stream, _addr)) = accepted {
                            let state = Arc::clone(&accept_state);
                            tokio::spawn(async move {
                                handle_connection(stream, state).await;
                            });
                        }
                    }
                }
            }
        });

        AsyncFixtureServer {
            port,
            state,
            shutdown_tx: Some(shutdown_tx),
            join_handle: Some(join_handle),
        }
    }
}

async fn handle_connection(stream: TcpStream, state: Arc<SharedState>) {
    let current = state.current_concurrency.fetch_add(1, Ordering::SeqCst) + 1;
    state.max_concurrency.fetch_max(current, Ordering::SeqCst);

    serve_one_request(stream, &state).await;

    state.current_concurrency.fetch_sub(1, Ordering::SeqCst);
}

async fn serve_one_request(stream: TcpStream, state: &SharedState) {
    let (read_half, mut write_half) = stream.into_split();
    let mut reader = BufReader::new(read_half);

    let mut request_line = String::new();
    if read_line(&mut reader, &mut request_line).await.unwrap_or(0) == 0 {
        return;
    }
    let path = request_line
        .split_whitespace()
        .nth(1)
        .unwrap_or("/")
        .to_string();

    let mut content_length: usize = 0;
    loop {
        let mut header_line = String::new();
        if read_line(&mut reader, &mut header_line).await.unwrap_or(0) == 0 {
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
        let _ = reader.read_exact(&mut body).await;
    }

    state.total_requests.fetch_add(1, Ordering::Relaxed);
    *state
        .requests_by_path
        .lock()
        .await
        .entry(path.clone())
        .or_insert(0) += 1;

    let should_fail = {
        let mut remaining = state.remaining_failures.lock().await;
        match remaining.get_mut(&path) {
            Some(n) if *n > 0 => {
                *n -= 1;
                true
            }
            _ => false,
        }
    };

    if should_fail {
        let _ = write_half.shutdown().await;
        return;
    }

    let config = state
        .routes
        .get(&path)
        .cloned()
        .unwrap_or_else(|| state.default_route.clone());

    if config.delay > Duration::ZERO {
        tokio::time::sleep(config.delay).await;
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

    let _ = write_half.write_all(&response).await;
    let _ = write_half.flush().await;
    let _ = write_half.shutdown().await;
}

async fn read_line<R: tokio::io::AsyncBufRead + Unpin>(
    reader: &mut R,
    buf: &mut String,
) -> std::io::Result<usize> {
    tokio::io::AsyncBufReadExt::read_line(reader, buf).await
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

/// A running async fixture server. Drop signals shutdown to the accept task
/// but does not block waiting for it (`Drop` cannot be async) — call
/// [`AsyncFixtureServer::shutdown`] for a deterministic, awaited stop.
pub struct AsyncFixtureServer {
    port: u16,
    state: Arc<SharedState>,
    shutdown_tx: Option<oneshot::Sender<()>>,
    join_handle: Option<tokio::task::JoinHandle<()>>,
}

impl AsyncFixtureServer {
    pub fn builder() -> AsyncFixtureServerBuilder {
        AsyncFixtureServerBuilder {
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

    pub async fn stats(&self) -> ServerStats {
        ServerStats {
            total_requests: self.state.total_requests.load(Ordering::Relaxed),
            max_concurrency: self.state.max_concurrency.load(Ordering::SeqCst) as u64,
            requests_by_path: self.state.requests_by_path.lock().await.clone(),
        }
    }

    /// Signals the accept loop to stop and awaits its task join.
    pub async fn shutdown(&mut self) {
        if let Some(tx) = self.shutdown_tx.take() {
            let _ = tx.send(());
        }
        if let Some(handle) = self.join_handle.take() {
            let _ = handle.await;
        }
    }
}

impl Drop for AsyncFixtureServer {
    fn drop(&mut self) {
        if let Some(tx) = self.shutdown_tx.take() {
            let _ = tx.send(());
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    async fn get(base_url: &str, path: &str) -> Option<(u16, String)> {
        let addr = base_url.trim_start_matches("http://");
        let mut stream = TcpStream::connect(addr).await.ok()?;
        stream
            .write_all(format!("GET {path} HTTP/1.1\r\nHost: {addr}\r\n\r\n").as_bytes())
            .await
            .ok()?;
        let mut response = String::new();
        stream.read_to_string(&mut response).await.ok()?;
        if response.is_empty() {
            return None;
        }
        let status_line = response.lines().next()?;
        let status: u16 = status_line.split_whitespace().nth(1)?.parse().ok()?;
        let body = response.split("\r\n\r\n").nth(1).unwrap_or("").to_string();
        Some((status, body))
    }

    #[tokio::test]
    async fn serves_configured_body_and_status() {
        let server = AsyncFixtureServer::builder()
            .route("/hello", RouteConfig::new(200, "world"))
            .start()
            .await;

        let (status, body) = get(&server.base_url(), "/hello")
            .await
            .expect("request should succeed");
        assert_eq!(status, 200);
        assert_eq!(body, "world");
    }

    #[tokio::test]
    async fn fail_first_n_then_succeeds() {
        let server = AsyncFixtureServer::builder()
            .route("/flaky", RouteConfig::new(200, "ok").fail_first(1))
            .start()
            .await;

        let attempt1 = get(&server.base_url(), "/flaky").await;
        let attempt2 = get(&server.base_url(), "/flaky").await;

        assert!(attempt1.is_none(), "first attempt should fail: {attempt1:?}");
        let (status, body) = attempt2.expect("second attempt should succeed");
        assert_eq!(status, 200);
        assert_eq!(body, "ok");
    }

    #[tokio::test]
    async fn counts_requests_under_tokio() {
        let mut server = AsyncFixtureServer::builder()
            .route("/a", RouteConfig::new(200, "a"))
            .start()
            .await;

        get(&server.base_url(), "/a").await;
        get(&server.base_url(), "/a").await;

        let stats = server.stats().await;
        assert_eq!(stats.total_requests, 2, "stats: {stats:?}");
        assert_eq!(stats.requests_by_path.get("/a"), Some(&2));

        server.shutdown().await;
    }
}
