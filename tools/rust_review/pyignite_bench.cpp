// Review harness only; links the unchanged PyIgnite kernel in another TU.
// SPDX-License-Identifier: Apache-2.0
#include <chrono>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <fstream>
#include <string>
#include <vector>
extern "C" int ignite_linear(size_t, size_t, size_t, const float*, const float*,
                             const float*, float*, int);
static std::vector<float> values(size_t n) {
    std::vector<float> v(n);
    for (size_t i=0; i<n; ++i) v[i] = (static_cast<int>(i%31)-15)/32.0f;
    return v;
}
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    const int c = std::atoi(argv[1])-6;
    if (c<0 || c>2) return 2;
    const size_t dims[3][3] = {{1,32,32},{32,128,64},{32,256,256}};
    const auto r=dims[c][0], i=dims[c][1], o=dims[c][2];
    const auto x=values(r*i), w=values(o*i), b=values(o);
    auto call = [&]() {
        // Include zero initialization/allocation, like the Rust owned-output API.
        std::vector<float> y(r*o, 0.0f);
        if (ignite_linear(r,i,o,x.data(),w.data(),b.data(),y.data(),0)) std::abort();
        return y;
    };
    volatile float sink=0;
    for (int k=0;k<5;++k) sink=call()[0];
    std::cout << std::setprecision(9) << "{\"samples_us\":[";
    for (int s=0;s<30;++s) {
        auto start=std::chrono::steady_clock::now();
        for (int k=0;k<20;++k) sink=call()[0];
        const double us=std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count()/20;
        std::cout << (s?",":"") << us;
    }
    const auto y=call();
    std::cout << "],\"values\":[";
    for (size_t j=0;j<y.size();++j) std::cout << (j?",":"") << y[j];
    std::ifstream status("/proc/self/status");
    std::string key, line;
    size_t rss=0;
    while (status >> key) {
        if (key == "VmHWM:") { status >> rss; break; }
        std::getline(status, line);
    }
    std::cout << "],\"peak_rss_bytes\":" << rss*1024 << "}\n";
    (void)sink;
}
