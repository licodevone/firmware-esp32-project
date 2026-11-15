#pragma once
#include <stdint.h>
#include "esp_err.h"
esp_err_t dht22_decode(const uint8_t bytes[5], float *temperature, float *humidity);
esp_err_t dht22_read(int pin, float *temperature, float *humidity);
