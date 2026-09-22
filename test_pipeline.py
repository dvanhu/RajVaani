"""
Comprehensive test suite for the RajVaani Audio Processing Pipeline.
Tests audio generation, audio slicing, schema validation, prompt generation, and mocked pipeline execution.
"""

import os
import math
import struct
import wave
import json
import shutil
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure UTF-8 output streams on Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


from config import (
    SUPPORTED_DIALECTS,
    TranscriptionManifest,
    AudioSegment,
    build_system_prompt,
)
from audio_slicer import slice_wav_native, slice_audio_segment, get_audio_duration
from process_dataset import (
    initialize_directories,
    load_existing_manifest,
    append_to_manifest,
    process_dialect_dataset,
)


def create_synthetic_wav(file_path: str, duration_sec: float = 3.0, sample_rate: int = 16000, freq: float = 440.0):
    """Generates a synthetic sine wave WAV file using standard library modules."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    num_samples = int(duration_sec * sample_rate)
    with wave.open(file_path, "wb") as wf:
        wf.setnchannels(1)  # Mono
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        
        frames = bytearray()
        for i in range(num_samples):
            # Generate sine wave sample
            sample_val = int(16000.0 * math.sin(2.0 * math.pi * freq * (i / sample_rate)))
            frames.extend(struct.pack("<h", sample_val))
        
        wf.writeframes(frames)


class TestRajVaaniConfigAndSchemas(unittest.TestCase):
    """Tests for configuration, prompts, and Pydantic schemas."""

    def test_supported_dialects_completeness(self):
        expected_dialects = {"bagri", "hadothi", "marwari", "mewari", "dhundhari", "mewati"}
        self.assertEqual(set(SUPPORTED_DIALECTS.keys()), expected_dialects)
        for d, info in SUPPORTED_DIALECTS.items():
            self.assertIn("name_english", info)
            self.assertIn("name_devanagari", info)
            self.assertIn("regions", info)
            self.assertIn("linguistic_notes", info)

    def test_build_system_prompt(self):
        for dialect in SUPPORTED_DIALECTS.keys():
            prompt = build_system_prompt(dialect)
            self.assertIn(SUPPORTED_DIALECTS[dialect]["name_english"], prompt)
            self.assertIn("VERBATIM DEVANAGARI TRANSCRIPTION", prompt)
            self.assertIn("SPOKEN NUMBERS", prompt)
            self.assertIn("NATURAL SPEECH SEGMENTATION", prompt)

    def test_transcription_manifest_schema_validation(self):
        sample_data = {
            "dialect": "marwari",
            "source_filename": "marwari_sample.wav",
            "total_duration_seconds": 15.0,
            "detected_speakers": ["speaker_01", "speaker_02"],
            "segments": [
                {
                    "segment_index": 1,
                    "start_time_seconds": 0.0,
                    "end_time_seconds": 7.5,
                    "speaker_id": "speaker_01",
                    "verbatim_devanagari": "म्हारो नाम भंवरलाल है अर म्हे जोधपुर रा रैवासी हां।",
                    "is_noise_or_music": False,
                    "confidence_score": 0.99,
                    "notes": "Clear Marwari speech",
                },
                {
                    "segment_index": 2,
                    "start_time_seconds": 7.5,
                    "end_time_seconds": 15.0,
                    "speaker_id": "speaker_02",
                    "verbatim_devanagari": "च्यार बजे म्हे गांव जासां।",
                    "is_noise_or_music": False,
                    "confidence_score": 0.97,
                    "notes": "Number four spoken as 'च्यार'",
                },
            ],
        }
        manifest = TranscriptionManifest(**sample_data)
        self.assertEqual(manifest.dialect, "marwari")
        self.assertEqual(len(manifest.segments), 2)
        self.assertEqual(manifest.segments[0].speaker_id, "speaker_01")
        self.assertFalse(manifest.segments[1].is_noise_or_music)


class TestAudioSlicer(unittest.TestCase):
    """Tests for native and pydub audio slicing."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.raw_wav = os.path.join(self.test_dir, "test_tone.wav")
        create_synthetic_wav(self.raw_wav, duration_sec=6.0)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_audio_duration(self):
        dur = get_audio_duration(self.raw_wav)
        self.assertIsNotNone(dur)
        self.assertAlmostEqual(dur, 6.0, delta=0.1)

    def test_slice_wav_native(self):
        out_wav = os.path.join(self.test_dir, "slice_native.wav")
        success = slice_wav_native(self.raw_wav, out_wav, start_sec=1.5, end_sec=4.5)
        self.assertTrue(success)
        self.assertTrue(os.path.exists(out_wav))
        
        sliced_dur = get_audio_duration(out_wav)
        self.assertIsNotNone(sliced_dur)
        self.assertAlmostEqual(sliced_dur, 3.0, delta=0.1)

    def test_slice_audio_segment(self):
        out_wav = os.path.join(self.test_dir, "slice_general.wav")
        success = slice_audio_segment(self.raw_wav, out_wav, start_sec=2.0, end_sec=5.0)
        self.assertTrue(success)
        self.assertTrue(os.path.exists(out_wav))
        
        sliced_dur = get_audio_duration(out_wav)
        self.assertIsNotNone(sliced_dur)
        self.assertAlmostEqual(sliced_dur, 3.0, delta=0.1)


