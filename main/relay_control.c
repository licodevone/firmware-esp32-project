#include <stdbool.h>
#include <stdlib.h>
#include "relay_control.h"
#include "driver/gpio.h"
#include "esp_check.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "relay_config.h"

static const char *TAG = "xmqr-relay";

static void relay_task(void *arg)
{
    (void)arg;
    int candidate = gpio_get_level(XMQR_INPUT_GPIO);
    int applied = 1 - XMQR_INPUT_ACTIVE_LEVEL;
    int64_t changed_at = esp_timer_get_time();
    for (;;) {
        int level = gpio_get_level(XMQR_INPUT_GPIO);
        int64_t now = esp_timer_get_time();
        if (level != candidate) {
            candidate = level;
            changed_at = now;
        }
        if (candidate != applied &&
            now - changed_at >= XMQR_RELAY_DEBOUNCE_MS * 1000LL) {
            bool on = candidate == XMQR_INPUT_ACTIVE_LEVEL;
            ESP_ERROR_CHECK(gpio_set_level(XMQR_RELAY_GPIO,
                on ? XMQR_RELAY_ACTIVE_LEVEL : 1 - XMQR_RELAY_ACTIVE_LEVEL));
            applied = candidate;
            ESP_LOGI(TAG, "Contato %s; rele %s", on ? "fechado" : "aberto",
                on ? "ligado" : "desligado");
        }
        vTaskDelay(pdMS_TO_TICKS(10) > 0 ? pdMS_TO_TICKS(10) : 1);
    }
}

void relay_control_start(void)
{
    /* Preload the inactive output latch before enabling the output driver. */
    ESP_ERROR_CHECK(gpio_set_level(XMQR_RELAY_GPIO, 1 - XMQR_RELAY_ACTIVE_LEVEL));
    gpio_config_t output = {
        .pin_bit_mask = 1ULL << XMQR_RELAY_GPIO,
        .mode = GPIO_MODE_OUTPUT,
    };
    ESP_ERROR_CHECK(gpio_config(&output));
    gpio_config_t input = {
        .pin_bit_mask = 1ULL << XMQR_INPUT_GPIO,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&input));
    if (xTaskCreate(relay_task, "relay-control", 2048, NULL, 5, NULL) != pdPASS) {
        ESP_LOGE(TAG, "Falha ao iniciar controle do rele; saida permanece desligada");
        abort();
    }
    ESP_LOGI(TAG, "Controle local iniciado: entrada GPIO%d, rele GPIO%d",
        XMQR_INPUT_GPIO, XMQR_RELAY_GPIO);
}
