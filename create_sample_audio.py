"""
Utility script to create sample audio files in input_audio/ directories for pipeline testing and verification.
"""

import os
import sys
import math
import struct
import wave
from pathlib import Path

# Ensure UTF-8 output streams on Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config import SUPPORTED_DIALECTS



def create_sample_wav(file_path: Path, duration_sec: float = 8.0, freq: float = 440.0):
    """Creates a clean PCM WAV audio file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 16000
    num_samples = int(duration_sec * sample_rate)
    
    with wave.open(str(file_path), "wb") as wf:
        wf.setnchannels(1)  # Mono
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        
        frames = bytearray()
        for i in range(num_samples):
            # Modulate frequency slightly to simulate acoustic variation
            cur_freq = freq + 20.0 * math.sin(2.0 * math.pi * 1.5 * (i / sample_rate))
            sample_val = int(14000.0 * math.sin(2.0 * math.pi * cur_freq * (i / sample_rate)))
            frames.extend(struct.pack("<h", sample_val))
        
        wf.writeframes(frames)


def main():
    input_root = Path("input_audio")
    print(f"Creating sample test audio files under '{input_root}'...")

    for dialect in SUPPORTED_DIALECTS.keys():
        dialect_dir = input_root / dialect
        dialect_dir.mkdir(parents=True, exist_ok=True)
        sample_file = dialect_dir / f"{dialect}_sample_01.wav"
        if not sample_file.exists():
            create_sample_wav(sample_file, duration_sec=12.0, freq=300.0)
            print(f"  ✓ Created {sample_file}")
        else:
            print(f"  • Already exists: {sample_file}")

    print("\nSample audio files ready in input_audio/")


if __name__ == "__main__":
    main()
