//! Deterministic data generator for `18-rust-track`.
//!
//! Writes `data/access.log`, `data/products.csv`, and `data/ground-truth.json`
//! into the module root. Ground truth is computed from the same in-memory
//! records used to write the files, before any formatting/corruption is
//! applied, so it is an independent answer key rather than a re-parse of the
//! output. Honours the `SCALE` env var (default `1.0`). Fixed seed: reruns
//! must be byte-identical — verified by the orchestrator via sha256.

use std::collections::BTreeMap;

use sandbox18_harness::ground_truth::{
    CsvGroundTruth, GroundTruth, LogGroundTruth, PathCount, PriceStats, ResponseTimeStats,
};
use sandbox18_harness::prng::Xorshift64;

const SEED: u64 = 0xC0FFEE_5EED_u64;
const BASE_LOG_LINES: u64 = 200_000;
const BASE_CSV_ROWS: u64 = 500_000;

const LOG_PATHS: &[&str] = &[
    "/",
    "/index.html",
    "/api/products",
    "/api/products/1",
    "/api/products/2",
    "/api/products/3",
    "/api/categories",
    "/api/cart",
    "/api/cart/checkout",
    "/api/search",
    "/api/users/me",
    "/static/css/main.css",
    "/static/js/app.js",
    "/static/img/logo.png",
    "/favicon.ico",
    "/robots.txt",
    "/sitemap.xml",
    "/health",
    "/login",
    "/logout",
    "/register",
    "/api/orders",
    "/api/orders/1",
    "/about",
    "/contact",
];

const METHODS: &[(&str, f64)] = &[
    ("GET", 0.85),
    ("POST", 0.10),
    ("PUT", 0.03),
    ("DELETE", 0.02),
];

const STATUSES: &[(u16, f64)] = &[
    (200, 0.86),
    (201, 0.04),
    (301, 0.015),
    (302, 0.015),
    (400, 0.01),
    (403, 0.005),
    (404, 0.035),
    (500, 0.01),
    (502, 0.005),
    (503, 0.005),
];

const CATEGORIES: &[&str] = &[
    "Electronics",
    "Home & Garden",
    "Toys",
    "Books",
    "Clothing",
    "Sports",
    "Beauty",
    "Automotive",
    "Grocery",
    "Office",
    "Pet Supplies",
    "Health",
];

const MONTH_ABBR: &[&str] = &[
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

fn main() {
    let scale: f64 = std::env::var("SCALE")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(1.0);
    assert!(scale > 0.0, "SCALE must be positive, got {scale}");

    let module_root = sandbox18_harness::ground_truth::module_root();
    let data_dir = module_root.join("data");
    std::fs::create_dir_all(&data_dir).expect("create data dir");

    let start = std::time::Instant::now();

    let (log_text, log_truth) = generate_access_log(scale);
    let log_path = data_dir.join("access.log");
    std::fs::write(&log_path, &log_text).expect("write access.log");

    let (csv_text, csv_truth) = generate_products_csv(scale);
    let csv_path = data_dir.join("products.csv");
    std::fs::write(&csv_path, &csv_text).expect("write products.csv");

    let ground_truth = GroundTruth {
        seed: SEED,
        scale,
        log: log_truth,
        csv: csv_truth,
    };
    let json = serde_json::to_string_pretty(&ground_truth).expect("serialize ground truth");
    let gt_path = data_dir.join("ground-truth.json");
    std::fs::write(&gt_path, json.as_bytes()).expect("write ground-truth.json");

    let elapsed = start.elapsed();
    println!("wrote {} ({} bytes)", log_path.display(), log_text.len());
    println!("wrote {} ({} bytes)", csv_path.display(), csv_text.len());
    println!("wrote {} ({} bytes)", gt_path.display(), json.len());
    println!("scale={scale} elapsed={:.2}s", elapsed.as_secs_f64());
}

fn epoch_to_parts(epoch_secs: i64) -> (i64, u32, u32, u32, u32, u32) {
    let days = epoch_secs.div_euclid(86400);
    let secs_of_day = epoch_secs.rem_euclid(86400);
    let (year, month, day) = civil_from_days(days);
    let hh = (secs_of_day / 3600) as u32;
    let mm = ((secs_of_day % 3600) / 60) as u32;
    let ss = (secs_of_day % 60) as u32;
    (year, month, day, hh, mm, ss)
}

/// Howard Hinnant's `civil_from_days`: days since 1970-01-01 -> (year, month,
/// day) in the proleptic Gregorian calendar. Public-domain algorithm; kept
/// dependency-free rather than pulling in a date/time crate not on this
/// module's pinned dependency list.
fn civil_from_days(z: i64) -> (i64, u32, u32) {
    let z = z + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = (z - era * 146_097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146_096) / 365;
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    let year = if m <= 2 { y + 1 } else { y };
    (year, m, d)
}

fn format_clf_timestamp(epoch_secs: i64) -> String {
    let (year, month, day, hh, mm, ss) = epoch_to_parts(epoch_secs);
    format!(
        "{day:02}/{}/{year:04}:{hh:02}:{mm:02}:{ss:02} +0000",
        MONTH_ABBR[(month - 1) as usize]
    )
}

fn format_iso_timestamp(epoch_secs: i64) -> String {
    let (year, month, day, hh, mm, ss) = epoch_to_parts(epoch_secs);
    format!("{year:04}-{month:02}-{day:02}T{hh:02}:{mm:02}:{ss:02}Z")
}

fn weighted_pick<'a, T>(rng: &mut Xorshift64, table: &'a [(T, f64)]) -> &'a T {
    let total: f64 = table.iter().map(|(_, w)| w).sum();
    let mut target = rng.next_f64() * total;
    for (value, weight) in table {
        if target < *weight {
            return value;
        }
        target -= weight;
    }
    &table[table.len() - 1].0
}

