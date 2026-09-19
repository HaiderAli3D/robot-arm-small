"""Pinned official MediaPipe model assets with SHA-256 integrity checks."""

import hashlib
from pathlib import Path
import urllib.request

ASSETS = {
    'hand_landmarker.task': (
        'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
        'fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1'),
    'pose_landmarker_lite.task': (
        'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task',
        '59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a'),
}


def _matches(path, expected):
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected


def check_models(directory: Path):
    for name, (_, digest) in ASSETS.items():
        if not _matches(directory / name, digest):
            raise ValueError(f'Missing or damaged model: {name}. Run python -m arm_control --download-models')


def download_models(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    for name, (url, digest) in ASSETS.items():
        destination = directory / name
        if _matches(destination, digest):
            print(f'Model verified: {name}')
            continue
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read(32 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f'Model checksum mismatch: {name}; no model was replaced')
        partial = destination.with_suffix('.part')
        partial.write_bytes(data)
        partial.replace(destination)
        print(f'Model downloaded and verified: {name}')
