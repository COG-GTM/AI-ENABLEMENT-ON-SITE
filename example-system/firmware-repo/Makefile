# Target build for the synthetic sensor-hub firmware (never run in this repository; the host harness builds the
# portable parts). Cross toolchain and board are chosen here, which is the first thing tools/c_fleet_scan.py reports.
CC      = arm-none-eabi-gcc
CXX     = arm-none-eabi-g++
CFLAGS  = -mcpu=cortex-m4 -mthumb -Os -DBOARD_REV_C -DUSE_HAL_DRIVER -Iinclude -Iapp -Ialgo -Idrivers -Icpp
LDFLAGS = -T bsp/sensor_hub.ld -nostartfiles
SRC     = $(wildcard app/*.c algo/*.c drivers/*.c bsp/*.c third_party/*.c) cpp/logger.cpp cpp/command_parser.cpp

all: sensor_hub.elf

sensor_hub.elf: $(SRC)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $^

.PHONY: all
