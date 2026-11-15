import json
import unittest
from unittest.mock import MagicMock

import ponte


def envelope(**changes):
    sample = dict(deviceId=ponte.DEVICE, temperature=24.5, humidity=60.2, rssi=-55, uptime_ms=1234)
    sample.update(changes)
    return json.dumps(dict(event='publish', topic=ponte.TOPIC, retain=False,
                           payload_bytes=list(json.dumps(sample).encode())))


class TelemetryTests(unittest.TestCase):
    def test_mqtt5_subscriber_never_requests_unsupported_reconnect(self):
        command = ponte.subscriber_command('mqtt-client', 'private-profile')
        self.assertNotIn('--reconnect-attempts', command)
        self.assertEqual(command[command.index('--protocol-version') + 1], '5')
        self.assertIn('--profile', command)

    def test_stderr_diagnostic_never_echoes_private_details(self):
        raw = b'Erro: MQTT 5 exige ausencia de modo linha e reconexao; secret-token C:\\private\\password'
        message = ponte.diagnostic(raw)
        self.assertIn('reconexao', message)
        self.assertNotIn('secret-token', message)
        self.assertNotIn('private', message)
        self.assertNotIn('sensitive-data', ponte.diagnostic(b'unknown sensitive-data'))

    def test_real_values_mapped_without_using_uptime_as_epoch(self):
        result = ponte.telemetry(envelope())
        self.assertEqual(result, dict(temperature=24.5, humidity=60.2, rssi=-55, uptime_ms=1234))
        self.assertNotIn('ts', result)

    def test_rejects_other_devices_even_on_shared_topic(self):
        with self.assertRaises(ValueError):
            ponte.telemetry(envelope(deviceId='other-device'))

    def test_rejects_invalid_sensor_values(self):
        for changes in [dict(temperature=float('nan')), dict(temperature=True),
                        dict(temperature=-41), dict(humidity=101), dict(humidity=-1),
                        dict(rssi=10), dict(uptime_ms=-1)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ponte.telemetry(envelope(**changes))

    def test_rejects_retained_wrong_topic_and_non_byte_payload(self):
        for changes in [dict(retain=True), dict(topic='other/topic'), dict(payload_bytes=[True]),
                        dict(payload_bytes=[256]), dict(payload_bytes=[]), dict(payload_bytes=[255])]:
            value = json.loads(envelope())
            value.update(changes)
            with self.subTest(changes=changes), self.assertRaises((ValueError, UnicodeError)):
                ponte.telemetry(json.dumps(value))

    def test_ignores_status_and_rejects_oversize(self):
        self.assertIsNone(ponte.telemetry('{"event":"status"}'))
        with self.assertRaises(ValueError):
            ponte.telemetry(' ' * 8193)

    def test_posts_to_fixed_origin_with_token_not_user_password(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.status = 200
        ponte.send(opener, 'test-token', {'temperature': 25})
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://xmqr.acmebr.net/api/v1/test-token/telemetry')
        self.assertEqual(request.method, 'POST')
        self.assertEqual(request.get_header('User-agent'), 'XMQR-DHT22-Bridge/1.0')
        self.assertEqual(request.get_header('Accept'), 'application/json')
        self.assertEqual(json.loads(request.data), {'temperature': 25})

    def test_never_follows_redirect_with_device_token(self):
        self.assertIsNone(ponte.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid'))


if __name__ == '__main__':
    unittest.main()
