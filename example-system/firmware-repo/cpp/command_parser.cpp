// Command parser. Portable; the handler table is supplied by the caller.
#include "command_parser.hpp"

#include <cstring>

namespace hub {

CommandParser::CommandParser(const Command *table, std::size_t n) : table_(table), n_(n), unknown_(0) {}

int CommandParser::dispatch(const char *line)
{
    while (*line == ' ') {
        ++line;
    }
    if (!*line) {
        return -2;
    }
    const char *sp = std::strchr(line, ' ');
    std::size_t len = sp ? static_cast<std::size_t>(sp - line) : std::strlen(line);
    for (std::size_t i = 0; i < n_; ++i) {
        if (std::strlen(table_[i].name) == len && std::strncmp(table_[i].name, line, len) == 0) {
            return table_[i].fn(sp ? sp + 1 : "");   // data-driven dispatch
        }
    }
    ++unknown_;
    return -1;
}

}  // namespace hub
