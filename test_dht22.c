#include <assert.h>
#include <stdio.h>
#include "dht22_frame.h"

int main(void)
{
    const uint8_t positive[5] = {2, 88, 0, 250, 84};
    const uint8_t negative[5] = {2, 88, 128, 55, 17};
    const uint8_t bad_crc[5] = {2, 88, 0, 250, 85};
    const uint8_t bad_humidity[5] = {3, 233, 0, 250, 230};
    const uint8_t bad_temperature[5] = {2, 88, 3, 33, 126};
    float t = 123, h = 456;
    assert(dht22_frame(positive, &t, &h) == 0 && t == 25 && h == 60);
    assert(dht22_frame(negative, &t, &h) == 0 && t == -5.5f && h == 60);
    t = 123; h = 456;
    assert(dht22_frame(bad_crc, &t, &h) == 1 && t == 123 && h == 456);
    assert(dht22_frame(bad_humidity, &t, &h) == 2 && t == 123 && h == 456);
    assert(dht22_frame(bad_temperature, &t, &h) == 2 && t == 123 && h == 456);
    puts("DHT22_FRAME_PASS");
    return 0;
}
