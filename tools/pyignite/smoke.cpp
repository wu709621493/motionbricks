// Bounded native-core smoke test; independent of Python and NumPy.
// This is not a CPU/cache diagnostic or an exhaustive numerical oracle.
#include "kernels.h"
#include <cmath>
#include <cstdio>
#include <limits>

static int fail(const char* name) {
    std::printf("{\"schema_version\":1,\"status\":\"FAIL\",\"check\":\"%s\"}\n", name);
    return 1;
}

int main() {
    const float x[] = {1, 2, 3, 4};
    const float w[] = {1, 2, -1, 1}, b[] = {0.5f, 0.25f};
    const float expected[] = {5.5f, 1.25f, 11.5f, 1.25f};
    const float identity[] = {1, 0, 0, 1}, zero[] = {0, 0};
    const IgniteLayer layers[] = {{2, 2, w, b}, {2, 2, identity, zero}};
    float scalar[4], fused[4], workspace[8];
    // Exactly representable answers. Repetition cannot detect common-mode
    // errors or certify the rest of the address space.
    for (int repeat = 0; repeat < 32; ++repeat) {
        if (ignite_linear(2, 2, 2, x, w, b, scalar, 0)) return fail("linear_status");
        if (ignite_fc(layers, 2, 2, x, fused, workspace, 2)) return fail("fused_status");
        for (int i = 0; i < 4; ++i)
            if (scalar[i] != expected[i] || fused[i] != expected[i]) return fail("known_answer");
    }
    const float negative[] = {-100, 100};
    if (ignite_linear(1, 2, 2, negative, identity, zero, scalar, 1) ||
        scalar[0] != -1 || scalar[1] != 100) return fail("leaky_relu");
    const float nan_input[] = {std::numeric_limits<float>::quiet_NaN(), 1};
    if (ignite_linear(1, 2, 2, nan_input, identity, zero, scalar, 0) != 2)
        return fail("nonfinite_rejection");
    const float max = std::numeric_limits<float>::max();
    const float huge[] = {max, max, max, max};
    if (ignite_linear(2, 2, 2, x, huge, zero, scalar, 0) != 2)
        return fail("overflow_rejection");
    float pe[4];
    if (ignite_pe(1, 4, pe) || pe[0] != 0 || pe[1] != 1 || pe[2] != 0 || pe[3] != 1)
        return fail("pe_origin_only");
    // Classic FDIV-sensitive pair. An SSE build exercises SSE, not x87;
    // the p5-x87 build is required for the historical instruction path.
    volatile double numerator = 4195835.0, denominator = 3145727.0;
    volatile double quotient = numerator / denominator;
    const double residual = numerator - quotient * denominator;
    if (!std::isfinite(residual) || std::fabs(residual) > 0.000001)
        return fail("division_residual");
    std::printf("{\"schema_version\":1,\"status\":\"PASS\",\"checks\":7,"
                "\"pointer_bits\":%u,\"scope\":\"native_core_smoke_only\"}\n",
                static_cast<unsigned>(sizeof(void*) * 8));
    return 0;
}
