// Private C ABI shared by the kernels and the Python-independent smoke runner.
#pragma once
#include <cstddef>
struct IgniteLayer {
    size_t in, out;
    const float *weight, *bias;
};
extern "C" int ignite_pe(size_t n, size_t d, float* out);
extern "C" int ignite_linear(size_t rows, size_t in, size_t out,
                             const float* x, const float* w, const float* b,
                             float* y, int activate);
extern "C" int ignite_fc(const IgniteLayer* layers, size_t count, size_t rows,
                         const float* x, float* y, float* workspace, size_t width);
