# Host-side test build for a firmware tree. No board, no cross-compiler, no framework install.
#
#   make test                                   # runs against example-system/src (the proof)
#   make test FW_SRC="path/to/a.c path/to/b.c" FW_INC=path/to/include   # your tree
#
# Cross-compilation and on-target tests stay in YOUR build; this only builds what is host-portable.
CC      ?= cc
CFLAGS  ?= -std=c11 -Wall -Wextra -Werror -O1
FW_INC  ?= ../../example-system/src
FW_SRC  ?= ../../example-system/src/filter.c ../../example-system/src/packet.c ../../example-system/src/node.c
BUILD   := build
HARNESS := test_main.c hal_stub.c

.PHONY: all test clean

all: $(BUILD)/host_tests

$(BUILD)/host_tests: $(HARNESS) $(FW_SRC) hal_stub.h harness.h
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) -I. $(addprefix -I,$(FW_INC)) -o $@ $(HARNESS) $(FW_SRC)

test: $(BUILD)/host_tests
	./$(BUILD)/host_tests

clean:
	rm -rf $(BUILD)
