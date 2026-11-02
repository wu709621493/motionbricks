// Semantics adapted from tools/onnx/models/layers.py.
// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
#include <cmath>
#include <cstddef>
#include <limits>

// Private C ABI. Callers must supply valid, disjoint buffers of the stated sizes.
// Python validates buffers; no exceptions or C++ objects cross this boundary.
static bool product(size_t a, size_t b) {
    return a && b && a <= std::numeric_limits<size_t>::max() / b / sizeof(float);
}
extern "C" int ignite_pe(size_t n, size_t d, float* out) {
    if (!out || d % 2 || !product(n, d)) return 1;
    const float scale = static_cast<float>(-std::log(10000.0) / d);
    for (size_t j = 0; j < d; j += 2) {
        const float f = std::exp(static_cast<float>(j) * scale);
        for (size_t i = 0; i < n; ++i) {
            const float phase = static_cast<float>(i) * f;
            out[i*d+j] = std::sin(phase);
            out[i*d+j+1] = std::cos(phase);
        }
    }
    return 0;
}
extern "C" int ignite_linear(size_t rows, size_t in, size_t out,
                             const float* x, const float* w, const float* b,
                             float* y, int activate) {
    if (!x || !w || !b || !y || !product(rows,in) ||
        !product(in,out) || !product(rows,out)) return 1;
    for (size_t i=0; i<rows*in; ++i) if (!std::isfinite(x[i])) return 2;
    for (size_t i=0; i<in*out; ++i) if (!std::isfinite(w[i])) return 2;
    for (size_t i=0; i<out; ++i) if (!std::isfinite(b[i])) return 2;
    for (size_t r=0; r<rows; ++r) for (size_t o=0; o<out; ++o) {
        float sum = b[o];
        for (size_t k=0; k<in; ++k) sum += x[r*in+k]*w[o*in+k];
        if (!std::isfinite(sum)) return 2;
        y[r*out+o] = activate && sum < 0 ? sum * 0.01f : sum;
    }
    return 0;
}
