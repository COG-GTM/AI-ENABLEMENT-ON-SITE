# Timing budget: 10 ms control loop

Synthetic numbers for a 32 MHz Cortex-M0-class MCU (`../parts/mcu-m0.json`). Period 10 ms (SN-REQ-001);
budget 8 ms worst case (SN-REQ-021).

| Step | Worst case | Notes |
| --- | --- | --- |
| Wake from sleep, clock stabilise | 0.10 ms | |
| IMU read, 8 bytes over SPI at 1 MHz | 0.08 ms | 4 x 16-bit registers |
| Filter update, 4 axes | 0.01 ms | 4 adds + 1 divide each |
| Temperature read (1 of every 100 loops) | 0.35 ms | I2C 100 kHz, 3 bytes + addressing |
| Packet build + CRC (1 of every 100 loops) | 0.05 ms | 14 bytes x 8 bit-iterations |
| UART transmit start (DMA or ring buffer) | 0.02 ms | Bytes drain in background (1.4 ms) |
| Housekeeping, fault checks | 0.05 ms | |
| **Worst-case loop (temp + packet in same tick)** | **0.66 ms** | 8 % of period |

Verdict: large margin. The MCU spends most of each period idle, which is why the missing sleep call
(SN-BUG-003) dominates the power budget rather than the timing budget.

## What changes this table

- Swapping the IMU for a part with more registers or slower SPI (see `/what-if-part-swap`).
- Increasing the filter window or moving to a biquad (ADR-0001).
- Adding CAN: transceiver enable and two-frame fragmentation add roughly 0.3 ms per second.
