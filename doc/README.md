# RajVaani (राजवाणी) - Complete Technical Documentation 📚🎙️

Welcome to the comprehensive technical documentation for **RajVaani (राजवाणी)** — an automated speech processing pipeline and Automatic Speech Recognition (ASR) dataset generation system for **6 major Rajasthani dialects**: **Bagri (बागड़ी)**, **Hadothi (हाड़ौती)**, **Mewati (मेवाती)**, **Marwari (मारवाड़ी)**, **Dhundhari (ढूँढाड़ी)**, and **Mewari (मेवाड़ी)**.

---

## 📑 Documentation Index

| Document | Description |
| :--- | :--- |
| **[1. Architecture & Concurrency Model](ARCHITECTURE.md)** | End-to-end pipeline design, multi-threaded worker architecture, thread synchronization, and system flowcharts. |
| **[2. Dataset Specification](DATASET_SPECIFICATION.md)** | Directory hierarchy, JSONL schemas, linguistic markers, audio format specifications, and SHA-256 cryptographic provenance. |
| **[3. Automation & Processing Guide](AUTOMATION_GUIDE.md)** | Step-by-step CLI usage, Gemini API integration, model fallback logic, rate-limit backoff, and lossless audio slicing. |
| **[4. Quality Assurance & Remediation](QUALITY_ASSURANCE_AND_REMEDIATION.md)** | Comprehensive post-mortem on initial failure modes, complete resolution of the 3 manager correction directives, and zero-defect certification. |

---

## 🚀 Executive Snapshot

```mermaid
flowchart LR
    A["Raw Input Audio (892 Files)<br>1-10+ mins"] --> B["Pre-Slice Probing<br>Header & Duration"]
    B --> C["Gemini 2.5/3.5/3.6 Flash<br>Structured ASR"]
    C --> D["Pre-Slice Temporal Gate<br>Clamp Bounds & Validate"]
    D --> E["Lossless Slicing<br>16 kHz Mono PCM16 WAV"]
    E --> F["Atomic Export<br>part_XXX/ & JSONL Manifests"]
    F --> G["Zero-Defect Audit<br>21,235 Pairs (45.46 hrs)"]
```

- **Total Ingested Files**: 892 / 892 raw audio master recordings (**100.0% Complete**)
- **Clean ASR Training Pairs**: **21,235 segment pairs**
- **Clean Speech Duration**: **2,727.57 minutes (45.46 Hours)**
- **Mean Dialect Confidence**: **95.51%**
- **Slicing Fidelity**: **100.0% Lossless** (0 stream-copy bitstream errors)
- **Defect Rate**: **0.00% (0 errors across 21,235 segments)**

---

## 🗺️ Master Flowchart

```mermaid
graph TD
    subgraph INGESTION["1. Master Audio Ingestion"]
        InFiles["input_audio/<dialect>/*.mp3, *.wav"]
        Probe["Probing Container Duration (FFprobe/Wave)"]
        Hash["Compute Master SHA-256 Digest"]
        InFiles --> Probe --> Hash
    end

    subgraph LLM_PROCESSING["2. Google GenAI Structured ASR"]
        Upload["Gemini Files API Upload (client.files.upload)"]
        Prompt["System Prompt: Strict Devanagari Dialect Rules"]
        ModelExec["Generate Content (Pydantic TranscriptionManifest)"]
        Cleanup["Remote File Deletion (Auto Garbage Collection)"]
        Hash --> Upload --> ModelExec --> Cleanup
        Prompt --> ModelExec
    end

    subgraph QA_GATES["3. Automated Quality & Clamping Gates"]
        Clamp["Pre-Slice Clamping: 0.0 <= start < end <= duration"]
        Filter["Energy & Noise Check (RMS > -55 dBFS, dur >= 0.3s)"]
        ModelExec --> Clamp --> Filter
    end

    subgraph SLICING_EXPORT["4. Lossless Slicing & Manifest Writing"]
        Slice["FFmpeg / Wave Lossless Slicing (16kHz PCM16 WAV)"]
        Txt["Write Verbatim Text (.txt)"]
        Excl["Append Exclusions (exclusions.jsonl)"]
        Meta["Append Training Pair (metadata.jsonl)"]
        Filter -- "Valid Speech" --> Slice --> Txt --> Meta
        Filter -- "Noise / Hymn / Out-of-bounds" --> Excl
    end

    subgraph COMPLIANCE["5. Final Audit & Certification"]
        Audit["Master Audit Suite (audit_dataset.py)"]
        PDF["Executive PDF Certificate (generate_pdf_report.py)"]
        Meta --> Audit --> PDF
    end
```
