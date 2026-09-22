"""
Audio slicing module supporting direct FFmpeg (via imageio-ffmpeg / system PATH),
pydub, and native standard-library fallback for WAV files.
"""

import os
import wave
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("RajVaani.AudioSlicer")

# Find FFmpeg binary
FFMPEG_BIN: Optional[str] = None

try:
    import imageio_ffmpeg
    FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_BIN = shutil.which("ffmpeg")

# Check if pydub is available (audioop-lts provides the 'audioop' module on Python 3.13+)
try:
    import audioop
except ImportError:
    pass

try:
    from pydub import AudioSegment as PydubSegment
    if FFMPEG_BIN:
        PydubSegment.converter = FFMPEG_BIN
        PydubSegment.ffmpeg = FFMPEG_BIN
        PydubSegment.ffprobe = FFMPEG_BIN
    PYDUB_AVAILABLE = True
except Exception:
    PYDUB_AVAILABLE = False


def get_audio_duration(file_path: str) -> Optional[float]:
    """
    Returns audio duration in seconds.
    Tries ffprobe/ffmpeg first, then pydub, then standard wave module for .wav files.
    """
    path = Path(file_path)
    if not path.exists():
        return None

    if FFMPEG_BIN:
        try:
            cmd = [
                FFMPEG_BIN,
                "-i", str(path),
                "-hide_banner",
            ]
            res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, errors="replace")
            for line in res.stderr.splitlines():
                if "Duration:" in line:
                    parts = line.split("Duration:")[1].split(",")[0].strip()
                    h, m, s = parts.split(":")
                    return float(h) * 3600 + float(m) * 60 + float(s)
        except Exception:
            pass

    if PYDUB_AVAILABLE:
        try:
            audio = PydubSegment.from_file(file_path)
            return len(audio) / 1000.0
        except Exception:
            pass

    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return frames / float(rate)
        except Exception as e:
            logger.debug(f"Failed to read WAV duration for {file_path}: {e}")

    return None


def slice_wav_native(
    input_audio_path: str,
    output_audio_path: str,
    start_sec: float,
    end_sec: float,
) -> bool:
    """
    Slices a PCM WAV audio file using only Python standard library wave module.
    Zero external dependencies required.
    """
    input_path = Path(input_audio_path)
    output_path = Path(output_audio_path)
    os.makedirs(output_path.parent, exist_ok=True)

    start_sec = max(0.0, float(start_sec))
    end_sec = float(end_sec)

    if start_sec >= end_sec:
        logger.warning(f"Invalid timestamp interval for native WAV slicing: {start_sec}s -> {end_sec}s")
        return False

    try:
        with wave.open(str(input_path), "rb") as wf_in:
            params = wf_in.getparams()
            n_channels, sampwidth, framerate, n_frames, comptype, compname = params
            if framerate <= 0:
                return False

            total_duration = n_frames / float(framerate)
            actual_end_sec = min(total_duration, end_sec)

            start_frame = int(start_sec * framerate)
            end_frame = int(actual_end_sec * framerate)
            frames_to_read = max(0, end_frame - start_frame)

            wf_in.setpos(start_frame)
            raw_data = wf_in.readframes(frames_to_read)

            with wave.open(str(output_path), "wb") as wf_out:
                wf_out.setnchannels(n_channels)
                wf_out.setsampwidth(sampwidth)
                wf_out.setframerate(framerate)
                wf_out.setcomptype(comptype, compname)
                wf_out.writeframes(raw_data)
            return True
    except Exception as wav_err:
        logger.error(f"Native WAV slicing failed for {input_audio_path}: {wav_err}")
        return False


def slice_audio_segment(
    input_audio_path: str,
    output_audio_path: str,
    start_sec: float,
    end_sec: float,
    output_format: Optional[str] = None,
) -> bool:
    """
    Extracts an audio clip between start_sec and end_sec.
    Prioritizes direct FFmpeg for speed and format flexibility,
    falls back to pydub and native wave module.
    """
    input_path = Path(input_audio_path)
    output_path = Path(output_audio_path)
    os.makedirs(output_path.parent, exist_ok=True)

    start_sec = max(0.0, float(start_sec))
    end_sec = float(end_sec)

    if start_sec >= end_sec:
        logger.warning(f"Invalid timestamp interval: {start_sec}s -> {end_sec}s")
        return False

    # 1. Fast Direct FFmpeg execution (supports mp3, wav, m4a, flac, ogg, etc.)
    if FFMPEG_BIN:
        try:
            # First attempt stream copy for speed
            cmd_copy = [
                FFMPEG_BIN,
                "-y",
                "-ss", f"{start_sec:.3f}",
                "-to", f"{end_sec:.3f}",
                "-i", str(input_path),
                "-c", "copy",
                str(output_path),
            ]
            res = subprocess.run(cmd_copy, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 500:
                return True

            # If copy failed (e.g. keyframe offset issues), re-encode
            cmd_encode = [
                FFMPEG_BIN,
                "-y",
                "-ss", f"{start_sec:.3f}",
                "-to", f"{end_sec:.3f}",
                "-i", str(input_path),
                "-avoid_negative_ts", "make_zero",
                str(output_path),
            ]
            res_enc = subprocess.run(cmd_encode, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if res_enc.returncode == 0 and output_path.exists() and output_path.stat().st_size > 500:
                return True
        except Exception as ffmpeg_err:
            logger.debug(f"Direct FFmpeg slicing failed: {ffmpeg_err}")

    # 2. Pydub fallback
    if PYDUB_AVAILABLE:
        try:
            audio = PydubSegment.from_file(str(input_path))
            total_duration_sec = len(audio) / 1000.0
            actual_end_sec = min(total_duration_sec, end_sec)

            start_ms = int(start_sec * 1000)
            end_ms = int(actual_end_sec * 1000)

            clip = audio[start_ms:end_ms]
            target_fmt = output_format or output_path.suffix.lstrip(".").lower() or "wav"
            clip.export(str(output_path), format=target_fmt)
            return True
        except Exception as pydub_err:
            logger.debug(f"Pydub slicing attempt encountered: {pydub_err}")

    # 3. Native WAV fallback
    if input_path.suffix.lower() == ".wav":
        return slice_wav_native(
            input_audio_path=input_audio_path,
            output_audio_path=output_audio_path,
            start_sec=start_sec,
            end_sec=end_sec,
        )

    logger.error(f"Failed to slice '{input_audio_path}' to '{output_audio_path}'.")
    return False
