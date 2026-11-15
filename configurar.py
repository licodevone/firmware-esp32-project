"""Configure o ensaio em terminal privado; nunca passe senhas em argumentos."""
import csv
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parent


def c_string(value):
    return '"' + ''.join(f'\\x{b:02x}' for b in value.encode('utf-8')) + '"'


def private_directory(path):
    if path.is_symlink():
        raise ValueError('Diretorio privado nao pode ser um link')
    path.mkdir(mode=0o700, exist_ok=True)
    if os.name == 'nt':
        identity = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'],
                                  capture_output=True, text=True, check=True)
        sid = next(csv.reader(identity.stdout.splitlines()))[1]
        subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r',
                        f'*{sid}:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'],
                       capture_output=True, check=True)
    else:
        path.chmod(0o700)


def write_private(path, text):
    if path.is_symlink():
        raise ValueError('Arquivo privado nao pode ser um link')
    # Parent has already been restricted, before the first secret byte is written.
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(text)
    if os.name != 'nt':
        path.chmod(0o600)


def main():
    metadata = json.loads((ROOT.parent / '.run/railway-mqtt-current.json').read_text())
    profile = Path(metadata['profile']).resolve()
    connection = tomllib.loads(profile.read_text())['connection']
    # Keep the current broker profile untouched; inspect only the expected endpoint.
    if connection['host'] != 'mqtt.acmebr.net' or connection['port'] != 52530:
        raise ValueError('Perfil nao corresponde ao endpoint validado')
    ssid = input('Nome da rede Wi-Fi 2,4 GHz (SSID): ')
    wifi_password = getpass.getpass('Senha do Wi-Fi (entrada oculta): ')
    if not 1 <= len(ssid.encode()) <= 32 or not 8 <= len(wifi_password.encode()) <= 63:
        raise ValueError('SSID ou tamanho da senha Wi-Fi invalido; use rede WPA2/WPA3 pessoal')
    token = getpass.getpass('Token de acesso do dispositivo esp32-dht22-01 (oculto): ').strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', token):
        raise ValueError('Formato de token invalido')
    materials = {}
    for source, name, marker in [('ca', 'XMQR_CA', 'BEGIN CERTIFICATE'),
                                  ('cert', 'XMQR_CLIENT_CERT', 'BEGIN CERTIFICATE'),
                                  ('key', 'XMQR_CLIENT_KEY', 'PRIVATE KEY')]:
        path = Path(connection[source])
        if not path.is_absolute():
            path = profile.parent / path
        text = path.read_text()
        if marker not in text or len(text) > 32768:
            raise ValueError('Material TLS ausente ou invalido')
        materials[name] = text
    password_path = Path(connection['password_file'])
    if not password_path.is_absolute():
        password_path = profile.parent / password_path
    password = password_path.read_text().rstrip('\r\n')
    if not password:
        raise ValueError('Senha MQTT ausente')
    values = dict(XMQR_WIFI_SSID=ssid, XMQR_WIFI_PASSWORD=wifi_password,
                  XMQR_MQTT_USERNAME=connection['username'], XMQR_MQTT_PASSWORD=password,
                  XMQR_DEVICE_ID='esp32-dht22-01', XMQR_MQTT_URI='mqtts://mqtt.acmebr.net:52530',
                  XMQR_MQTT_TOPIC='xmqr/test/smoke', **materials)
    private = ROOT / '.private'
    private_directory(private)
    header = '#pragma once\n#define XMQR_CONFIGURED 1\n'
    header += ''.join(f'#define {name} {c_string(value)}\n' for name, value in values.items())
    write_private(private / 'private_config.h', header)
    write_private(private / 'bridge.json', json.dumps({
        'profile': str(profile), 'token': token,
        'deviceId': 'esp32-dht22-01',
        'platformDeviceId': 'd096d400-e0a4-11f1-830d-61590aed812b',
    }, indent=2))
    print('Configuracao privada salva. Recompile antes do flash; nao compartilhe build/binarios.')


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('Configuracao cancelada. Nenhum flash executado.')
        raise SystemExit(1)
    except Exception:
        print('Falha no preparo privado. Confira perfil, certificados e entradas; valores omitidos.')
        raise SystemExit(1)
