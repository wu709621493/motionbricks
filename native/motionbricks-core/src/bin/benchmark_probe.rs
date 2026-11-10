//! Review-only native timings. Fixture construction and stdout are outside timing.
use motionbricks_core::{Codebook, Matrix};
use std::{hint::black_box, time::Instant};

fn values(n: usize, modulus: usize) -> Vec<f32> {
    (0..n)
        .map(|i| ((i % modulus) as f32 - (modulus / 2) as f32) / 32.0)
        .collect()
}

fn measure(mut call: impl FnMut() -> Matrix) {
    for _ in 0..5 {
        black_box(call());
    }
    let mut samples = Vec::new();
    for _ in 0..30 {
        let start = Instant::now();
        for _ in 0..20 {
            black_box(call());
        }
        samples.push(start.elapsed().as_secs_f64() * 1e6 / 20.0);
    }
    let output = call();
    let rss = std::fs::read_to_string("/proc/self/status")
        .ok()
        .and_then(|s| {
            s.lines()
                .find(|line| line.starts_with("VmHWM:"))
                .and_then(|line| line.split_whitespace().nth(1)?.parse::<u64>().ok())
        })
        .map(|kib| kib * 1024);
    println!(
        "{{\"samples_us\":{samples:?},\"peak_rss_bytes\":{},\"values\":{:?}}}",
        rss.map_or_else(|| "null".to_string(), |n| n.to_string()),
        output.data()
    );
}

fn main() {
    let case: usize = std::env::args().nth(1).expect("case 0..8").parse().unwrap();
    assert!(case < 9);
    if case < 6 {
        let rows = [1, 32, 256][case / 2];
        let book = Codebook::new(8, 10, 32, values(2560, 257)).unwrap();
        let ids: Vec<u64> = (0..rows).map(|i| (i as u64 * 7919) % 100_000_000).collect();
        let heads: Vec<usize> = ids
            .iter()
            .flat_map(|id| (0..8).map(move |h| ((id / 10u64.pow(h)) % 10) as usize))
            .collect();
        if case % 2 == 0 {
            measure(|| book.decode_overall(1, rows, black_box(&ids)).unwrap());
        } else {
            measure(|| book.decode_heads(1, rows, black_box(&heads)).unwrap());
        }
    } else {
        let (rows, inputs, outputs) = [(1, 32, 32), (32, 128, 64), (32, 256, 256)][case - 6];
        let x = Matrix::new(rows, inputs, values(rows * inputs, 31)).unwrap();
        let w = Matrix::new(outputs, inputs, values(outputs * inputs, 31)).unwrap();
        let b = values(outputs, 31);
        measure(|| x.linear(black_box(&w), black_box(&b)).unwrap());
    }
}
