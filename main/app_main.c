#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "driver/gpio.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "mqtt_client.h"
#include "nvs_flash.h"
#if __has_include("private_config.h")
#include "private_config.h"
#else
#include "config.example.h"
#endif
#include "dht22.h"
#include "relay_control.h"

static const char *TAG = "xmqr-dht22";
static EventGroupHandle_t connected;
static esp_mqtt_client_handle_t mqtt;
#define WIFI_READY BIT0
#define MQTT_READY BIT1
#define SENSOR_PIN GPIO_NUM_4

static void wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)data;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        const wifi_event_sta_disconnected_t *event = data;
        ESP_LOGW(TAG, "Wi-Fi desconectado; motivo=%u. Tentando reconectar", (unsigned)event->reason);
        xEventGroupClearBits(connected, WIFI_READY | MQTT_READY);
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ESP_LOGW(TAG, "Wi-Fi conectado, IP obtido; iniciando sincronizacao de horario");
        xEventGroupSetBits(connected, WIFI_READY);
    }
}

static void mqtt_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)base;
    esp_mqtt_event_handle_t event = data;
    if (id == MQTT_EVENT_CONNECTED) {
        xEventGroupSetBits(connected, MQTT_READY);
        ESP_LOGW(TAG, "MQTT5 conectado com mTLS");
    } else if (id == MQTT_EVENT_DISCONNECTED) {
        xEventGroupClearBits(connected, MQTT_READY);
        ESP_LOGW(TAG, "MQTT desconectado");
    } else if (id == MQTT_EVENT_PUBLISHED) {
        ESP_LOGW(TAG, "PUBACK id=%d (broker confirmou, plataforma ainda depende da ponte)", event->msg_id);
    } else if (id == MQTT_EVENT_ERROR) {
        ESP_LOGW(TAG, "Falha MQTT/TLS: confira CA, horario, credenciais e ACL");
    }
}

static void sensor_task(void *arg)
{
    (void)arg;
    vTaskDelay(pdMS_TO_TICKS(2500));
    for (;;) {
        float temperature, humidity;
        esp_err_t error = dht22_read(SENSOR_PIN, &temperature, &humidity);
        if (error != ESP_OK) {
            ESP_LOGW(TAG, "Leitura DHT22 descartada: %s; confira 3V3/GND/GPIO4/pull-up", esp_err_to_name(error));
        } else if (xEventGroupGetBits(connected) & MQTT_READY) {
            wifi_ap_record_t ap;
            int rssi = esp_wifi_sta_get_ap_info(&ap) == ESP_OK ? ap.rssi : -127;
            char payload[256];
            int n = snprintf(payload, sizeof(payload),
                "{\"deviceId\":\"%s\",\"temperature\":%.1f,\"humidity\":%.1f,\"rssi\":%d,\"uptime_ms\":%" PRId64 "}",
                XMQR_DEVICE_ID, temperature, humidity, rssi, esp_timer_get_time() / 1000);
            if (n > 0 && n < (int)sizeof(payload)) {
                int msg = esp_mqtt_client_enqueue(mqtt, XMQR_MQTT_TOPIC, payload, n, 1, 0, true);
                ESP_LOGW(TAG, "DHT22 %.1f C / %.1f %% ; enfileiramento=%d", temperature, humidity, msg);
            }
        } else {
            ESP_LOGW(TAG, "Leitura valida; MQTT offline, amostra nao enviada");
        }
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}

void app_main(void)
{
    relay_control_start();
    if (!XMQR_CONFIGURED) {
        ESP_LOGE(TAG, "Build de verificacao: execute configurar.py e recompile antes de gravar");
        return;
    }
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    connected = xEventGroupCreate();
    assert(connected);
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t wifi_init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi_init));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, NULL));
    wifi_config_t wifi = {0};
    memcpy(wifi.sta.ssid, XMQR_WIFI_SSID, strlen(XMQR_WIFI_SSID));
    memcpy(wifi.sta.password, XMQR_WIFI_PASSWORD, strlen(XMQR_WIFI_PASSWORD));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi));
    ESP_ERROR_CHECK(esp_wifi_start());
    xEventGroupWaitBits(connected, WIFI_READY, pdFALSE, pdTRUE, portMAX_DELAY);
    esp_sntp_config_t sntp = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
    ESP_ERROR_CHECK(esp_netif_sntp_init(&sntp));
    while (time(NULL) < 1767225600) {
        ESP_LOGW(TAG, "Aguardando horario SNTP antes de validar TLS");
        esp_netif_sntp_sync_wait(pdMS_TO_TICKS(10000));
    }
    esp_mqtt_client_config_t config = {
        .broker.address.uri = XMQR_MQTT_URI,
        .broker.verification.certificate = XMQR_CA,
        .credentials.username = XMQR_MQTT_USERNAME,
        .credentials.client_id = XMQR_DEVICE_ID,
        .credentials.authentication.password = XMQR_MQTT_PASSWORD,
        .credentials.authentication.certificate = XMQR_CLIENT_CERT,
        .credentials.authentication.key = XMQR_CLIENT_KEY,
        .session.protocol_ver = MQTT_PROTOCOL_V_5,
        .session.keepalive = 30,
        .outbox.limit = 8192,
    };
    mqtt = esp_mqtt_client_init(&config);
    assert(mqtt);
    ESP_ERROR_CHECK(esp_mqtt_client_register_event(mqtt, ESP_EVENT_ANY_ID, mqtt_event, NULL));
    ESP_ERROR_CHECK(esp_mqtt_client_start(mqtt));
    gpio_config_t pin = {
        .pin_bit_mask = 1ULL << SENSOR_PIN, .mode = GPIO_MODE_INPUT_OUTPUT_OD,
        .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&pin));
    ESP_ERROR_CHECK(gpio_set_level(SENSOR_PIN, 1));
    BaseType_t started = xTaskCreatePinnedToCore(sensor_task, "dht22", 4096, NULL, 4, NULL, 1);
    assert(started == pdPASS);
}
