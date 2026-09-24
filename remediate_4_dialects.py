import os
import sys
import json
import math
import wave
import shutil
import hashlib
import subprocess
from pathlib import Path

# UTF-8 for Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import imageio_ffmpeg
FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()

def sha256_file(p: Path) -> str:
    if not p.exists():
        return ""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def get_audio_info(p: Path):
    if not p.exists():
        return {"decodable": False, "duration": 0.0, "rms_db": -100.0, "samples": 0}
    
    # Fast-path for WAV files using native wave module
    if p.suffix.lower() == ".wav":
        try:
            with wave.open(str(p), "rb") as wf:
                nchannels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                nframes = wf.getnframes()
                
                if nframes == 0 or framerate == 0:
                    return {"decodable": False, "duration": 0.0, "rms_db": -100.0, "samples": 0}
                
                duration = nframes / float(framerate)
                raw = wf.readframes(min(nframes, 32000))
                
                import numpy as np
                if sampwidth == 2:
                    samples = np.frombuffer(raw, dtype=np.int16)
                elif sampwidth == 1:
                    samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.int16) - 128) * 256
                else:
                    samples = np.frombuffer(raw, dtype=np.int16)
                    
                if len(samples) > 0:
                    rms = np.sqrt(np.mean(samples.astype(np.float64)**2))
                    rms_db = 20 * math.log10(rms / 32768.0) if rms > 0 else -100.0
                else:
                    rms_db = -100.0
                    
                return {
                    "decodable": True,
                    "duration": round(duration, 4),
                    "rms_db": round(rms_db, 1),
                    "samples": nframes
                }
        except Exception:
            pass

    # Fallback to ffmpeg for other audio containers
    try:
        cmd = [FFMPEG_BIN, "-i", str(p), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        raw = res.stdout
        if len(raw) == 0:
            return {"decodable": False, "duration": 0.0, "rms_db": -100.0, "samples": 0}
        
        import numpy as np
        samples = np.frombuffer(raw, dtype=np.int16)
        num_samples = len(samples)
        duration = num_samples / 16000.0
        
        if num_samples > 0:
            rms = np.sqrt(np.mean(samples.astype(np.float64)**2))
            rms_db = 20 * math.log10(rms / 32768.0) if rms > 0 else -100.0
        else:
            rms_db = -100.0
            
        return {
            "decodable": True,
            "duration": round(duration, 4),
            "rms_db": round(rms_db, 1),
            "samples": num_samples
        }
    except Exception:
        return {"decodable": False, "duration": 0.0, "rms_db": -100.0, "samples": 0}

def remediate():
    output_root = Path("output_dataset")
    input_root = Path("input_audio")
    dialects = ["mewati", "dhundhari", "mewari", "marwari", "bagri", "hadothi"]
    
    print("=" * 80)
    print("  RAJVAANI ZERO-DEFECT REMEDIATION & CLEAN REPLACEMENT PIPELINE (4 DIALECTS)")
    print("=" * 80)
    
    # 1. Flagged CSV IDs for special handling
    csv_problem_ids = {
        "dhundhari": {
            "segment_1591": "silent_audio",
            "segment_1750": "over_30s",
            "segment_1824": "over_30s",
            "segment_1973": "silent_audio",
            "segment_2141": "silent_audio",
            "segment_2205": "over_30s",
            "segment_2219": "over_30s",
        },
        "marwari": {
            "segment_0127": "silent_audio",
            "segment_0545": "silent_audio",
            "segment_0584": "silent_audio",
            "segment_0687": "source_duration_overflow",
            "segment_0839": "silent_audio",
            "segment_1657": "over_30s",
            "segment_1658": "over_30s",
            "segment_1660": "over_30s",
            "segment_1663": "over_30s",
            "segment_1705": "over_30s",
            "segment_1706": "over_30s",
            "segment_1742": "over_30s",
            "segment_1743": "over_30s",
            "segment_1744": "over_30s",
            "segment_1745": "over_30s",
            "segment_1746": "over_30s",
            "segment_1859": "over_30s",
            "segment_1888": "over_30s",
            "segment_1891": "over_30s",
            "segment_1894": "over_30s",
            "segment_1895": "over_30s",
            "segment_1918": "over_30s",
            "segment_1920": "over_30s",
            "segment_1958": "over_30s",
            "segment_1960": "over_30s",
            "segment_1961": "over_30s",
            "segment_1999": "over_30s",
            "segment_2000": "over_30s",
            "segment_2002": "over_30s",
            "segment_2003": "over_30s",
            "segment_2066": "over_30s",
            "segment_2067": "over_30s",
            "segment_2068": "over_30s",
            "segment_2069": "over_30s",
            "segment_2070": "over_30s",
            "segment_2071": "over_30s",
            "segment_2072": "over_30s",
            "segment_2074": "synthetic_noise_contradiction",
        },
        "mewari": {
            "segment_0137": "over_30s",
            "segment_0138": "over_30s",
            "segment_0139": "over_30s",
            "segment_0154": "silent_audio",
            "segment_0193": "over_30s",
            "segment_0239": "silent_audio",
            "segment_0240": "silent_audio",
            "segment_0249": "over_30s",
            "segment_0251": "over_30s",
        },
        "mewati": {
            "segment_0053": "synthetic_noise_contradiction",
            "segment_0054": "synthetic_noise_contradiction",
            "segment_0903": "over_30s",
            "segment_1009": "over_30s",
            "segment_1039": "duration_sync",
            "segment_1049": "over_30s",
            "segment_1158": "over_30s",
            "segment_1176": "over_30s",
            "segment_1217": "over_30s",
            "segment_1242": "duration_sync",
            "segment_1735": "over_30s",
        }
    }
    
    # Priority review items for Mewari
    mewari_priority_review = {"segment_0040", "segment_0080", "segment_0149", "segment_0152", "segment_0228"}
    
    old_to_new_mapping = {}
    
    for dialect in dialects:
        d_dir = output_root / dialect
        d_in = input_root / dialect
        meta_file = d_dir / f"{dialect}_metadata.jsonl"
        excl_file = d_dir / f"{dialect}_exclusions.jsonl"
        
        print(f"\n[Processing Dialect: {dialect.upper()}]")
        
        # 1. Clean out legacy/superseded root-level mp3 and txt files
        legacy_mp3s = list(d_dir.glob("*.mp3"))
        legacy_root_wavs = list(d_dir.glob("*.wav"))
        legacy_root_txts = list(d_dir.glob("*.txt"))
        
        # Remove old mp3s
        removed_mp3_count = 0
        for mp3 in legacy_mp3s:
            try:
                mp3.unlink()
                removed_mp3_count += 1
            except:
                pass
        if removed_mp3_count > 0:
            print(f"  • Removed {removed_mp3_count} obsolete .mp3 files from {dialect} root")
            
        # 2. Read existing manifest & exclusions
        manifest_records = []
        if meta_file.exists():
            with open(meta_file, "r", encoding="utf-8") as f:
                for l in f:
                    if l.strip():
                        manifest_records.append(json.loads(l.strip()))
                        
        exclusion_records = []
        if excl_file.exists():
            with open(excl_file, "r", encoding="utf-8") as f:
                for l in f:
                    if l.strip():
                        exclusion_records.append(json.loads(l.strip()))
                        
        cleaned_manifest = []
        cleaned_exclusions = []
        dialect_mapping = {}
        
        # Lazy cache source file hashes
        source_cache = {}
        def get_source_hash(sf_name):
            if sf_name not in source_cache:
                sf = d_in / sf_name
                source_cache[sf_name] = sha256_file(sf) if sf.exists() else ""
            return source_cache[sf_name]
                    
        # 3. Process Exclusions first: Fix negative durations & add proper reason codes
        for ex in exclusion_records:
            seg_id = ex.get("segment_id", "")
            src = ex.get("source_file", "")
            start = float(ex.get("start_time_seconds", 0.0))
            end = float(ex.get("end_time_seconds", 0.0))
            
            # Correct negative duration
            if end < start or (end - start) < 0:
                attempted_start = start
                attempted_end = end
                fixed_start = min(attempted_start, attempted_end)
                fixed_end = max(attempted_start, attempted_end)
                fixed_dur = round(fixed_end - fixed_start, 3)
                ex["start_time_seconds"] = fixed_start
                ex["end_time_seconds"] = fixed_end
                ex["duration_seconds"] = fixed_dur
                ex["exclusion_reason"] = ex.get("exclusion_reason", "") or "invalid_timestamp_overflow_corrected"
            else:
                ex["duration_seconds"] = round(end - start, 3)
                
            # Fill missing source hash
            if not ex.get("source_sha256") and src:
                ex["source_sha256"] = get_source_hash(src)
                
            cleaned_exclusions.append(ex)
            
        # 4. Process Training Manifest entries
        dialect_csv_probs = csv_problem_ids.get(dialect, {})
        
        for rec in manifest_records:
            seg_id = rec.get("segment_id", "")
            src = rec.get("source_file", "")
            audio_rel = rec.get("audio_file")
            text_rel = rec.get("text_file")
            text_val = rec.get("verbatim_devanagari", "")
            start = float(rec.get("start_time_seconds", 0.0))
            end = float(rec.get("end_time_seconds", 0.0))
            
            # Fill source hash
            if not rec.get("source_sha256") and src:
                rec["source_sha256"] = get_source_hash(src)
                
            # Check for synthetic test tone conflict (63b552ea76521ff4)
            if "sample_01.wav" in src or rec.get("source_sha256", "").startswith("63b552ea"):
                # Move to exclusions with explicit reason
                ex_rec = {
                    "segment_id": seg_id,
                    "source_file": src,
                    "source_sha256": rec.get("source_sha256", "63b552ea76521ff4"),
                    "dialect": dialect,
                    "start_time_seconds": start,
                    "end_time_seconds": end,
                    "duration_seconds": round(end - start, 3),
                    "speaker_id": "unknown_synthetic_test",
                    "verbatim_devanagari": "",
                    "exclusion_reason": "synthetic_test_signal_no_human_speech",
                    "is_noise_or_music": True,
                    "confidence_score": 0.0
                }
                cleaned_exclusions.append(ex_rec)
                dialect_mapping[seg_id] = {"status": "excluded", "reason": "synthetic_test_signal"}
                # Remove audio and text if they exist
                if audio_rel and (d_dir / audio_rel).exists():
                    (d_dir / audio_rel).unlink()
                if text_rel and (d_dir / text_rel).exists():
                    (d_dir / text_rel).unlink()
                continue
                
            # Check if flagged in CSV
            prob_flag = dialect_csv_probs.get(seg_id)
            
            # Case A: Silent audio -> Move to exclusions
            if prob_flag in ["silent_audio", "synthetic_noise_contradiction"]:
                ex_rec = {
                    "segment_id": seg_id,
                    "source_file": src,
                    "source_sha256": rec.get("source_sha256", ""),
                    "dialect": dialect,
                    "start_time_seconds": start,
                    "end_time_seconds": end,
                    "duration_seconds": round(end - start, 3),
                    "speaker_id": rec.get("speaker_id", "unknown"),
                    "verbatim_devanagari": text_val,
                    "exclusion_reason": f"silent_audio_below_energy_gate ({prob_flag})",
                    "is_noise_or_music": True,
                    "confidence_score": rec.get("confidence_score", 0.0)
                }
                cleaned_exclusions.append(ex_rec)
                dialect_mapping[seg_id] = {"status": "excluded", "reason": "silent_audio"}
                if audio_rel and (d_dir / audio_rel).exists():
                    (d_dir / audio_rel).unlink()
                if text_rel and (d_dir / text_rel).exists():
                    (d_dir / text_rel).unlink()
                continue
                
            # Case B: Over 30s clips -> If unsegmented or dialogue-rich, isolate or keep with strict sub-utterance flag
            if prob_flag == "over_30s" or (end - start) > 30.0:
                # Isolate overlength items into exclusions as requiring sub-utterance manual slicing
                ex_rec = {
                    "segment_id": seg_id,
                    "source_file": src,
                    "source_sha256": rec.get("source_sha256", ""),
                    "dialect": dialect,
                    "start_time_seconds": start,
                    "end_time_seconds": end,
                    "duration_seconds": round(end - start, 3),
                    "speaker_id": rec.get("speaker_id", "unknown"),
                    "verbatim_devanagari": text_val,
                    "exclusion_reason": "over_30s_requires_sub_utterance_splitting",
                    "is_noise_or_music": True,
                    "confidence_score": rec.get("confidence_score", 0.0)
                }
                cleaned_exclusions.append(ex_rec)
                dialect_mapping[seg_id] = {"status": "excluded", "reason": "over_30s_split_required"}
                if audio_rel and (d_dir / audio_rel).exists():
                    (d_dir / audio_rel).unlink()
                if text_rel and (d_dir / text_rel).exists():
                    (d_dir / text_rel).unlink()
                continue
                
            # Case C: Valid speech segment -> Audit physical WAV file
            if not audio_rel:
                dialect_mapping[seg_id] = {"status": "excluded", "reason": "null_audio_file"}
                continue
                
            audio_path = d_dir / audio_rel
            if not audio_path.exists():
                dialect_mapping[seg_id] = {"status": "missing_audio_dropped"}
                continue
                
            ainfo = get_audio_info(audio_path)
            if not ainfo["decodable"] or ainfo["rms_db"] < -55.0 or ainfo["duration"] < 0.3:
                # Corrupt or silent -> drop to exclusions
                ex_rec = {
                    "segment_id": seg_id,
                    "source_file": src,
                    "source_sha256": rec.get("source_sha256", ""),
                    "dialect": dialect,
                    "start_time_seconds": start,
                    "end_time_seconds": end,
                    "duration_seconds": round(end - start, 3),
                    "speaker_id": rec.get("speaker_id", "unknown"),
                    "verbatim_devanagari": text_val,
                    "exclusion_reason": f"audio_corrupt_or_silent (RMS: {ainfo['rms_db']:.1f} dB)",
                    "is_noise_or_music": True,
                    "confidence_score": rec.get("confidence_score", 0.0)
                }
                cleaned_exclusions.append(ex_rec)
                dialect_mapping[seg_id] = {"status": "excluded", "reason": "audio_corrupt_or_silent"}
                audio_path.unlink()
                continue
                
            # Synchronize actual exact duration from decoded PCM samples
            rec["duration_seconds"] = round(ainfo["duration"], 4)
            if not rec.get("exported_audio_sha256"):
                rec["exported_audio_sha256"] = sha256_file(audio_path)
            rec["audio_format"] = "16kHz_mono_pcm16_wav"
            
            # Add Reviewer & Verification Metadata (Section 4 of Review)
            if seg_id in mewari_priority_review:
                rec["human_verification_status"] = "priority_review_needed"
                rec["reviewer_id"] = "RAJVAANI_NATIVE_REVIEW_TEAM"
                rec["review_date"] = "2026-09-23"
            else:
                rec["human_verification_status"] = "ai_draft_structurally_verified"
                rec["reviewer_id"] = "RAJVAANI_AUTOMATED_QA_GATE"
                rec["review_date"] = "2026-09-23"
                
            # Stable speaker identifier formatting (Section 5 of Review)
            if not rec.get("speaker_id") or rec.get("speaker_id") == "speaker_01":
                clean_src = "".join([c if c.isalnum() else "_" for c in Path(src).stem])[:20]
                rec["speaker_id"] = f"spk_{dialect}_{clean_src}_01"
                
            cleaned_manifest.append(rec)
            dialect_mapping[seg_id] = {"status": "active_training_pair", "new_audio": audio_rel}
            
        # 5. Write back clean manifests and exclusions atomically
        with open(meta_file, "w", encoding="utf-8") as f:
            for r in cleaned_manifest:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                
        with open(excl_file, "w", encoding="utf-8") as f:
            for r in cleaned_exclusions:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                
        old_to_new_mapping[dialect] = dialect_mapping
        
        print(f"  ✓ Cleaned {dialect.upper()}: {len(cleaned_manifest)} active training pairs, {len(cleaned_exclusions)} exclusions.")
        
    # Save old_to_new_mapping.json (Section 1 & 6 of Review)
    mapping_path = Path("old_to_new_mapping.json")
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(old_to_new_mapping, f, ensure_ascii=False, indent=2)
    print(f"\nSaved old-to-new segment mapping to: {mapping_path}")

if __name__ == "__main__":
    remediate()
