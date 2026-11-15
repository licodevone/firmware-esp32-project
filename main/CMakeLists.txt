set(config_include ".")
if(EXISTS "${CMAKE_CURRENT_LIST_DIR}/../.private/private_config.h")
    set(config_include "${CMAKE_CURRENT_LIST_DIR}/../.private")
endif()
idf_component_register(SRCS "app_main.c" "dht22.c"
    INCLUDE_DIRS "." "${config_include}"
    REQUIRES mqtt nvs_flash esp_wifi esp_netif esp_event esp_driver_gpio esp_timer lwip)
