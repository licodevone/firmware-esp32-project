"""Exercise the actual C decoder using an existing offline local build image."""
from pathlib import Path
import subprocess
import unittest


class Dht22Tests(unittest.TestCase):
    def test_decoder_checksum_sign_range_and_output_on_error(self):
        root = Path(__file__).resolve().parent
        command = ['docker', 'run', '--rm', '--pull=never', '--network=none', '--read-only',
                   '--tmpfs', '/work:exec,mode=1777', '--env', 'TMPDIR=/work', '--workdir', '/work',
                   '--mount', f'type=bind,source={root},target=/src,readonly',
                   '--entrypoint', 'sh', 'xmqr-complete-gateway-windows:pl185', '-c',
                   'cc -std=c11 -Wall -Wextra -Werror -I/src/main /src/test_dht22.c '
                   '-o /work/dht22-test && /work/dht22-test']
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])
        self.assertIn('DHT22_FRAME_PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
