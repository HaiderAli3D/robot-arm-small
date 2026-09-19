from pathlib import Path
import hashlib
import tempfile
import unittest
from unittest.mock import patch

from arm_control.models import check_models, download_models


class ModelTests(unittest.TestCase):
    def test_corrupted_cached_model_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/'test.task').write_bytes(b'corrupt')
            with patch('arm_control.models.ASSETS', {'test.task': ('https://example.test/model', hashlib.sha256(b'good').hexdigest())}):
                with self.assertRaises(ValueError):
                    check_models(path)

    def test_verified_cached_model_requires_no_network(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/'test.task').write_bytes(b'good')
            with patch('arm_control.models.ASSETS', {'test.task': ('https://example.test/model', hashlib.sha256(b'good').hexdigest())}), patch('urllib.request.urlopen', side_effect=AssertionError('unexpected network')):
                download_models(path)
                check_models(path)


if __name__ == '__main__':
    unittest.main()