class TestPipelineOrchestration(unittest.TestCase):
    """Tests directory setup, manifest operations, and mocked pipeline runs."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.input_root = Path(self.test_dir) / "input_audio"
        self.output_root = Path(self.test_dir) / "output_dataset"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_initialize_directories(self):
        dialects = ["bagri", "hadothi", "marwari", "mewari", "dhundhari", "mewati"]
        initialize_directories(self.input_root, self.output_root, dialects)
        for d in dialects:
            self.assertTrue((self.input_root / d).is_dir())
            self.assertTrue((self.output_root / d).is_dir())

    def test_manifest_read_write(self):
        manifest_path = self.output_root / "bagri" / "bagri_metadata.jsonl"
        records = [
            {"segment_id": "segment_0001", "verbatim_devanagari": "म्हे आवां हां"},
            {"segment_id": "segment_0002", "verbatim_devanagari": "कोनी ग्या"},
        ]
        append_to_manifest(manifest_path, records)
        loaded = load_existing_manifest(manifest_path)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["segment_id"], "segment_0001")
        self.assertEqual(loaded[1]["verbatim_devanagari"], "कोनी ग्या")

    def test_mocked_dialect_processing(self):
        # Create input dialect folder & synthetic audio file
        bagri_in = self.input_root / "bagri"
        bagri_in.mkdir(parents=True, exist_ok=True)
        sample_audio = bagri_in / "interview_01.wav"
        create_synthetic_wav(str(sample_audio), duration_sec=10.0)

        # Prepare mock processor
        mock_processor = MagicMock()
        mock_processor.process_audio.return_value = TranscriptionManifest(
            dialect="bagri",
            source_filename="interview_01.wav",
            total_duration_seconds=10.0,
            detected_speakers=["speaker_01"],
            segments=[
                AudioSegment(
                    segment_index=1,
                    start_time_seconds=0.0,
                    end_time_seconds=5.0,
                    speaker_id="speaker_01",
                    verbatim_devanagari="म्हारो नाम सोहनलाल है अर म्हे गंगानगर रा हां।",
                    is_noise_or_music=False,
                    confidence_score=0.98,
                ),
                AudioSegment(
                    segment_index=2,
                    start_time_seconds=5.0,
                    end_time_seconds=10.0,
                    speaker_id="speaker_01",
                    verbatim_devanagari="[पृष्ठभूमि संगीत / शोर]",
                    is_noise_or_music=True,
                    confidence_score=0.90,
                    notes="Pure background noise",
                ),
            ],
        )

        stats = process_dialect_dataset(
            dialect="bagri",
            input_root=self.input_root,
            output_root=self.output_root,
            processor=mock_processor,
            slice_audio=True,
            skip_existing=False,
        )

        self.assertEqual(stats["processed_files"], 1)
        self.assertEqual(stats["valid_speech_segments"], 1)
        self.assertEqual(stats["noise_segments"], 1)

        # Verify output directory structure
        bagri_out = self.output_root / "bagri"
        self.assertTrue((bagri_out / "segment_0001.wav").exists())
        self.assertTrue((bagri_out / "segment_0001.txt").exists())
        
        # Verify text content
        with open(bagri_out / "segment_0001.txt", "r", encoding="utf-8") as f:
            text_content = f.read().strip()
            self.assertEqual(text_content, "म्हारो नाम सोहनलाल है अर म्हे गंगानगर रा हां।")

        # Verify JSONL metadata
        manifest_path = bagri_out / "bagri_metadata.jsonl"
        self.assertTrue(manifest_path.exists())
        manifest_entries = load_existing_manifest(manifest_path)
        self.assertEqual(len(manifest_entries), 2)
        self.assertEqual(manifest_entries[0]["segment_id"], "segment_0001")
        self.assertFalse(manifest_entries[0]["is_noise_or_music"])
        self.assertTrue(manifest_entries[1]["is_noise_or_music"])


if __name__ == "__main__":
    unittest.main()
