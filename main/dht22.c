#include "dht22.h"
#include "dht22_frame.h"
#include "driver/gpio.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"

static portMUX_TYPE sensor_mux = portMUX_INITIALIZER_UNLOCKED;

esp_err_t dht22_decode(const uint8_t b[5], float *temperature, float *humidity)
{
    int result = dht22_frame(b, temperature, humidity);
    return result == 0 ? ESP_OK : result == 1 ? ESP_ERR_INVALID_CRC : ESP_ERR_INVALID_RESPONSE;
}

static bool wait_level(int pin, int level, int timeout, int64_t *elapsed)
{
    int64_t start = esp_timer_get_time();
    while (gpio_get_level(pin) != level) {
        if (esp_timer_get_time() - start > timeout) { return false; }
    }
    if (elapsed) { *elapsed = esp_timer_get_time() - start; }
    return true;
}

esp_err_t dht22_read(int pin, float *temperature, float *humidity)
{
    uint8_t bytes[5] = {0};
    if (!gpio_get_level(pin)) { return ESP_ERR_INVALID_STATE; }
    /* Open drain: never drive high against the sensor. */
    gpio_set_level(pin, 0);
    esp_rom_delay_us(1200);
    bool ok;
    portENTER_CRITICAL(&sensor_mux);
    gpio_set_level(pin, 1);
    ok = wait_level(pin, 0, 120, NULL)
        && wait_level(pin, 1, 120, NULL)
        && wait_level(pin, 0, 120, NULL);
    for (int bit = 0; ok && bit < 40; bit++) {
        int64_t high = 0;
        ok = wait_level(pin, 1, 120, NULL) && wait_level(pin, 0, 120, &high);
        bytes[bit / 8] = (uint8_t)((bytes[bit / 8] << 1) | (high > 45));
    }
    portEXIT_CRITICAL(&sensor_mux);
    if (!ok) { return ESP_ERR_TIMEOUT; }
    return dht22_decode(bytes, temperature, humidity);
}