fn gen_ip_pool(rng: &mut Xorshift64, n: usize) -> Vec<String> {
    (0..n)
        .map(|_| {
            format!(
                "{}.{}.{}.{}",
                rng.gen_range(1, 224),
                rng.gen_range(0, 256),
                rng.gen_range(0, 256),
                rng.gen_range(1, 255),
            )
        })
        .collect()
}

struct LogRecord {
    ip: String,
    epoch_secs: i64,
    method: &'static str,
    path: &'static str,
    status: u16,
    bytes: u64,
    response_time_ms: f64,
}

fn generate_access_log(scale: f64) -> (String, LogGroundTruth) {
    let mut rng = Xorshift64::new(SEED ^ 0xA11_0641);
    let n = ((BASE_LOG_LINES as f64) * scale).round() as u64;
    let n = n.max(1);

    let ip_pool = gen_ip_pool(&mut rng, 300);
    let base_epoch: i64 = 1_704_067_200; // 2024-01-01T00:00:00Z
    let window_secs: i64 = 86_400;

    let mut out = String::with_capacity((n as usize) * 140);
    let mut well_formed_lines: u64 = 0;
    let mut malformed_lines: u64 = 0;
    let mut status_class_counts: BTreeMap<String, u64> = BTreeMap::new();
    let mut method_counts: BTreeMap<String, u64> = BTreeMap::new();
    let mut path_counts: BTreeMap<String, u64> = BTreeMap::new();
    let mut ips_seen: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
    let mut response_times: Vec<f64> = Vec::with_capacity(n as usize);
    let mut sum_5xx: u64 = 0;

    for i in 0..n {
        let ip = ip_pool[rng.gen_range(0, ip_pool.len() as u64) as usize].clone();
        let path_idx = rng.zipf_rank(LOG_PATHS.len(), 1.1);
        let path = LOG_PATHS[path_idx];
        let method = *weighted_pick(&mut rng, METHODS);
        let status = *weighted_pick(&mut rng, STATUSES);
        let bytes = rng.gen_range(120, 65_536);
        let z = rng.next_standard_normal();
        let response_time_ms = ((3.4 + 0.7 * z).exp()).clamp(0.5, 4000.0);
        let jitter = rng.gen_range(0, 3);
        let epoch_secs =
            base_epoch + ((i as i64 * window_secs) / n as i64) + jitter as i64;

        let record = LogRecord {
            ip,
            epoch_secs,
            method,
            path,
            status,
            bytes,
            response_time_ms,
        };

        // ~1.5% of lines are corrupted at write time; the record itself
        // (and therefore the ground truth) is otherwise well-formed.
        let is_malformed = rng.next_f64() < 0.015;

        if is_malformed {
            malformed_lines += 1;
            out.push_str(&corrupt_line(&mut rng, &record));
        } else {
            well_formed_lines += 1;
            *status_class_counts
                .entry(status_class(record.status))
                .or_insert(0) += 1;
            *method_counts.entry(record.method.to_string()).or_insert(0) += 1;
            *path_counts.entry(record.path.to_string()).or_insert(0) += 1;
            ips_seen.insert(record.ip.clone());
            response_times.push(record.response_time_ms);
            if record.status >= 500 {
                sum_5xx += 1;
            }
            out.push_str(&format_log_line(&record));
        }
        out.push('\n');
    }

    response_times.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let response_time_stats = summarize_response_times(&response_times);

    let mut top_paths: Vec<PathCount> = path_counts
        .iter()
        .map(|(path, count)| PathCount {
            path: path.clone(),
            count: *count,
        })
        .collect();
    top_paths.sort_by(|a, b| b.count.cmp(&a.count).then_with(|| a.path.cmp(&b.path)));
    top_paths.truncate(10);

    let error_rate_5xx = if well_formed_lines > 0 {
        sum_5xx as f64 / well_formed_lines as f64
    } else {
        0.0
    };

    let truth = LogGroundTruth {
        total_lines: well_formed_lines + malformed_lines,
        well_formed_lines,
        malformed_lines,
        status_class_counts,
        method_counts,
        path_counts,
        top_paths,
        unique_ips: ips_seen.len() as u64,
        error_rate_5xx,
        response_time_ms: response_time_stats,
    };

    (out, truth)
}

