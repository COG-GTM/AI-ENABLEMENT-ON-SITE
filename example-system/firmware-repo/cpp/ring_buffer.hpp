// Fixed-capacity ring buffer. Header-only template: portable, but a template has no single translation unit to test.
#ifndef HUB_RING_BUFFER_HPP
#define HUB_RING_BUFFER_HPP

#include <cstddef>
#include <cstdint>

namespace hub {

template <typename T, std::size_t N>
class RingBuffer {
public:
    RingBuffer() : head_(0), count_(0) {}
    bool push(const T &v)
    {
        if (count_ == N) {
            return false;
        }
        buf_[(head_ + count_) % N] = v;
        ++count_;
        return true;
    }
    bool pop(T &out)
    {
        if (count_ == 0) {
            return false;
        }
        out = buf_[head_];
        head_ = (head_ + 1) % N;
        --count_;
        return true;
    }
    std::size_t size() const { return count_; }

private:
    T buf_[N];
    std::size_t head_;
    std::size_t count_;
};

}  // namespace hub

#endif
