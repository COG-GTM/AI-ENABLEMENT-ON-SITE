// Bounded text logger with overloaded log() and a UART sink behind a function pointer.
#ifndef HUB_LOGGER_HPP
#define HUB_LOGGER_HPP

#include <cstddef>
#include <cstdint>

#include "ring_buffer.hpp"

namespace hub {

typedef void (*sink_fn)(const char *line, std::size_t n);

class Logger {
public:
    explicit Logger(sink_fn sink);
    void log(const char *msg);
    void log(const char *key, int32_t value);
    void log(const char *key, const char *value);
    std::size_t dropped() const { return dropped_; }
    void flush();

private:
    void enqueue(const char *line);
    sink_fn sink_;
    RingBuffer<const char *, 16> lines_;
    std::size_t dropped_;
};

}  // namespace hub

#endif
