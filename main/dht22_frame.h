#pragma once
#include <stdint.h>

/* Portable decoder: 0=valid, 1=checksum, 2=physical range. */
static inline int dht22_frame(const uint8_t b[5], float *temperature, float *humidity)
{
    if ((uint8_t)(b[0] + b[1] + b[2] + b[3]) != b[4]) { return 1; }
    float h = ((unsigned)b[0] * 256 + b[1]) / 10.0f;
    float t = ((unsigned)(b[2] & 0x7f) * 256 + b[3]) / 10.0f;
    if (b[2] & 0x80) { t = -t; }
    if (h > 100 || t < -40 || t > 80) { return 2; }
    *temperature = t;
    *humidity = h;
    return 0;
}
