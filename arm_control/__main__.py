"""CLI entrypoint; preview mode is the default."""

import argparse
from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent


def build_parser():
    parser = argparse.ArgumentParser(description='MediaPipe robot arm: right elbow/wrist/pinch + left hand rotation')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--port', help='USB UART COM port, for example COM9; enables live control')
    mode.add_argument('--dry-run', action='store_true', help='Preview only; never open a serial port (default)')
    parser.add_argument('--camera', type=int, help='Camera index override')
    parser.add_argument('--config', type=Path, default=ROOT/'config.toml')
    parser.add_argument('--models', type=Path, default=ROOT/'models')
    parser.add_argument('--list-ports', action='store_true')
    parser.add_argument('--list-cameras', action='store_true', help='Probe camera indices 0 through 3')
    parser.add_argument('--download-models', action='store_true', help='Download and verify official model assets')
    parser.add_argument('--headless', action='store_true', help='Bounded camera/inference smoke test; dry-run only')
    parser.add_argument('--frames', type=int, default=0, help='Stop after this many processed frames (0 = until Q)')
    return parser


def validate_args(args):
    args.dry_run = not bool(args.port)
    if args.camera is not None and args.camera < 0:
        raise ValueError('Camera index cannot be negative')
    if args.frames < 0:
        raise ValueError('Frame count cannot be negative')
    if args.headless and (not args.dry_run or args.frames == 0):
        raise ValueError('--headless requires dry-run and a positive --frames count')
    return args


def main(argv=None):
    parser = build_parser()
    try:
        args = validate_args(parser.parse_args(argv))
        if args.download_models:
            from .models import download_models
            download_models(args.models)
            return 0
        if args.list_ports:
            from .transport import list_ports
            ports = list_ports()
            for port, description in ports:
                print(f'{port}: {description}')
            if not ports:
                print('No serial ports found. Connect the ESP32 UART USB connector.')
            return 0
        if args.list_cameras:
            from .app import list_cameras
            list_cameras()
            return 0
        from .config import load_config
        config = load_config(args.config)
        if args.camera is not None:
            config = replace(config, camera=args.camera)
        from .app import run
        return run(config, args)
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
