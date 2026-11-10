// SPDX-License-Identifier: Apache-2.0
//! CPU reference primitives, not a full model or PyTorch API replacement.
#![forbid(unsafe_code)]

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Error {
    Shape,
    NonFinite,
    Index,
    Limit,
    Allocation,
}
pub type Result<T> = std::result::Result<T, Error>;
// Per-buffer cap, not a process memory or real-time guarantee.
pub const MAX_ELEMENTS: usize = 16 * 1024 * 1024;

fn count(dims: &[usize]) -> Result<usize> {
    if dims.is_empty() || dims.contains(&0) {
        return Err(Error::Shape);
    }
    let n = dims
        .iter()
        .try_fold(1usize, |n, d| n.checked_mul(*d))
        .ok_or(Error::Limit)?;
    if n > MAX_ELEMENTS {
        return Err(Error::Limit);
    }
    Ok(n)
}
fn finite(values: &[f32]) -> Result<()> {
    if values.iter().all(|x| x.is_finite()) {
        Ok(())
    } else {
        Err(Error::NonFinite)
    }
}
fn buffer(n: usize) -> Result<Vec<f32>> {
    if n > MAX_ELEMENTS {
        return Err(Error::Limit);
    }
    let mut values = Vec::new();
    values.try_reserve_exact(n).map_err(|_| Error::Allocation)?;
    values.resize(n, 0.0);
    Ok(values)
}

/// Owned contiguous row-major FP32 matrix. No broadcasting or implicit casts.
#[derive(Debug, Clone)]
pub struct Matrix {
    rows: usize,
    cols: usize,
    data: Vec<f32>,
}
impl Matrix {
    pub fn new(rows: usize, cols: usize, data: Vec<f32>) -> Result<Self> {
        if count(&[rows, cols])? != data.len() {
            return Err(Error::Shape);
        }
        finite(&data)?;
        Ok(Self { rows, cols, data })
    }
    pub fn shape(&self) -> (usize, usize) {
        (self.rows, self.cols)
    }
    pub fn data(&self) -> &[f32] {
        &self.data
    }
    /// PyTorch nn.Linear convention: x [N,I], weight [O,I], bias [O].
    pub fn linear(&self, weight: &Matrix, bias: &[f32]) -> Result<Self> {
        if self.cols != weight.cols || bias.len() != weight.rows {
            return Err(Error::Shape);
        }
        finite(bias)?;
        let mut y = buffer(count(&[self.rows, weight.rows])?)?;
        for r in 0..self.rows {
            for o in 0..weight.rows {
                let mut sum = bias[o];
                for i in 0..self.cols {
                    sum += self.data[r * self.cols + i] * weight.data[o * weight.cols + i];
                }
                y[r * weight.rows + o] = sum;
            }
        }
        Self::new(self.rows, weight.rows, y)
    }
    pub fn relu(&self) -> Result<Self> {
        let mut y = buffer(self.data.len())?;
        for (out, x) in y.iter_mut().zip(&self.data) {
            *out = x.max(0.0);
        }
        Self::new(self.rows, self.cols, y)
    }
    /// Stable softmax over last dimension. Finite input/output only.
    pub fn softmax(&self) -> Result<Self> {
        let mut y = buffer(self.data.len())?;
        for (x, out) in self.data.chunks(self.cols).zip(y.chunks_mut(self.cols)) {
            let max = x.iter().copied().fold(f32::NEG_INFINITY, f32::max);
            let mut sum = 0.0;
            for (dst, src) in out.iter_mut().zip(x) {
                *dst = (src - max).exp();
                sum += *dst;
            }
            for dst in out {
                *dst /= sum;
            }
        }
        Self::new(self.rows, self.cols, y)
    }
}

/// Port of tools/onnx/models/quantizer.py's inference lookup semantics.
/// Storage [head, entry, width]; output flattened [batch*frames, head*width].
/// Original module: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES,
/// Apache-2.0. Upstream attribution is retained in NOTICE.md.
pub struct Codebook {
    heads: usize,
    entries: usize,
    width: usize,
    data: Vec<f32>,
    space: u64,
}
impl Codebook {
    pub fn new(heads: usize, entries: usize, width: usize, data: Vec<f32>) -> Result<Self> {
        if count(&[heads, entries, width])? != data.len() {
            return Err(Error::Shape);
        }
        finite(&data)?;
        let space = (0..heads)
            .try_fold(1u64, |n, _| n.checked_mul(entries as u64))
            .ok_or(Error::Limit)?;
        Ok(Self {
            heads,
            entries,
            width,
            data,
            space,
        })
    }
    pub fn code_space(&self) -> u64 {
        self.space
    }
    /// Lowest head is least significant base-entries digit.
    /// Reject out-of-range overall indices (upstream modulo would wrap).
    pub fn decode_overall(&self, batch: usize, frames: usize, indices: &[u64]) -> Result<Matrix> {
        let rows = count(&[batch, frames])?;
        if indices.len() != rows {
            return Err(Error::Shape);
        }
        if indices.iter().any(|i| *i >= self.space) {
            return Err(Error::Index);
        }
        let cols = count(&[self.heads, self.width])?;
        let mut y = buffer(count(&[rows, cols])?)?;
        for (r, index) in indices.iter().enumerate() {
            let mut code = *index;
            for h in 0..self.heads {
                let entry = (code % self.entries as u64) as usize;
                code /= self.entries as u64;
                let start = (h * self.entries + entry) * self.width;
                let dest = r * cols + h * self.width;
                y[dest..dest + self.width].copy_from_slice(&self.data[start..start + self.width]);
            }
        }
        Matrix::new(rows, cols, y)
    }
    pub fn decode_heads(&self, batch: usize, frames: usize, indices: &[usize]) -> Result<Matrix> {
        let rows = count(&[batch, frames])?;
        if indices.len() != count(&[rows, self.heads])? {
            return Err(Error::Shape);
        }
        if indices.iter().any(|i| *i >= self.entries) {
            return Err(Error::Index);
        }
        let cols = count(&[self.heads, self.width])?;
        let mut y = buffer(count(&[rows, cols])?)?;
        for r in 0..rows {
            for h in 0..self.heads {
                let start = (h * self.entries + indices[r * self.heads + h]) * self.width;
                let dest = r * cols + h * self.width;
                y[dest..dest + self.width].copy_from_slice(&self.data[start..start + self.width]);
            }
        }
        Matrix::new(rows, cols, y)
    }
}
