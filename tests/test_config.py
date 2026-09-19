import tempfile
import unittest
from pathlib import Path

from arm_control.config import Config, JointConfig, load_config


class ConfigTests(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.toml'
            path.write_text(text, encoding='utf-8')
            return load_config(path)

    def test_defaults_keep_center_and_hand_sensitivity(self):
        config = load_config(None)
        self.assertEqual(config.claw_open, 90)
        self.assertEqual(len(config.joints), 4)
        self.assertEqual(config.confidence, .4)
        self.assertEqual(config.hand_confidence, .2)

    def test_supplied_config_uses_more_permissive_detection(self):
        config = load_config(Path(__file__).resolve().parents[1] / 'config.toml')
        self.assertEqual(config.confidence, .4)
        self.assertEqual(config.hand_confidence, .2)

    def test_user_joint_override_preserves_other_defaults(self):
        config = self.load('[joints.gpio6]\ndirection=-1\ngain=0.5\n')
        self.assertEqual(config.joints[0], JointConfig(direction=-1,gain=0.5))
        self.assertEqual(config.joints[1], JointConfig())

    def test_large_gain_is_accepted_but_nonfinite_and_nonpositive_are_rejected(self):
        self.assertEqual(self.load('[joints.gpio9]\ngain=100\n').joints[3].gain, 100)
        for gain in (0, -1, float('nan'), float('inf'), True):
            with self.subTest(gain=gain), self.assertRaises(ValueError):
                JointConfig(gain=gain)

    def test_rejects_invalid_or_misspelled_configuration(self):
        for text in ('max_speed=100', 'send_hz=100', 'camera=true', 'smoothing_tau=nan',
                     'deadband=-1', 'loss_timeout=1', 'unknown=3', 'claw_open=0',
                     'hand_confidence=0', 'hand_confidence=nan',
                     'pinch_open_ratio=0.2', 'pinch_open_ratio=0.1',
                     'pinch_open_ratio=nan', 'pinch_open_ratio=inf',
                     '[joints.gpio6]\nminimum=100', '[joints.gpio8]\ndirection=0',
                     '[joints.gpio9]\nminimum=30\n', '[joints.gpio5]\ngain=1',
                     '[joints.gpio7]\nminimun=4', 'joints=[]'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.load(text)

    def test_claw_endpoint_can_be_reversed(self):
        self.assertEqual(self.load('claw_closed=270').claw_closed, 270)

    def test_nonfinite_direct_config_is_rejected(self):
        with self.assertRaises(ValueError):
            Config(smoothing_tau=float('nan'))

    def test_combined_claw_endpoint_must_fit_integer_encoding(self):
        for endpoint,direction,gain in ((-(2**31),1,2), (-(2**31),-1,1),
                                       (2**31-1,1,2)):
            with self.subTest(endpoint=endpoint,direction=direction,gain=gain):
                with self.assertRaisesRegex(ValueError,'claw target'):
                    Config(claw_closed=endpoint,
                           joints=(JointConfig(),)*3+(JointConfig(direction=direction,gain=gain),))
        for target in (-(2**31),2**31-1):
            config = Config(claw_closed=(target+90)/2,
                            joints=(JointConfig(),)*3+(JointConfig(gain=2),))
            self.assertEqual(90+2*(config.claw_closed-90),target)


if __name__ == '__main__':
    unittest.main()
