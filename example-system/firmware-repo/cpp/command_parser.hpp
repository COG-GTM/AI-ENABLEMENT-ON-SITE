// Command line parser: a table of name -> handler. Handlers are looked up by string, so calls are data-driven.
#ifndef HUB_COMMAND_PARSER_HPP
#define HUB_COMMAND_PARSER_HPP

#include <cstddef>
#include <cstdint>

namespace hub {

typedef int (*command_fn)(const char *args);

struct Command {
    const char *name;
    command_fn fn;
};

class CommandParser {
public:
    CommandParser(const Command *table, std::size_t n);
    int dispatch(const char *line);   // returns the handler's result, -1 unknown, -2 empty
    std::size_t unknown() const { return unknown_; }

private:
    const Command *table_;
    std::size_t n_;
    std::size_t unknown_;
};

}  // namespace hub

#endif