fn status_class(status: u16) -> String {
    format!("{}xx", status / 100)
}

fn percentile(sorted: &[f64], p: f64) -> f64 {
    if sorted.is_empty() {
        return 0.0;
    }
    let rank = (p * (sorted.len() as f64 - 1.0)).round() as usize;
    sorted[rank.min(sorted.len() - 1)]
}

fn summarize_response_times(sorted: &[f64]) -> ResponseTimeStats {
    if sorted.is_empty() {
        return ResponseTimeStats {
            mean_ms: 0.0,
            p50_ms: 0.0,
            p95_ms: 0.0,
            p99_ms: 0.0,
            max_ms: 0.0,
        };
    }
    let sum: f64 = sorted.iter().sum();
    ResponseTimeStats {
        mean_ms: round2(sum / sorted.len() as f64),
        p50_ms: round2(percentile(sorted, 0.50)),
        p95_ms: round2(percentile(sorted, 0.95)),
        p99_ms: round2(percentile(sorted, 0.99)),
        max_ms: round2(*sorted.last().unwrap()),
    }
}

fn round2(v: f64) -> f64 {
    (v * 100.0).round() / 100.0
}

fn format_log_line(r: &LogRecord) -> String {
    format!(
        "{} - - [{}] \"{} {} HTTP/1.1\" {} {} \"-\" \"Mozilla/5.0 (compatible; sandbox18-bot/1.0)\" {:.1}",
        r.ip,
        format_clf_timestamp(r.epoch_secs),
        r.method,
        r.path,
        r.status,
        r.bytes,
        r.response_time_ms,
    )
}

fn corrupt_line(rng: &mut Xorshift64, r: &LogRecord) -> String {
    let good = format_log_line(r);
    match rng.gen_range(0, 5) {
        0 => good.replace('[', "").replace(']', ""),
        1 => good.replacen(&r.status.to_string(), "UNKNOWN", 1),
        2 => {
            let cut = good.len() / 2;
            good[..cut].to_string()
        }
        3 => good.replace('"', ""),
        _ => format!("{} EXTRA_GARBAGE_FIELD", good),
    }
}

struct ProductRecord {
    id: u64,
    sku: String,
    category: &'static str,
    price: f64,
    in_stock: bool,
    epoch_secs: i64,
}

