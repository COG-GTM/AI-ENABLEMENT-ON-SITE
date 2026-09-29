// Logger implementation. Portable C++ (no exceptions, no heap); the sink is injected so a host test can capture it.
#include "logger.hpp"

#include <cstring>

namespace hub {

static char scratch[16][64];
static std::size_t scratch_idx = 0;

Logger::Logger(sink_fn sink) : sink_(sink), lines_(), dropped_(0) {}

void Logger::enqueue(const char *line)
{
    if (!lines_.push(line)) {
        ++dropped_;
    }
}

void Logger::log(const char *msg)
{
    enqueue(msg);
}

void Logger::log(const char *key, int32_t value)
{
    char *s = scratch[scratch_idx++ % 16];
    std::size_t n = std::strlen(key);
    if (n > 40) {
        n = 40;
    }
    std::memcpy(s, key, n);
    s[n++] = '=';
    int32_t v = value < 0 ? -value : value;
    char digits[12];
    int d = 0;
    do {
        digits[d++] = static_cast<char>('0' + v % 10);
        v /= 10;
    } while (v && d < 11);
    if (value < 0) {
        s[n++] = '-';
    }
    while (d) {
        s[n++] = digits[--d];
    }
    s[n] = '\0';
    enqueue(s);
}

void Logger::log(const char *key, const char *value)
{
    char *s = scratch[scratch_idx++ % 16];
    std::size_t k = std::strlen(key), v = std::strlen(value);
    if (k > 30) {
        k = 30;
    }
    if (v > 30) {
        v = 30;
    }
    std::memcpy(s, key, k);
    s[k] = '=';
    std::memcpy(s + k + 1, value, v);
    s[k + 1 + v] = '\0';
    enqueue(s);
}

void Logger::flush()
{
    const char *line;
    while (lines_.pop(line)) {
        if (sink_) {
            sink_(line, std::strlen(line));
        }
    }
}

}  // namespace hub
