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


def calculate_audio_rms_db(file_path: Path) -> float:
    """Calculates RMS audio level in dBFS to detect silent or empty clips."""
    try:
        if FFMPEG_BIN:
            cmd = [
                FFMPEG_BIN,
                "-i", str(file_path),
                "-f", "s16le",
                "-ac", "1",
                "-ar", "16000",
                "-"
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            raw = res.stdout
            if len(raw) < 100:
                return -100.0
            import math
            import numpy as np
            samples = np.frombuffer(raw, dtype=np.int16)
            if len(samples) == 0:
                return -100.0
            rms = np.sqrt(np.mean(samples.astype(np.float64)**2))
            if rms > 0:
                return 20 * math.log10(rms / 32768.0)
            return -100.0
    except Exception:
        pass
    return 0.0


def slice_audio_segment(
    input_audio_path: str,
    output_audio_path: str,
    start_sec: float,
    end_sec: float,
    output_format: Optional[str] = "wav",
    target_sample_rate: int = 16000,
) -> bool:
    """
    Losslessly extracts and standardizes an audio clip between start_sec and end_sec.
    Always decodes compressed formats first and exports standard 16 kHz Mono PCM16 WAV.
    Includes post-export duration and RMS energy validation.
    """
    input_path = Path(input_audio_path)
    output_path = Path(output_audio_path)
    os.makedirs(output_path.parent, exist_ok=True)

    start_sec = max(0.0, float(start_sec))
    end_sec = float(end_sec)
    expected_duration = end_sec - start_sec

    if expected_duration <= 0.05:
        logger.warning(f"Invalid timestamp interval: {start_sec}s -> {end_sec}s (duration too small)")
        return False

    # Standard ASR Audio Export: 16kHz, Mono, PCM 16-bit WAV
    if FFMPEG_BIN:
        try:
            cmd_export = [
                FFMPEG_BIN,
                "-y",
                "-ss", f"{start_sec:.3f}",
                "-to", f"{end_sec:.3f}",
                "-i", str(input_path),
                "-ar", str(target_sample_rate),
                "-ac", "1",
                "-c:a", "pcm_s16le",
                "-avoid_negative_ts", "make_zero",
                str(output_path),
            ]
            res = subprocess.run(cmd_export, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            
            if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 500:
                # Post-Export Acoustic & Temporal Validation Gate
                actual_dur = get_audio_duration(str(output_path))
                if actual_dur is not None:
                    dur_delta = abs(actual_dur - expected_duration)
                    if dur_delta > 0.20 and (dur_delta / max(expected_duration, 0.01)) > 0.25:
                        logger.error(f"Duration mismatch for {output_path.name}: expected {expected_duration:.2f}s, got {actual_dur:.2f}s")
                        return False
                        
                    # Check silence
                    rms_db = calculate_audio_rms_db(output_path)
                    if rms_db < -55.0 and actual_dur > 0.5:
                        logger.warning(f"Silent audio clip detected: {output_path.name} (RMS: {rms_db:.1f} dB)")
                        
                    return True
        except Exception as ffmpeg_err:
            logger.debug(f"FFmpeg slicing failed: {ffmpeg_err}")

    # Pydub fallback
    if PYDUB_AVAILABLE:
        try:
            audio = PydubSegment.from_file(str(input_path))
            total_duration_sec = len(audio) / 1000.0
            actual_end_sec = min(total_duration_sec, end_sec)

            start_ms = int(start_sec * 1000)
            end_ms = int(actual_end_sec * 1000)

            clip = audio[start_ms:end_ms]
            clip = clip.set_frame_rate(target_sample_rate).set_channels(1).set_sample_width(2)
            clip.export(str(output_path), format="wav")
            return True
        except Exception as pydub_err:
            logger.debug(f"Pydub slicing attempt encountered: {pydub_err}")

    # Native WAV fallback
    if input_path.suffix.lower() == ".wav":
        return slice_wav_native(
            input_audio_path=input_audio_path,
            output_audio_path=output_audio_path,
            start_sec=start_sec,
            end_sec=end_sec,
        )

    logger.error(f"Failed to slice '{input_audio_path}' to '{output_audio_path}'.")
    return False
