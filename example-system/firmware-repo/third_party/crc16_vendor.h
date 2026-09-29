/* CRC-16/CCITT-FALSE as shipped in the vendor SDK example. Kept verbatim; treat as a dependency, not as our code. */
#ifndef CRC16_VENDOR_H
#define CRC16_VENDOR_H
#include <stddef.h>
#include <stdint.h>
uint16_t crc16_vendor(const uint8_t *data, size_t len);
#endif
