# RajVaani System Architecture & Concurrency Model 🏛️⚙️

## 1. Overview

The **RajVaani** system is an enterprise-grade automated audio processing pipeline engineered in Python. It converts long-form raw audio recordings (ranging from 1 minute to 15+ minutes) into pristine, aligned, and structured Automatic Speech Recognition (ASR) corpora.

```mermaid
classDiagram
    class GeminiAudioProcessor {
        +Client client
        +str model_name
        +int max_retries
        +upload_file_with_retry(file_path)
        +process_audio(audio_path, dialect_key)
        +delete_remote_file(file_obj)
    }
    class AudioSlicer {
        +get_audio_duration(file_path)
        +slice_audio_segment(input_audio_path, output_audio_path, start_sec, end_sec, target_sample_rate)
    }
    class DatasetProcessor {
        +process_dialect_dataset(dialect, input_root, output_root, workers)
        +load_existing_manifest(path)
        +append_to_manifest(path, records)
        +calculate_sha256(file_path)
    }
    class ComplianceAuditor {
        +get_audio_info(file_path)
        +audit()
    }
    DatasetProcessor --> GeminiAudioProcessor : Invokes
    DatasetProcessor --> AudioSlicer : Invokes
    ComplianceAuditor ..> DatasetProcessor : Validates Output
```

---

## 2. Pipeline Architecture Stages

### Stage 1: File Ingestion & Probing
1. The orchestrator scans `input_audio/<dialect>/` for supported audio formats (`.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`).
2. Probes the container duration with microsecond precision using FFprobe / Python standard library `wave`.
3. Computes the cryptographic **SHA-256 digest** of the raw master recording for provenance tracking.

### Stage 2: Gemini Structured Inference
1. Uploads the audio file to the Google Gemini Files API (`client.files.upload()`) using safe ASCII temporary filenames.
2. Polls until the remote file state is `ACTIVE`.
3. Dispatches structured output generation via `client.models.generate_content()` with `response_schema=TranscriptionManifest` and temperature `0.1`.
4. Enforces dialect-specific phonetic guidelines, spoken numeral transcription, natural pause segmentation (5–20s), and speaker tracking.
5. Immediately executes remote file deletion (`client.files.delete()`) to prevent cloud storage leaks.

### Stage 3: Pre-Slice Temporal Gate
1. Receives the parsed Pydantic schema containing all segments.
2. Clamps timestamps to ensure:
   $$\text{clamped\_start} = \max(0.0, \text{start\_time})$$
   $$\text{clamped\_end} = \min(\text{source\_duration}, \text{end\_time})$$
   $$\text{duration} = \text{clamped\_end} - \text{clamped\_start}$$
3. Any segment with $\text{duration} < 0.3s$, $\text{clamped\_start} \ge \text{source\_duration}$, or flagged as `is_noise_or_music: true` is routed to the exclusions ledger.

### Stage 4: Lossless Slicing & Export
1. Fully decodes the source bitstream to uncompressed PCM audio before slicing.
2. Exports the segment as **16 kHz Mono PCM16 WAV**.
3. Writes the verbatim Devanagari text into an adjacent `.txt` file.
4. Computes the exported WAV SHA-256 hash.
5. Emits the structured JSON metadata record.

---

## 3. Multi-Threaded Concurrency Model

To process 892 files rapidly while respecting Gemini API rate limits, `process_dataset.py` implements a synchronized thread pool architecture:

```mermaid
sequenceDiagram
    autonumber
    actor CLI as Orchestrator CLI
    participant TP as ThreadPoolExecutor (Workers 1..N)
    participant LockC as Counter Lock (Mutex)
    participant Gemini as Google GenAI API
    participant Slicer as Audio Slicer (PCM16)
    participant LockW as Write Lock (Mutex)
    participant Manifest as JSONL Manifest

    CLI->>TP: Dispatch pending files
    par Worker Thread 1
        TP->>Gemini: Upload & Transcribe File A
        Gemini-->>TP: Return TranscriptionManifest
        TP->>LockC: Acquire Counter Lock
        LockC-->>TP: Reserve Segment IDs (0001..0015)
        TP->>LockC: Release Counter Lock
        TP->>Slicer: Slice 16kHz PCM16 WAVs & write .txt
        TP->>LockW: Acquire Write Lock
        LockW-->>TP: Append records atomically
        TP->>Manifest: Write to <dialect>_metadata.jsonl
        TP->>LockW: Release Write Lock
    and Worker Thread 2
        TP->>Gemini: Upload & Transcribe File B
        Gemini-->>TP: Return TranscriptionManifest
        TP->>LockC: Acquire Counter Lock
        LockC-->>TP: Reserve Segment IDs (0016..0032)
        TP->>LockC: Release Counter Lock
        TP->>Slicer: Slice 16kHz PCM16 WAVs & write .txt
        TP->>LockW: Acquire Write Lock
        LockW-->>TP: Append records atomically
        TP->>Manifest: Write to <dialect>_metadata.jsonl
        TP->>LockW: Release Write Lock
    end
```

### Concurrency Guarantees
- **No Race Conditions**: Segment ID counters and manifest appending operations are wrapped in dedicated `threading.Lock` critical sections.
- **Idempotency & Resumability**: If a run is interrupted, previously processed source files are skipped automatically via `skip_existing=True`.
- **Partitioning**: Slices are partitioned into `part_001/`, `part_002/`, etc. (1,000 files per directory) to prevent filesystem performance degradation.

---

## 4. Fallback Model Engine

The pipeline implements automated model fallback with exponential backoff:

```mermaid
flowchart TD
    Req["Audio Transcription Request"] --> M1["gemini-3.6-flash"]
    M1 -- "200 OK" --> Success["Parse Response"]
    M1 -- "429 Rate Limit" --> B1["Exponential Backoff (2^n + jitter)"] --> M1
    M1 -- "503 Unavailable / 404" --> M2["gemini-3.5-flash"]
    M2 -- "200 OK" --> Success
    M2 -- "503 / Fail" --> M3["gemini-3.7-flash"]
    M3 -- "200 OK" --> Success
    M3 -- "503 / Fail" --> M4["gemini-3.5-flash-lite"]
    M4 -- "200 OK" --> Success
    M4 -- "503 / Fail" --> M5["gemini-flash-latest"]
    M5 -- "200 OK" --> Success
```
