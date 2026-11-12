// Semantics adapted from tools/onnx/models/layers.py.
// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
#include <cmath>
#include <cstddef>
#include <limits>
#include "kernels.h"

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

// Private fused ABI. Python owns immutable, already-validated weights and all
// disjoint buffers for the duration of this call. Keep ignite_linear unchanged
// as the independently checked scalar reference / legacy ABI.
extern "C" int ignite_fc(const IgniteLayer* layers, size_t count, size_t rows,
                         const float* x, float* y, float* workspace, size_t width) {
    if (!layers || count < 2 || !x || !y || !workspace ||
        !product(rows, width) || rows * width > std::numeric_limits<size_t>::max() / sizeof(float) / 2)
        return 1;
    for (size_t l = 0; l < count; ++l) {
        const auto& layer = layers[l];
        if (!layer.weight || !layer.bias || !product(rows, layer.in) ||
            !product(rows, layer.out) || !product(layer.in, layer.out) ||
            (l && layers[l-1].out != layer.in) ||
            (l+1 < count && layer.out > width)) return 1;
    }
    const float* h = x;
    for (size_t l = 0; l < count; ++l) {
        const auto& layer = layers[l];
        float* out = l+1 == count ? y : workspace + (l % 2) * rows * width;
        for (size_t r = 0; r < rows; ++r) for (size_t o = 0; o < layer.out; ++o) {
            float sum = layer.bias[o];
            for (size_t k = 0; k < layer.in; ++k)
                sum += h[r*layer.in+k] * layer.weight[o*layer.in+k];
            if (!std::isfinite(sum)) return 2;
            out[r*layer.out+o] = l+1 < count && sum < 0 ? sum * 0.01f : sum;
        }
        h = out;
    }
    return 0;
}

