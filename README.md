# ESP32-WROOM-32 + DHT22 -> Railway -> XMQR Platform

Ensaio PL187, 15/11/2026. Código implementado; configuração privada, build operacional, flash e medição física dependem das próximas etapas. Não tratar teste unitário como leitura de hardware.

Atualização de aceite em15/11/2026: operador configurou Wi-Fi/token e gravou a placa. Conexão Wi-Fi/MQTT5 e leitura física/PUBACK observados. Ponte com User-Agent próprio enviou uma amostra real autorizada e telemetria/histórico foram lidos de volta na plataforma. Etapas abaixo permanecem como procedimento de reprodução; operação contínua requer o processo da ponte aberto.

## Ligação e destino

Com USB desligado: módulo DHT22 +/VCC -> 3V3, S/DATA -> GPIO4, −/GND -> GND. Siga serigrafia, não posição física; módulo precisa de pull-up para 3V3 (normalmente integrado). O ESP32 usa Wi-Fi 2,4 GHz, não 5 GHz. Placa CP210x COM3 confirmada pelo operador.

Firmware usa MQTT5/mTLS + senha, mqtt.acmebr.net:52530, tópico de ensaio permitido xmqr/test/smoke, QoS1 sem retained, intervalo5s. SNTP sincroniza relógio antes de TLS. Leitura inválida/timeout/checksum não vira amostra zero. Fila MQTT limitada a8KiB; sem garantia de retenção offline. PUBACK confirma broker, não a plataforma.

Dispositivo na plataforma: esp32-dht22-01 (d096d400-e0a4-11f1-830d-61590aed812b), atribuído a Customer A e visível pelo usuário Terra. Token deve ser copiado dessa identidade específica, não de dispositivo demo. O token é a autorização de destino; a ponte não consegue provar o id remoto apenas pela API de transporte HTTP.

## 1. Configuração privada no seu terminal

Na pasta deste README:

```powershell
.\Rodar.ps1 -Etapa Configurar
```

O programa solicita SSID, senha Wi-Fi e token do dispositivo (segredos com entrada oculta). Reutiliza o perfil MQTT referenciado por ../.run/railway-mqtt-current.json, preservando o original. Não usa senha de login da plataforma. Não cole segredos no chat.

Neste firmware o Wi-Fi não é lido do sdkconfig. Os nomes do cabeçalho privado são XMQR_WIFI_SSID e XMQR_WIFI_PASSWORD. O configurador os gera como literais C escapados; esse formato é normal e não deve ser substituído por CONFIG_ESP_WIFI_SSID/CONFIG_ESP_WIFI_PASSWORD no sdkconfig. Depois de configurar, recompile para incorporar os valores. Senha MQTT e token da plataforma são outros valores, não a senha Wi-Fi.

Gera .private/private_config.h e .private/bridge.json com permissões restritas e ignorados pelo Git. Header contém Wi-Fi e identidade TLS; firmware compilado também conterá esses dados. Não compartilhe build, binários, sdkconfig ou arquivos privados. A identidade MQTT railway-smoke é provisória, compartilhada só neste ensaio; provisionamento definitivo requer identidade própria e ACL dedicada.

## 2. Compilar

```powershell
.\Rodar.ps1 -Etapa Compilar
```

Wrapper usa por padrão ESP-IDF5.5.5 do EIM em C:/esp/v5.5.5/esp-idf e seu Python em C:/Espressif/tools/python/v5.5.5/venv. Chama o idf.py do SDK explicitamente, evitando outro idf.py no PATH. Aceita -IdfPath alternativo e isola build e sdkconfig por versão (build-5.5.5, por exemplo). Não reutiliza o build antigo5.5.3. Sem configuração privada, compila somente imagem bloqueada para conexão e recusa a etapa Gravar. Suporte6.1 ainda exige dependência gerenciada espressif/mqtt e validação própria.

## 3. Iniciar ponte no computador

Em outro PowerShell nesta pasta:

```powershell
.\Rodar.ps1 -Etapa Ponte
```

Ponte usa mqtt-client instalado em C:/Program Files/XMQR/Client/mqtt-client.exe, mTLS e senha por perfil, client-id exclusivo, MQTT5 e JSONL. Rejeita tópico/identidade divergentes, retained, payload excessivo e leituras fora de faixa. Envia temperature, humidity, rssi e uptime_ms via HTTPS /api/v1/TOKEN/telemetry; timestamp é o horário de ingestão da plataforma, não uptime. Redirecionamento é recusado para proteger token. URLs com token e stderr privado do cliente não são impressos.

O computador deve permanecer ligado durante este ensaio. Não há spool durável ou serviço de ponte instalado. HTTP2xx confirma aceite do transporte; confirme armazenamento/visualização na plataforma. Falha HTTP encerra a ponte explicitamente. Depois de corrigir a causa, reinicie-a; amostras perdidas não são repostas. Ingestão real ainda não validada nesta preparação.

No aceite PL187v7, ingestão real e leitura de volta foram confirmadas. Cabeçalho User-Agent XMQR-DHT22-Bridge/1.0 identifica a aplicação; Cloudflare pode recusar o UA Python urllib padrão com403/error1010. O ajuste não muda destino nem desativa proteções. Ver https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/ .

Cliente XMQR instalado não aceita --reconnect-attempts diferente de0 no MQTT5. A ponte não passa essa opção; falha do assinante encerra com código e categoria segura, sem imprimir stderr privado. Para Wi-Fi, o firmware registra motivo numérico de desconexão e confirmação de IP obtido. O aviso Password length matches WPA2 standards é normal; sozinho não diagnostica falha de autenticação.

## 4. Gravar e acompanhar

Somente após Configurar e Compilar:

```powershell
.\Rodar.ps1 -Etapa Gravar -Porta COM3
```

Esta etapa recompila, substitui o programa da placa e abre monitor serial. Feche outros monitores usando COM3 antes. Não executa erase-flash total. A disposição de partições do novo firmware pode tornar dados antigos da aplicação indisponíveis; preserve o firmware anterior se necessário.

Esperado: sincronização de horário, MQTT5 conectado, leituras reais DHT22 e PUBACK. Monitor sai com Ctrl+]. Ponte sai com Ctrl+C. Sem SNTP/Wi-Fi não haverá tentativa TLS; sem sensor válido não haverá temperatura falsa.

## 5. Conferir como cliente

Na plataforma como lepinheiro100@terra.com.br: Dispositivos -> esp32-dht22-01 -> Ao vivo ou Atualizar telemetria. Devem surgir temperature, humidity, rssi e uptime_ms. Atributo active depende da política de atividade da plataforma; não basta PUBACK para assumir status ativo. Observe horário da telemetria e valores reais.

## Verificações locais

```powershell
python -m unittest -v test_ponte.py test_dht22_host.py
```

Teste C usa imagem Docker local xmqr-complete-gateway-windows:pl185, com --pull=never, sem rede, fonte somente leitura e diretório temporário executável apenas no contêiner. Não baixa ferramentas. Sem imagem/daemon, essa verificação precisa do pré-requisito; não prova estado elétrico de GPIO/sensor. Testes da ponte simulam HTTP, não escrevem telemetria real.
