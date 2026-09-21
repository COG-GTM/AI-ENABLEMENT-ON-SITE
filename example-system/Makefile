# Host build of the sensor-node firmware modules and their C tests (SN-REQ-022).
# No hardware or cross-compiler needed. `make test` also runs the Python twin tests.
CC      ?= cc
CFLAGS  ?= -std=c11 -Wall -Wextra -Werror -O1
BUILD   := build
SRC     := src/filter.c src/packet.c src/node.c

.PHONY: all test test-c test-py clean

all: $(BUILD)/test_firmware

$(BUILD)/test_firmware: tests/test_firmware.c $(SRC) src/*.h
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) -o $@ tests/test_firmware.c $(SRC)

test-c: $(BUILD)/test_firmware
	./$(BUILD)/test_firmware

test-py:
	python3 -m unittest discover -s tests -q

test: test-py test-c

clean:
	rm -rf $(BUILD)
