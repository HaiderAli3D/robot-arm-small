import unittest
from arm_control.__main__ import build_parser, validate_args


class CLITests(unittest.TestCase):
    def test_preview_is_default(self):
        args = validate_args(build_parser().parse_args([]))
        self.assertTrue(args.dry_run)

    def test_live_headless_is_rejected(self):
        args = build_parser().parse_args(['--port','COM9','--headless','--frames','2'])
        with self.assertRaises(ValueError):
            validate_args(args)

    def test_unbounded_headless_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_args(build_parser().parse_args(['--headless']))

    def test_bounded_preview_is_accepted(self):
        args = validate_args(build_parser().parse_args(['--dry-run','--headless','--frames','10']))
        self.assertEqual(args.frames,10)

    def test_negative_camera_or_frame_count_is_rejected(self):
        for flag in ('--camera','--frames'):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                validate_args(build_parser().parse_args([flag,'-1']))


if __name__ == '__main__':
    unittest.main()
