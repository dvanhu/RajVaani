import os
import sys
import json
import math
import subprocess
from pathlib import Path
from typing import Dict, List, Any

import numpy as np

# Set UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import imageio_ffmpeg
FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()

import wave

def get_audio_info(file_path: Path) -> Dict[str, Any]:
    """Get duration, decodability, rms volume, sample rate, channels using fast native wave with ffmpeg fallback."""
    if not file_path.exists():
        return {"error": "File does not exist", "decodable": False, "duration": 0.0, "rms_db": -999.0, "size_bytes": 0}
    
    # Fast path for WAV files
    if file_path.suffix.lower() == ".wav":
        try:
            with wave.open(str(file_path), "rb") as wf:
                channels = wf.getnchannels()
                sample_rate = wf.getframerate()
                sampwidth = wf.getsampwidth()
                nframes = wf.getnframes()
                
                if nframes > 0 and sample_rate > 0:
                    duration = nframes / float(sample_rate)
                    raw_pcm = wf.readframes(min(nframes, 32000))
                    if sampwidth == 2:
                        samples = np.frombuffer(raw_pcm, dtype=np.int16)
                    elif sampwidth == 1:
                        samples = (np.frombuffer(raw_pcm, dtype=np.uint8).astype(np.int16) - 128) * 256
                    else:
                        samples = np.frombuffer(raw_pcm, dtype=np.int16)
                    
                    if len(samples) > 0:
                        rms = np.sqrt(np.mean(samples.astype(np.float64)**2))
                        rms_db = 20 * math.log10(rms / 32768.0) if rms > 0 else -100.0
                    else:
                        rms_db = -100.0
                        
                    is_silent = (rms_db < -55.0) or (duration < 0.05)
                    return {
                        "decodable": True,
                        "duration": duration,
                        "sample_rate": sample_rate,
                        "channels": channels,
                        "rms_db": rms_db,
                        "is_silent": is_silent,
                        "size_bytes": file_path.stat().st_size
                    }
        except Exception:
            pass

    cmd = [
        FFMPEG_BIN,
        "-i", str(file_path),
        "-f", "null",
        "-"
    ]
    res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, errors="replace")
    
    duration = None
    channels = None
    sample_rate = None
    for line in res.stderr.splitlines():
        if "Duration:" in line:
            try:
                parts = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = parts.split(":")
                duration = float(h) * 3600 + float(m) * 60 + float(s)
            except Exception:
                pass
        if "Audio:" in line:
            try:
                audio_part = line.split("Audio:")[1]
                if "Hz" in audio_part:
                    sr_str = audio_part.split("Hz")[0].split(",")[-1].strip()
                    sample_rate = int(sr_str)
                if "mono" in audio_part:
                    channels = 1
                elif "stereo" in audio_part:
                    channels = 2
            except Exception:
                pass

    decodable = (res.returncode == 0) and (duration is not None) and (duration > 0.0)

    rms_db = -999.0
    is_silent = False
    if decodable and duration > 0.001:
        cmd_pcm = [
            FFMPEG_BIN,
            "-i", str(file_path),
            "-f", "s16le",
            "-ac", "1",
            "-ar", "16000",
            "-"
        ]
        res_pcm = subprocess.run(cmd_pcm, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        raw_pcm = res_pcm.stdout
        if len(raw_pcm) > 0:
            samples = np.frombuffer(raw_pcm, dtype=np.int16)
            if len(samples) > 0:
                rms = np.sqrt(np.mean(samples.astype(np.float64)**2))
                if rms > 0:
                    rms_db = 20 * math.log10(rms / 32768.0)
                else:
                    rms_db = -100.0
                if rms_db < -50.0 or duration < 0.05:
                    is_silent = True
            else:
                is_silent = True
        else:
            is_silent = True
            decodable = False
    elif duration is not None and duration <= 0.005:
        is_silent = True

    return {
        "decodable": decodable,
        "duration": duration if duration is not None else 0.0,
        "sample_rate": sample_rate,
        "channels": channels,
        "rms_db": rms_db,
        "is_silent": is_silent,
        "size_bytes": file_path.stat().st_size
    }

from audio_slicer import get_audio_duration

def audit():
    output_dir = Path("output_dataset")
    input_dir = Path("input_audio")
    
    dialects = ["mewari", "marwari", "dhundhari", "mewati", "bagri", "hadothi"]
    
    print("=" * 80)
    print("           RAJVAANI COMPREHENSIVE DATASET AUDIT REPORT")
    print("=" * 80)
    
    source_durations = {}
    dialect_results = {}
    
    for dialect in dialects:
        d_out = output_dir / dialect
        d_in = input_dir / dialect
        manifest_path = d_out / f"{dialect}_metadata.jsonl"
        
        if not manifest_path.exists():
            print(f"Warning: Manifest {manifest_path} not found!")
            continue
            
        entries = []
        with open(manifest_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        entries.append(json.loads(line.strip()))
                    except Exception as e:
                        print(f"JSON decode error in {dialect}: {e}")
                        
        d_stats = {
            "metadata_entries": len(entries),
            "audio_files": 0,
            "noise_entries": 0,
            "speech_entries": 0,
            "passed": 0,
            "failed": 0,
            "passed_duration_sec": 0.0,
            "decoding_failures": [],
            "silent_or_truncated": [],
            "duration_mismatch": [],
            "timestamp_exceeds_source": [],
            "invalid_timestamp_interval": [],
            "text_mismatches": [],
            "digits_found": [],
            "long_clips_gt_30s": [],
            "short_clips_lt_3s": [],
            "missing_audio": [],
            "missing_text": [],
            "issues": []
        }
        
        for rec in entries:
            seg_id = rec.get("segment_id", "unknown")
            source_file = rec.get("source_file", "")
            is_noise = rec.get("is_noise_or_music", False)
            start_s = rec.get("start_time_seconds", 0.0)
            end_s = rec.get("end_time_seconds", 0.0)
            meta_dur = rec.get("duration_seconds", round(end_s - start_s, 3))
            audio_name = rec.get("audio_file")
            text_name = rec.get("text_file")
            transcript = rec.get("verbatim_devanagari", "")
            
            source_path = d_in / source_file if source_file else None
            source_dur = None
            if source_path and source_path.exists():
                if str(source_path) not in source_durations:
                    source_durations[str(source_path)] = get_audio_duration(str(source_path)) or 0.0
                source_dur = source_durations[str(source_path)]
            
            has_error = False
            item_issues = []
            
            if is_noise or audio_name is None:
                d_stats["noise_entries"] += 1
                continue
            
            d_stats["speech_entries"] += 1
            
            # Check timestamps against source file
            if source_dur is not None:
                if end_s > source_dur + 0.5:
                    d_stats["timestamp_exceeds_source"].append({
                        "seg_id": seg_id,
                        "source_file": source_file,
                        "source_dur": round(source_dur, 2),
                        "end_s": round(end_s, 2),
                        "diff": round(end_s - source_dur, 2)
                    })
                    item_issues.append(f"Timestamp end ({end_s:.2f}s) exceeds source duration ({source_dur:.2f}s)")
                    has_error = True
            
            if start_s < 0 or end_s <= start_s:
                d_stats["invalid_timestamp_interval"].append(seg_id)
                item_issues.append(f"Invalid timestamp range: {start_s}s -> {end_s}s")
                has_error = True
                
            # Check audio file
            audio_path = d_out / audio_name
            if not audio_path.exists():
                d_stats["missing_audio"].append(seg_id)
                item_issues.append(f"Missing audio file: {audio_name}")
                has_error = True
            else:
                d_stats["audio_files"] += 1
                ainfo = get_audio_info(audio_path)
                
                if not ainfo["decodable"]:
                    d_stats["decoding_failures"].append({
                        "seg_id": seg_id,
                        "audio_name": audio_name,
                        "meta_dur": meta_dur,
                        "size_bytes": ainfo["size_bytes"]
                    })
                    item_issues.append(f"Could not decode audio ({audio_name}, size: {ainfo['size_bytes']} bytes)")
                    has_error = True
                elif ainfo["is_silent"] or ainfo["duration"] < 0.05:
                    d_stats["silent_or_truncated"].append({
                        "seg_id": seg_id,
                        "audio_name": audio_name,
                        "meta_dur": meta_dur,
                        "actual_dur": round(ainfo["duration"], 3),
                        "rms_db": round(ainfo["rms_db"], 1)
                    })
                    item_issues.append(f"Silent or truncated audio ({ainfo['duration']:.3f}s, {ainfo['rms_db']:.1f} dB)")
                    has_error = True
                else:
                    dur_diff = abs(ainfo["duration"] - meta_dur)
                    if dur_diff > 0.5 and (dur_diff / max(meta_dur, 0.001)) > 0.15:
                        d_stats["duration_mismatch"].append({
                            "seg_id": seg_id,
                            "audio_name": audio_name,
                            "meta_dur": meta_dur,
                            "actual_dur": round(ainfo["duration"], 3),
                            "diff": round(dur_diff, 3)
                        })
                        item_issues.append(f"Duration mismatch: meta={meta_dur:.2f}s, actual={ainfo['duration']:.2f}s")
                        has_error = True
                        
                if ainfo["duration"] > 30.0:
                    d_stats["long_clips_gt_30s"].append({"seg_id": seg_id, "dur": round(ainfo["duration"], 2)})
                elif ainfo["duration"] < 3.0:
                    d_stats["short_clips_lt_3s"].append({"seg_id": seg_id, "dur": round(ainfo["duration"], 2)})
            
            # Check text file
            if text_name:
                text_path = d_out / text_name
                if not text_path.exists():
                    d_stats["missing_text"].append(seg_id)
                    item_issues.append(f"Missing text file: {text_name}")
                    has_error = True
                else:
                    try:
                        content = text_path.read_text(encoding="utf-8").strip()
                        if content != transcript.strip():
                            d_stats["text_mismatches"].append(seg_id)
                            item_issues.append("Text file content mismatch with JSONL")
                    except Exception as te:
                        item_issues.append(f"Error reading text file: {te}")
                        has_error = True
                        
            digits_in_transcript = [c for c in transcript if c in "0123456789"]
            if digits_in_transcript:
                d_stats["digits_found"].append({"seg_id": seg_id, "digits": "".join(digits_in_transcript), "text": transcript[:30]})
                
            if has_error:
                d_stats["failed"] += 1
                d_stats["issues"].append({"seg_id": seg_id, "source_file": source_file, "issues": item_issues})
            else:
                d_stats["passed"] += 1
                d_stats["passed_duration_sec"] += meta_dur
                
        dialect_results[dialect] = d_stats
        
    print(f"\n{'DIALECT':<12} | {'TOTAL':<7} | {'NOISE':<6} | {'PASSED':<8} | {'FAILED/NEEDS REPAIR':<20} | {'PASS DURATION':<14}")
    print("-" * 75)
    
    grand_total_meta = 0
    grand_total_passed = 0
    grand_total_failed = 0
    grand_total_pass_dur = 0.0
    
    for dialect, d_stats in dialect_results.items():
        total_m = d_stats["metadata_entries"]
        passed = d_stats["passed"]
        failed = d_stats["failed"] + d_stats["noise_entries"]
        dur_min = d_stats["passed_duration_sec"] / 60.0
        
        grand_total_meta += total_m
        grand_total_passed += passed
        grand_total_failed += failed
        grand_total_pass_dur += dur_min
        
        print(f"{dialect.capitalize():<12} | {total_m:<7} | {d_stats['noise_entries']:<6} | {passed:<8} | {failed:<20} | {dur_min:<6.2f} min")
        
    print("-" * 75)
    print(f"{'TOTAL':<12} | {grand_total_meta:<7} | {'-':<6} | {grand_total_passed:<8} | {grand_total_failed:<20} | {grand_total_pass_dur:<6.2f} min")
    print("\n" + "=" * 80)
    
    with open("audit_report.json", "w", encoding="utf-8") as f:
        json.dump(dialect_results, f, ensure_ascii=False, indent=2)
    print("Detailed audit report written to audit_report.json")

if __name__ == "__main__":
    audit()
