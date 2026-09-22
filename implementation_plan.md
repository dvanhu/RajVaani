# Implementation Plan - Rajasthani Dialects Audio Processing Pipeline (`RajVaani`)

Build a complete, automated Python pipeline to process multi-dialect Rajasthani audio datasets (Bagri, Hadothi, Marwari, Mewari, Dhundhari) using the Gemini API (`gemini-2.5-flash` via `google-genai` SDK), slice audio into natural segment clips, transcribe verbatim Devanagari text, and generate structured manifest datasets.

## User Review Required

> [!IMPORTANT]
> - The pipeline uses the latest **`google-genai`** SDK (`from google import genai`) and targets `gemini-2.5-flash` for high accuracy, speed, and cost efficiency.
> - Structured outputs with Pydantic JSON Schema ensure strict schema conformity for timestamps, speaker labels, noise flags, and verbatim Devanagari transcription.
> - Audio slicing will support both standard `.wav` processing natively (Python standard library) and compressed formats (`.mp3`, `.m4a`, `.ogg`) via `pydub` (with ffmpeg).

## Proposed Architecture & Directory Structure

```
RajVaani/
├── input_audio/                     # Raw dialect audio input
│   ├── bagri/
│   ├── hadothi/
│   ├── marwari/
│   ├── mewari/
│   └── dhundhari/
├── output_dataset/                  # Structured final dataset
│   ├── bagri/
│   │   ├── segment_001.mp3 / .wav
│   │   ├── segment_001.txt
│   │   └── bagri_metadata.jsonl
│   ├── hadothi/
│   ├── marwari/
│   ├── mewari/
│   └── dhundhari/
├── config.py                        # Dialect definitions, prompts, & constants
├── audio_slicer.py                  # Audio slicing utility (pydub + native wave fallback)
├── gemini_processor.py              # Gemini Files API, upload/wait, structured transcription
├── process_dataset.py               # Main CLI orchestrator with progress bar & retries
├── test_pipeline.py                 # Unit & mock pipeline validation suite
├── requirements.txt                 # Dependencies
├── .env.example                     # Environment template
└── README.md                        # Documentation and user guide
```

## Key Components

### 1. `config.py`
- Dialect configurations with localized context guidelines:
  - **Bagri**: Ganganagar, Hanumangarh, Sirsa border nuances.
  - **Hadothi**: Kota, Bundi, Baran, Jhalawar speech characteristics.
  - **Marwari**: Jodhpur, Barmer, Jaisalmer, Nagaur phonetics.
  - **Mewari**: Udaipur, Chittorgarh, Rajsamand linguistic traits.
  - **Dhundhari**: Jaipur, Dausa, Tonk grammatical and lexical markers.
- System prompt enforcing:
  1. Strict verbatim Devanagari (no Hindi normalization).
  2. All numbers spelled out in dialect words.
  3. Natural segment chunking between 5 to 20 seconds at natural pauses.
  4. Speaker tagging (`speaker_01`, `speaker_02`, etc.).
  5. Noise / singing / music detection and flagging.
- Pydantic models for structured output parsing (`AudioSegment`, `TranscriptionResponse`).

### 2. `gemini_processor.py`
- Uses `google-genai` (`genai.Client`).
- Uploads audio files via `client.files.upload()`.
- Exponential backoff retry logic for rate limits (`429`) and server errors (`503`).
- Invokes `client.models.generate_content` with structured output schema (`response_schema=TranscriptionResponse` and `response_mime_type="application/json"`).
- Automatically cleans up uploaded files from Gemini storage after processing.

### 3. `audio_slicer.py`
- Slices audio source using millisecond timestamps.
- Exports segments in MP3 or WAV format matching source audio format.
- Graceful error handling for timestamp bounds and formatting issues.

### 4. `process_dataset.py`
- Main CLI application with `argparse`.
- Supported arguments:
  - `--input_dir` (default: `input_audio`)
  - `--output_dir` (default: `output_dataset`)
  - `--dialects` (process specific or all 5 dialects)
  - `--model` (default: `gemini-2.5-flash`)
  - `--api_key` / env `GEMINI_API_KEY`
  - `--skip_existing` / `--overwrite`
  - `--dry_run` / `--no_slice`
- Progress tracking with `rich` / `tqdm` console status and structured logging.
- Generates `.txt` verbatim files alongside segment audio clips and writes/updates `<dialect>_metadata.jsonl`.

### 5. `test_pipeline.py`
- Synthetic audio test generator (pure tone WAV file).
- Mocked Gemini client tests for verification without consuming real API quota.
- End-to-end integration test support with live API key if provided.

## Verification Plan

### Automated Tests
- Run `test_pipeline.py` with mock responses to verify:
  - CLI argument parsing
  - Audio slicing and timestamp boundary validation
  - Output directory structure and JSONL schema formatting
  - Noise skipping behavior
  - Error and retry handling
- Run syntax/lint checks on all python scripts.

### Manual Verification
- Verify generated sample directories and manifest entries.
