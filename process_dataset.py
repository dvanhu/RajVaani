"""
Main dataset processing pipeline for Rajasthani Dialects.
Orchestrates Gemini Files API transcription, audio slicing, text generation, and JSONL manifest creation.
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from config import (
    SUPPORTED_DIALECTS,
    SUPPORTED_AUDIO_EXTENSIONS,
    TranscriptionManifest,
    AudioSegment,
)
from audio_slicer import slice_audio_segment, get_audio_duration
from gemini_processor import GeminiAudioProcessor

# Ensure UTF-8 output streams on Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Load environment variables from .env
load_dotenv()

console = Console(safe_box=True, highlight=False)



def setup_logging(level: str = "INFO"):
    """Configures structured logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def initialize_directories(input_root: Path, output_root: Path, dialects: List[str]):
    """Creates the necessary input and output folder hierarchy."""
    for dialect in dialects:
        (input_root / dialect).mkdir(parents=True, exist_ok=True)
        (output_root / dialect).mkdir(parents=True, exist_ok=True)
    console.print(f"[green]✓ Initialized directories under '{input_root}' and '{output_root}' for dialects: {', '.join(dialects)}[/green]")


def find_audio_files(dialect_dir: Path) -> List[Path]:
    """Recursively locates supported audio files in a dialect directory."""
    if not dialect_dir.exists():
        return []
    files = [
        f for f in dialect_dir.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
    ]
    return sorted(files)


