// Test-only text protocol: one bounded request per process, no model loading.
use motionbricks_core::{Codebook, Matrix};
use std::io::{self, Read};
use std::str::{FromStr, SplitWhitespace};
fn read<T: FromStr>(tokens: &mut SplitWhitespace<'_>) -> Result<T, String> {
    tokens
        .next()
        .ok_or("missing token")?
        .parse()
        .map_err(|_| "invalid token".into())
}
fn floats(tokens: &mut SplitWhitespace<'_>, n: usize) -> Result<Vec<f32>, String> {
    if n > 100_000 {
        return Err("fixture too large".into());
    }
    (0..n).map(|_| read(tokens)).collect()
}
fn run() -> Result<(), String> {
    let mut input = String::new();
    io::stdin()
        .take(2_000_001)
        .read_to_string(&mut input)
        .map_err(|e| e.to_string())?;
    if input.len() > 2_000_000 {
        return Err("request too large".into());
    }
    let mut t = input.split_whitespace();
    let op = t.next().ok_or("missing operation")?;
    let mut dim = || -> Result<usize, String> {
        let n = read::<usize>(&mut t)?;
        if n == 0 || n > 256 {
            return Err("dimension outside 1..256".into());
        }
        Ok(n)
    };
    let a = dim()?;
    let b = dim()?;
    let c = dim()?;
    let result = match op {
        "linear" => {
            let x = Matrix::new(a, b, floats(&mut t, a * b)?).map_err(|e| format!("{e:?}"))?;
            let w = Matrix::new(c, b, floats(&mut t, c * b)?).map_err(|e| format!("{e:?}"))?;
            x.linear(&w, &floats(&mut t, c)?)
        }
        "softmax" | "relu" => {
            if c != 1 {
                return Err("reserved dimension must be 1".into());
            }
            let x = Matrix::new(a, b, floats(&mut t, a * b)?).map_err(|e| format!("{e:?}"))?;
            if op == "softmax" {
                x.softmax()
            } else {
                x.relu()
            }
        }
        "codebook" => {
            let book =
                Codebook::new(a, b, c, floats(&mut t, a * b * c)?).map_err(|e| format!("{e:?}"))?;
            let batch: usize = read(&mut t)?;
            let frames: usize = read(&mut t)?;
            let n = batch
                .checked_mul(frames)
                .filter(|n| *n <= 100_000)
                .ok_or("too many indices")?;
            let indices: Vec<u64> = (0..n).map(|_| read(&mut t)).collect::<Result<_, _>>()?;
            book.decode_overall(batch, frames, &indices)
        }
        _ => return Err("unsupported operation".into()),
    }
    .map_err(|e| format!("{e:?}"))?;
    if t.next().is_some() {
        return Err("trailing tokens".into());
    }
    for value in result.data() {
        println!("{value:.9e}");
    }
    Ok(())
}
fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(2);
    }
}
