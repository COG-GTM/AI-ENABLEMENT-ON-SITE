# Host-side test build for a firmware tree. No board, no cross-compiler, no framework install.
#
#   make test                                   # runs against example-system/src (the proof)
#   make test FW_SRC="path/to/a.c path/to/b.c" FW_INC=path/to/include   # your tree
#
# Cross-compilation and on-target tests stay in YOUR build; this only builds what is host-portable.
# Each .c compiles to build/<name>.o with a build/<name>.d dependency file (-MMD), so editing a header
# anywhere under FW_INC rebuilds what includes it. Sources must have distinct basenames.
CC      ?= cc
CFLAGS  ?= -std=c11 -Wall -Wextra -Werror -O1
FW_INC  ?= ../../example-system/src
FW_SRC  ?= ../../example-system/src/filter.c ../../example-system/src/packet.c ../../example-system/src/node.c
BUILD   := build
HARNESS := test_main.c hal_stub.c
SRCS    := $(HARNESS) $(FW_SRC)
OBJS    := $(addprefix $(BUILD)/,$(notdir $(SRCS:.c=.o)))

ifneq ($(words $(sort $(notdir $(SRCS)))),$(words $(SRCS)))
$(error FW_SRC has duplicate basenames; objects would collide in $(BUILD)/)
endif

.PHONY: all test clean

all: $(BUILD)/host_tests

$(BUILD)/host_tests: $(OBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS)

# One compile rule per source so files from different directories all land in $(BUILD)/.
define compile_rule
$(BUILD)/$(notdir $(1:.c=.o)): $(1) | $(BUILD)
	$$(CC) $$(CFLAGS) -MMD -MP -I. $$(addprefix -I,$$(FW_INC)) -c -o $$@ $$<
endef
$(foreach src,$(SRCS),$(eval $(call compile_rule,$(src))))

$(BUILD):
	@mkdir -p $(BUILD)

-include $(OBJS:.o=.d)

test: $(BUILD)/host_tests
	./$(BUILD)/host_tests

clean:
	rm -rf $(BUILD)