def load_existing_manifest(manifest_path: Path) -> List[Dict[str, Any]]:
    """Loads existing JSONL manifest entries."""
    if not manifest_path.exists():
        return []
    records = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def append_to_manifest(manifest_path: Path, records: List[Dict[str, Any]]):
    """Appends records to the JSONL manifest."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


import hashlib

def calculate_sha256(file_path: Path) -> str:
    """Computes SHA-256 hex digest of a file for cryptographic provenance."""
    if not file_path.exists():
        return ""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


def process_dialect_dataset(
    dialect: str,
    input_root: Path,
    output_root: Path,
    processor: GeminiAudioProcessor,
    slice_audio: bool = True,
    skip_existing: bool = True,
    max_duration_mins: Optional[float] = None,
    max_files: Optional[int] = None,
    workers: int = 5,
) -> Dict[str, Any]:
    """
    Processes all audio files for a single dialect with strict pre-slice temporal validation,
    16kHz mono PCM16 WAV export, exclusions separation, SHA-256 provenance, and multi-threaded acceleration.
    """
    dialect_in_dir = input_root / dialect
    dialect_out_dir = output_root / dialect
    manifest_file = dialect_out_dir / f"{dialect}_metadata.jsonl"
    exclusions_file = dialect_out_dir / f"{dialect}_exclusions.jsonl"

    audio_files = find_audio_files(dialect_in_dir)
    stats = {
        "dialect": dialect,
        "total_files": len(audio_files),
        "processed_files": 0,
        "total_segments": 0,
        "valid_speech_segments": 0,
        "noise_segments": 0,
        "total_speech_duration_sec": 0.0,
    }

    if not audio_files:
        console.print(f"[yellow]! No audio files found in '{dialect_in_dir}'.[/yellow]")
        return stats

    existing_records = load_existing_manifest(manifest_file)
    existing_exclusions = load_existing_manifest(exclusions_file)
    processed_sources = {r.get("source_file") for r in existing_records if "source_file" in r}
    for r in existing_exclusions:
        if "source_file" in r:
            processed_sources.add(r.get("source_file"))

    # Calculate starting segment counter based on existing files/records
    segment_counter = len(existing_records) + len(existing_exclusions) + 1
    counter_lock = threading.Lock()
    file_write_lock = threading.Lock()
    stats_lock = threading.Lock()

    # Filter files to process
    pending_files = []
    for audio_file in audio_files:
        if skip_existing and audio_file.name in processed_sources:
            stats["processed_files"] += 1
            continue
        pending_files.append(audio_file)

    if max_files:
        pending_files = pending_files[:max_files]

    console.print(
        f"\n[bold cyan]─── Processing Dialect: {dialect.upper()} ({len(pending_files)} remaining of {len(audio_files)} files | Workers: {workers}) ───[/bold cyan]"
    )

    if not pending_files:
        console.print(f"[green]✓ All files in '{dialect}' are already processed![/green]")
        return stats

    def _process_single_file(audio_file: Path):
        nonlocal segment_counter

        # Probe raw audio master properties
        source_dur = get_audio_duration(str(audio_file))
        source_sha256 = calculate_sha256(audio_file)

        if source_dur is None or source_dur <= 0.0:
            console.print(f"[bold red]✗ Could not read source audio duration for '{audio_file.name}'. Skipping.[/bold red]")
            return

        clean_stem = "".join([c if c.isalnum() else "_" for c in audio_file.stem])[:24]

        try:
            # 1. Call Gemini to transcribe and segment
            manifest: TranscriptionManifest = processor.process_audio(
                audio_path=str(audio_file),
                dialect_key=dialect,
            )

            num_segments = len(manifest.segments)
            with counter_lock:
                start_seg_idx = segment_counter
                segment_counter += num_segments

            file_speech_records: List[Dict[str, Any]] = []
            file_exclusion_records: List[Dict[str, Any]] = []

            for i, seg in enumerate(manifest.segments):
                curr_idx = start_seg_idx + i
                seg_id = f"segment_{curr_idx:04d}"

                # Pre-slice Temporal Clamp Gate
                clamped_start = max(0.0, float(seg.start_time_seconds))
                clamped_end = min(float(source_dur), float(seg.end_time_seconds))
                duration = round(clamped_end - clamped_start, 3)

                # Traceable Scoped Speaker ID
                scoped_speaker_id = f"spk_{dialect}_{clean_stem}_{seg.speaker_id}"

                # Noise / Singing / Background Music Exclusions Handling
                if seg.is_noise_or_music or duration < 0.3 or clamped_start >= source_dur:
                    exclusion_record = {
                        "segment_id": seg_id,
                        "source_file": audio_file.name,
                        "source_sha256": source_sha256,
                        "dialect": dialect,
                        "start_time_seconds": clamped_start,
                        "end_time_seconds": clamped_end,
                        "duration_seconds": duration,
                        "speaker_id": scoped_speaker_id,
                        "verbatim_devanagari": seg.verbatim_devanagari,
                        "exclusion_reason": seg.notes or "Pure noise, singing, or music",
                        "is_noise_or_music": True,
                        "confidence_score": seg.confidence_score,
                    }
                    file_exclusion_records.append(exclusion_record)
                    continue

                # Standardized ASR Output: 16 kHz Mono PCM16 WAV partitioned into 1,000-segment subfolders
                part_idx = ((curr_idx - 1) // 1000) + 1
                part_folder = f"part_{part_idx:03d}"
                (dialect_out_dir / part_folder).mkdir(parents=True, exist_ok=True)

                out_audio_name = f"{part_folder}/{seg_id}.wav"
                out_text_name = f"{part_folder}/{seg_id}.txt"

                out_audio_path = dialect_out_dir / out_audio_name
                out_text_path = dialect_out_dir / out_text_name

                # 2. Slice audio with post-export validation gate
                slice_success = True
                if slice_audio:
                    slice_success = slice_audio_segment(
                        input_audio_path=str(audio_file),
                        output_audio_path=str(out_audio_path),
                        start_sec=clamped_start,
                        end_sec=clamped_end,
                        output_format="wav",
                        target_sample_rate=16000,
                    )

                if not slice_success:
                    exclusion_record = {
                        "segment_id": seg_id,
                        "source_file": audio_file.name,
                        "source_sha256": source_sha256,
                        "dialect": dialect,
                        "start_time_seconds": clamped_start,
                        "end_time_seconds": clamped_end,
                        "duration_seconds": duration,
                        "speaker_id": scoped_speaker_id,
                        "verbatim_devanagari": seg.verbatim_devanagari,
                        "exclusion_reason": "Failed acoustic/slicing gate",
                        "is_noise_or_music": True,
                        "confidence_score": seg.confidence_score,
                    }
                    file_exclusion_records.append(exclusion_record)
                    continue

                # 3. Write verbatim text file
                with open(out_text_path, "w", encoding="utf-8") as tf:
                    tf.write(seg.verbatim_devanagari.strip() + "\n")

                # Compute exported WAV SHA-256
                exported_sha256 = calculate_sha256(out_audio_path) if out_audio_path.exists() else ""

                # 4. Prepare JSONL record for clean training pair
                record = {
                    "segment_id": seg_id,
                    "source_file": audio_file.name,
                    "source_sha256": source_sha256,
                    "dialect": dialect,
                    "audio_file": out_audio_name,
                    "exported_audio_sha256": exported_sha256,
                    "text_file": out_text_name,
                    "start_time_seconds": clamped_start,
                    "end_time_seconds": clamped_end,
                    "duration_seconds": duration,
                    "speaker_id": scoped_speaker_id,
                    "verbatim_devanagari": seg.verbatim_devanagari.strip(),
                    "audio_format": "16kHz_mono_pcm16_wav",
                    "is_noise_or_music": False,
                    "confidence_score": seg.confidence_score,
                    "notes": seg.notes,
                }
                file_speech_records.append(record)

            # 5. Append records atomically
            with file_write_lock:
                if file_speech_records:
                    append_to_manifest(manifest_file, file_speech_records)
                if file_exclusion_records:
                    append_to_manifest(exclusions_file, file_exclusion_records)

            with stats_lock:
                stats["processed_files"] += 1
                stats["total_segments"] += num_segments
                stats["valid_speech_segments"] += len(file_speech_records)
                stats["noise_segments"] += len(file_exclusion_records)
                stats["total_speech_duration_sec"] += sum(r["duration_seconds"] for r in file_speech_records)

            console.print(
                f"  [green]✓ {audio_file.name}[/green] -> {len(file_speech_records)} valid segments, {len(file_exclusion_records)} exclusions (Total processed: {stats['processed_files']}/{len(pending_files)})"
            )

        except Exception as e:
            console.print(f"[bold red]✗ Failed to process '{audio_file.name}': {e}[/bold red]")
            logging.exception(f"Processing error in {audio_file.name}")

    effective_workers = min(workers, len(pending_files)) if pending_files else 1
    if effective_workers > 1:
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            futures = [executor.submit(_process_single_file, f) for f in pending_files]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    logger.error(f"Worker task error: {exc}")
    else:
        for f in pending_files:
            _process_single_file(f)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="RajVaani: Automated Rajasthani Dialects Audio Processing Pipeline with Gemini API",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input_dir",
        type=str,
        default="input_audio",
        help="Root path containing raw dialect audio folders (e.g. input_audio/bagri/)",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="output_dataset",
        help="Root path where structured dataset will be saved",
    )
    parser.add_argument(
        "--dialects",
        nargs="+",
        default=list(SUPPORTED_DIALECTS.keys()),
        choices=list(SUPPORTED_DIALECTS.keys()) + ["all"],
        help="Specific dialects to process or 'all'",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-3.6-flash",
        help="Gemini model to use for transcription & segmentation",
    )
    parser.add_argument(
        "--api_key",
        type=str,
        default=None,
        help="Gemini API Key (optional, defaults to GEMINI_API_KEY environment variable)",
    )
    parser.add_argument(
        "--max_duration_mins",
        type=float,
        default=None,
        help="Target maximum duration in minutes to process per dialect (e.g., 20.0)",
    )
    parser.add_argument(
        "--max_files",
        type=int,
        default=None,
        help="Maximum number of files to process per dialect",
    )
    parser.add_argument(
        "--no_slice",
        action="store_true",
        help="Disable audio slicing (transcription and metadata only)",
    )
    parser.add_argument(
        "--skip_existing",
        action="store_true",
        default=True,
        help="Skip previously processed audio files (default behavior)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite previously processed audio files",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Number of concurrent worker threads for Gemini API calls & audio slicing",
    )
    parser.add_argument(
        "--init_dirs",
        action="store_true",
        help="Initialize directory tree for all dialects and exit",
    )
    parser.add_argument(
        "--log_level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity level",
    )

    args = parser.parse_args()
    setup_logging(args.log_level)

    input_root = Path(args.input_dir)
    output_root = Path(args.output_dir)

    target_dialects = list(SUPPORTED_DIALECTS.keys()) if "all" in args.dialects else args.dialects

    if args.init_dirs:
        initialize_directories(input_root, output_root, target_dialects)
        return

    # Auto-initialize directories
    initialize_directories(input_root, output_root, target_dialects)

    # Initialize Gemini Processor
    try:
        processor = GeminiAudioProcessor(
            api_key=args.api_key,
            model_name=args.model,
        )
    except Exception as e:
        console.print(f"[bold red]Initialization Error: {e}[/bold red]")
        sys.exit(1)

    console.print("\n[bold magenta]═══════════════════════════════════════════════════════[/bold magenta]")
    console.print("[bold magenta]    RajVaani: Rajasthani Audio Dataset Pipeline       [/bold magenta]")
    console.print("[bold magenta]═══════════════════════════════════════════════════════[/bold magenta]\n")
    console.print(f"• Input Directory:  [cyan]{input_root.resolve()}[/cyan]")
    console.print(f"• Output Directory: [cyan]{output_root.resolve()}[/cyan]")
    console.print(f"• Model:            [cyan]{args.model}[/cyan]")
    console.print(f"• Dialects:         [cyan]{', '.join(target_dialects)}[/cyan]")
    console.print(f"• Workers:          [cyan]{args.workers}[/cyan]")
    console.print(f"• Slice Audio:      [cyan]{not args.no_slice}[/cyan]\n")

    summary_stats = []

    for dialect in target_dialects:
        stat = process_dialect_dataset(
            dialect=dialect,
            input_root=input_root,
            output_root=output_root,
            processor=processor,
            slice_audio=not args.no_slice,
            skip_existing=not args.overwrite,
            max_duration_mins=args.max_duration_mins,
            max_files=args.max_files,
            workers=args.workers,
        )
        summary_stats.append(stat)

    # Display Summary Table
    table = Table(title="\nProcessing Summary Report", show_header=True, header_style="bold magenta")
    table.add_column("Dialect", style="cyan")
    table.add_column("Total Files", justify="right")
    table.add_column("Processed", justify="right")
    table.add_column("Speech Segments", justify="right", style="green")
    table.add_column("Noise Segments", justify="right", style="yellow")
    table.add_column("Speech Audio (sec)", justify="right", style="bold white")

    for s in summary_stats:
        table.add_row(
            s["dialect"].capitalize(),
            str(s["total_files"]),
            str(s["processed_files"]),
            str(s["valid_speech_segments"]),
            str(s["noise_segments"]),
            f"{s['total_speech_duration_sec']:.2f}s",
        )

    console.print(table)
    console.print("\n[bold green]✓ Pipeline run complete![/bold green]\n")


if __name__ == "__main__":
    main()
