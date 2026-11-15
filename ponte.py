"""Ponte limitada a um dispositivo de ensaio; nenhum segredo em logs/argumentos."""
import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import threading
import urllib.error
import urllib.request

TOPIC = 'xmqr/test/smoke'
DEVICE = 'esp32-dht22-01'
PLATFORM_DEVICE = 'd096d400-e0a4-11f1-830d-61590aed812b'
ORIGIN = 'https://xmqr.acmebr.net'
USER_AGENT = 'XMQR-DHT22-Bridge/1.0'


class SubscriberError(RuntimeError):
    pass


def subscriber_command(client, profile):
    # Installed MQTT5 client rejects nonzero reconnect-attempts.
    return [client, 'sub', '--profile', profile, '--protocol-version', '5',
            '--host', 'mqtt.acmebr.net', '--port', '52530', '--topic', TOPIC,
            '--client-id', 'xmqr-platform-dht22-bridge', '--qos', '1', '--output', 'jsonl']


def diagnostic(stderr):
    # Never return raw stderr: it can contain credential paths or supplied values.
    text = stderr.lower()
    if b'mqtt 5 exige ausencia de modo linha e reconexao' in text:
        return 'Cliente MQTT5 recebeu uma opcao de reconexao incompativel.'
    if b'permission' in text or b'permiss' in text:
        return 'Confira as permissoes dos arquivos privados do perfil MQTT.'
    if b'password' in text or b'senha' in text:
        return 'Confira a leitura do arquivo de senha do perfil MQTT.'
    if b'tls' in text or b'certificate' in text or b'certificado' in text:
        return 'Confira CA, certificado, chave, horario e identidade TLS.'
    if b'dns' in text or b'host' in text or b'resolve' in text:
        return 'Confira DNS e conectividade ao endpoint MQTT.'
    return 'Confira conectividade, perfil mTLS e compatibilidade do cliente instalado.'


def numeric(value, minimum, maximum):
    return (type(value) in (int, float) and minimum <= value <= maximum
            and math.isfinite(value))


def telemetry(line):
    if len(line) > 8192:
        raise ValueError('envelope excessivo')
    envelope = json.loads(line)
    if not isinstance(envelope, dict):
        raise ValueError('envelope invalido')
    if envelope.get('event') != 'publish':
        return None
    if envelope.get('topic') != TOPIC or envelope.get('retain') is not False:
        raise ValueError('topico ou retained recusado')
    raw = envelope.get('payload_bytes')
    if (not isinstance(raw, list) or not 1 <= len(raw) <= 1024
            or any(type(b) is not int or not 0 <= b <= 255 for b in raw)):
        raise ValueError('payload invalido')
    sample = json.loads(bytes(raw).decode('utf-8'))
    if not isinstance(sample, dict) or sample.get('deviceId') != DEVICE:
        raise ValueError('identidade divergente')
    if not numeric(sample.get('temperature'), -40, 80) or not numeric(sample.get('humidity'), 0, 100):
        raise ValueError('leitura invalida')
    if not numeric(sample.get('rssi'), -127, 0):
        raise ValueError('RSSI invalido')
    uptime = sample.get('uptime_ms')
    if type(uptime) is not int or not 0 <= uptime <= 2**53 - 1:
        raise ValueError('uptime invalido')
    # Plain values use ingestion time assigned by the platform, never uptime as epoch.
    return {key: sample[key] for key in ('temperature', 'humidity', 'rssi', 'uptime_ms')}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward device credentials to another origin.
        return None


def send(opener, token, values):
    request = urllib.request.Request(
        ORIGIN + '/api/v1/' + token + '/telemetry',
        data=json.dumps(values, allow_nan=False).encode(),
        headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                 'User-Agent': USER_AGENT}, method='POST')
    with opener.open(request, timeout=15) as response:
        if not 200 <= response.status < 300:
            raise ValueError('ingestao nao confirmada')


def run(args):
    config = json.loads(Path(args.config).read_text())
    if config.get('deviceId') != DEVICE or config.get('platformDeviceId') != PLATFORM_DEVICE:
        raise ValueError('configuracao de dispositivo divergente')
    token = config.get('token', '')
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', token):
        raise ValueError('token invalido')
    opener = urllib.request.build_opener(NoRedirect())
    command = subscriber_command(args.client, config['profile'])
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    private_error = bytearray()

    def drain_errors():
        while chunk := process.stderr.read(1024):
            private_error.extend(chunk)
            del private_error[:-8192]

    stderr_thread = threading.Thread(target=drain_errors, daemon=True)
    stderr_thread.start()
    count = 0
    print('Ponte iniciada; aguardando leituras reais do ESP32.', flush=True)
    try:
        while True:
            line = process.stdout.readline(8193)
            if not line:
                code = process.wait(timeout=5)
                stderr_thread.join(timeout=2)
                raise SubscriberError(f'Assinante MQTT encerrou (codigo {code}). {diagnostic(bytes(private_error))}')
            if len(line) > 8192:
                raise ValueError('saida excessiva do assinante')
            try:
                values = telemetry(line)
            except (ValueError, TypeError, UnicodeError):
                print('Mensagem descartada: envelope, identidade ou leitura invalida.', flush=True)
                continue
            if values is None:
                continue
            send(opener, token, values)
            count += 1
            print(f'Ingestao HTTP confirmada: amostra {count}. Confira a telemetria na plataforma.', flush=True)
            if args.count and count >= args.count:
                return
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        stderr_thread.join(timeout=2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(Path(__file__).parent / '.private/bridge.json'))
    parser.add_argument('--client', default=r'C:\Program Files\XMQR\Client\mqtt-client.exe')
    parser.add_argument('--count', type=int, default=0, help='0: continuo; N: encerra apos N envios')
    args = parser.parse_args()
    if args.count < 0:
        parser.error('count deve ser positivo ou zero')
    try:
        run(args)
    except KeyboardInterrupt:
        print('Ponte encerrada pelo operador.')
    except SubscriberError as error:
        print(str(error))
        raise SystemExit(1)
    except urllib.error.HTTPError as error:
        if error.code == 401:
            print('Ingestao falhou: HTTP401. Confira o token do dispositivo; URL privada omitida.')
        elif error.code == 403:
            print('Ingestao falhou: HTTP403. Pode ser bloqueio HTTP ou permissao; nao conclua token invalido. URL privada omitida.')
        else:
            print(f'Ingestao falhou: HTTP {error.code}. URL privada omitida.')
        raise SystemExit(1)
    except Exception:
        print('Ponte interrompida. Confira rede, perfil mTLS e configuracao privada. Sem fila persistente.')
        raise SystemExit(1)
