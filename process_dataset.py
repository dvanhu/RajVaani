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


def process_dialect_dataset(
    dialect: str,
    input_root: Path,
    output_root: Path,
    processor: GeminiAudioProcessor,
    slice_audio: bool = True,
    skip_existing: bool = True,
    max_duration_mins: Optional[float] = None,
    max_files: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Processes all audio files for a single dialect up to max_duration_mins or max_files.
    """
    dialect_in_dir = input_root / dialect
    dialect_out_dir = output_root / dialect
    manifest_file = dialect_out_dir / f"{dialect}_metadata.jsonl"

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
    processed_sources = {r.get("source_file") for r in existing_records if "source_file" in r}

    # Calculate starting segment counter based on existing files/records
    segment_counter = len(existing_records) + 1

    console.print(f"\n[bold cyan]─── Processing Dialect: {dialect.upper()} ({len(audio_files)} files) ───[/bold cyan]")

    for audio_file in audio_files:
        # Check limits
        if max_files and stats["processed_files"] >= max_files:
            console.print(f"[green]✓ Reached max files limit ({max_files}) for {dialect}. Stopping.[/green]")
            break

        if max_duration_mins and (stats["total_speech_duration_sec"] >= max_duration_mins * 60.0):
            console.print(f"[green]✓ Reached target duration limit ({max_duration_mins:.1f} mins) for {dialect}. Stopping.[/green]")
            break

        if skip_existing and audio_file.name in processed_sources:
            console.print(f"[dim]• Skipping already processed file: {audio_file.name}[/dim]")
            stats["processed_files"] += 1
            continue

        console.print(f"[bold]▶ Processing file:[/bold] [blue]{audio_file.name}[/blue]")

        try:
            # 1. Call Gemini to transcribe and segment
            manifest: TranscriptionManifest = processor.process_audio(
                audio_path=str(audio_file),
                dialect_key=dialect,
            )

            file_records: List[Dict[str, Any]] = []

            for seg in manifest.segments:
                seg_id = f"segment_{segment_counter:04d}"
                duration = round(seg.end_time_seconds - seg.start_time_seconds, 3)

                stats["total_segments"] += 1

                if seg.is_noise_or_music:
                    stats["noise_segments"] += 1
                    console.print(f"  [yellow]• [{seg_id}] Flagged as noise/music ({seg.start_time_seconds:.1f}s - {seg.end_time_seconds:.1f}s)[/yellow]")
                    
                    record = {
                        "segment_id": seg_id,
                        "source_file": audio_file.name,
                        "dialect": dialect,
                        "audio_file": None,
                        "text_file": None,
                        "start_time_seconds": seg.start_time_seconds,
                        "end_time_seconds": seg.end_time_seconds,
                        "duration_seconds": duration,
                        "speaker_id": seg.speaker_id,
                        "verbatim_devanagari": seg.verbatim_devanagari,
                        "is_noise_or_music": True,
                        "confidence_score": seg.confidence_score,
                        "notes": seg.notes or "Pure noise / music",
                    }
                    file_records.append(record)
                    segment_counter += 1
                    continue

                # Valid speech segment
                stats["valid_speech_segments"] += 1
                stats["total_speech_duration_sec"] += duration

                # Determine audio output format (keep original extension or fallback to wav)
                audio_ext = audio_file.suffix.lower() if audio_file.suffix.lower() in [".wav", ".mp3"] else ".wav"
                out_audio_name = f"{seg_id}{audio_ext}"
                out_text_name = f"{seg_id}.txt"

                out_audio_path = dialect_out_dir / out_audio_name
                out_text_path = dialect_out_dir / out_text_name

                # 2. Slice audio if enabled
                if slice_audio:
                    slice_success = slice_audio_segment(
                        input_audio_path=str(audio_file),
                        output_audio_path=str(out_audio_path),
                        start_sec=seg.start_time_seconds,
                        end_sec=seg.end_time_seconds,
                    )
                    if not slice_success:
                        console.print(f"  [red]✗ Slicing failed for {seg_id}[/red]")

                # 3. Write verbatim text file
                with open(out_text_path, "w", encoding="utf-8") as tf:
                    tf.write(seg.verbatim_devanagari.strip() + "\n")

                # 4. Prepare JSONL record
                record = {
                    "segment_id": seg_id,
                    "source_file": audio_file.name,
                    "dialect": dialect,
                    "audio_file": out_audio_name,
                    "text_file": out_text_name,
                    "start_time_seconds": seg.start_time_seconds,
                    "end_time_seconds": seg.end_time_seconds,
                    "duration_seconds": duration,
                    "speaker_id": seg.speaker_id,
                    "verbatim_devanagari": seg.verbatim_devanagari.strip(),
                    "is_noise_or_music": False,
                    "confidence_score": seg.confidence_score,
                    "notes": seg.notes,
                }
                file_records.append(record)
                segment_counter += 1

                console.print(
                    f"  [green]✓ {seg_id}[/green] ({seg.start_time_seconds:.1f}s - {seg.end_time_seconds:.1f}s | {seg.speaker_id}): "
                    f"[white]{seg.verbatim_devanagari[:45]}...[/white]"
                )

            # 5. Append records to dialect metadata manifest
            append_to_manifest(manifest_file, file_records)
            stats["processed_files"] += 1

        except Exception as e:
            console.print(f"[bold red]✗ Failed to process '{audio_file.name}': {e}[/bold red]")
            logging.exception(f"Processing error in {audio_file.name}")

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
        "--overwrite",
        action="store_true",
        help="Overwrite previously processed audio files",
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