fn generate_products_csv(scale: f64) -> (String, CsvGroundTruth) {
    let mut rng = Xorshift64::new(SEED ^ 0xC5_C0DE);
    let n = ((BASE_CSV_ROWS as f64) * scale).round() as u64;
    let n = n.max(1);

    let base_epoch: i64 = 1_704_067_200; // 2024-01-01T00:00:00Z
    let window_secs: i64 = 30 * 86_400;

    let mut out = String::with_capacity((n as usize) * 60);
    out.push_str("id,sku,category,price,in_stock,scraped_at\n");

    let mut total_rows: u64 = 0;
    let mut valid_rows: u64 = 0;
    let mut dirty_rows: u64 = 0;
    let mut in_stock_count: u64 = 0;
    let mut out_of_stock_count: u64 = 0;
    let mut category_counts: BTreeMap<String, u64> = BTreeMap::new();
    let mut category_prices: BTreeMap<String, Vec<f64>> = BTreeMap::new();
    let mut all_prices: Vec<f64> = Vec::with_capacity(n as usize);

    for i in 1..=n {
        let category_idx = rng.zipf_rank(CATEGORIES.len(), 0.6);
        let category = CATEGORIES[category_idx];
        let z = rng.next_standard_normal();
        let price = round2(((3.2 + 0.85 * z).exp()).clamp(0.99, 9999.99));
        let in_stock = rng.next_f64() < 0.82;
        let epoch_secs = base_epoch + rng.gen_range(0, window_secs as u64) as i64;
        let sku = format!("{}-{:07}", category_code(category), i);

        let record = ProductRecord {
            id: i,
            sku,
            category,
            price,
            in_stock,
            epoch_secs,
        };

        total_rows += 1;
        let is_dirty = rng.next_f64() < 0.02;

        if is_dirty {
            dirty_rows += 1;
            out.push_str(&corrupt_csv_row(&mut rng, &record));
        } else {
            valid_rows += 1;
            if record.in_stock {
                in_stock_count += 1;
            } else {
                out_of_stock_count += 1;
            }
            *category_counts.entry(record.category.to_string()).or_insert(0) += 1;
            category_prices
                .entry(record.category.to_string())
                .or_default()
                .push(record.price);
            all_prices.push(record.price);
            out.push_str(&format_csv_row(&record));
        }
        out.push('\n');
    }

    let category_price_stats: BTreeMap<String, PriceStats> = category_prices
        .iter()
        .map(|(cat, prices)| (cat.clone(), price_stats(prices)))
        .collect();
    let overall_price_stats = price_stats(&all_prices);

    let truth = CsvGroundTruth {
        total_rows,
        valid_rows,
        dirty_rows,
        in_stock_count,
        out_of_stock_count,
        category_counts,
        category_price_stats,
        overall_price_stats,
    };

    (out, truth)
}

fn category_code(category: &str) -> String {
    category
        .split_whitespace()
        .map(|w| w.chars().take(3).collect::<String>().to_uppercase())
        .collect::<Vec<_>>()
        .join("")
}

fn price_stats(prices: &[f64]) -> PriceStats {
    if prices.is_empty() {
        return PriceStats {
            count: 0,
            min: 0.0,
            max: 0.0,
            mean: 0.0,
            sum: 0.0,
        };
    }
    let sum: f64 = prices.iter().sum();
    let min = prices.iter().cloned().fold(f64::INFINITY, f64::min);
    let max = prices.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    PriceStats {
        count: prices.len() as u64,
        min: round2(min),
        max: round2(max),
        mean: round2(sum / prices.len() as f64),
        sum: round2(sum),
    }
}

fn format_csv_row(r: &ProductRecord) -> String {
    format!(
        "{},{},{},{:.2},{},{}",
        r.id,
        r.sku,
        r.category,
        r.price,
        r.in_stock,
        format_iso_timestamp(r.epoch_secs),
    )
}

fn corrupt_csv_row(rng: &mut Xorshift64, r: &ProductRecord) -> String {
    let good = format_csv_row(r);
    let mut fields: Vec<String> = good.split(',').map(|s| s.to_string()).collect();
    match rng.gen_range(0, 6) {
        0 => fields[3] = String::new(), // empty price
        1 => fields[3] = "N/A".to_string(),
        2 => fields[3] = format!("-{}", fields[3]), // negative price
        3 => fields[1] = String::new(),             // missing sku
        4 => fields[4] = "maybe".to_string(),        // bad boolean
        _ => fields[5] = "not-a-date".to_string(),   // bad timestamp
    }
    fields.join(",")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn civil_from_days_matches_known_dates() {
        assert_eq!(civil_from_days(0), (1970, 1, 1));
        assert_eq!(civil_from_days(19_723), (2024, 1, 1));
    }

    #[test]
    fn category_code_is_stable() {
        assert_eq!(category_code("Electronics"), "ELE");
        assert_eq!(category_code("Home & Garden"), "HOM&GAR");
        assert_eq!(category_code("Pet Supplies"), "PETSUP");
    }
}
