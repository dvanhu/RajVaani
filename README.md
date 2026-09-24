# RajVaani (राजवाणी) 🎙️🇮🇳
### Automated Rajasthani Dialects Audio Dataset Processing Pipeline & ASR Corpus

[![Quality Certification](https://img.shields.io/badge/Quality_Audit-100%25_Zero_Defects-success.svg)](#-master-dataset-summary)
[![Corpus Scale](https://img.shields.io/badge/Corpus_Yield-21%2C235_Pairs_(45.46_hrs)-blue.svg)](#-master-dataset-summary)
[![SDK](https://img.shields.io/badge/Powered_by-Google_GenAI_SDK-purple.svg)](#-core-features--gemini-enforcement)
[![Python](https://img.shields.io/badge/Python-3.10_|_3.11_|_3.12_|_3.13-blue.svg)](#-getting-started)

An end-to-end automated speech engineering pipeline powered by the **Google GenAI SDK** and **Gemini Flash models** to process, segment, transcribe, and structure multi-dialect Rajasthani audio corpora into pristine ASR training datasets.

---

## 🌟 Supported Dialects

| Dialect | Devanagari | Primary Geographic Regions | Key Linguistic Markers |
|---|---|---|---|
| **Bagri** | बागड़ी | Sri Ganganagar, Hanumangarh, Sirsa, Fazilka border | Heavy use of 'कोनी' (not), progressive 'करण लाग्यो', 'म्हारो/थारो' |
| **Hadothi** | हाड़ौती | Kota, Bundi, Baran, Jhalawar | Distinctive 'छै' / 'छो' / 'छा' copula system, vowel contractions |
| **Mewati** | मेवाटी | Alwar, Bharatpur, Deeg, Kotkasim, Mewat/Nuh border | 'सै'/'है'/'हूंतो' copula, 'कू'/'तै'/'मैं' postpositions, 'गयो'/'हतो' |
| **Marwari** | मारवाड़ी | Jodhpur, Barmer, Jaisalmer, Nagaur, Bikaner, Pali | 'है'/'हो'/'हूँ' verb systems, 'कांई' (what), 'किण' (whom) |
| **Dhundhari** | ढूँढाड़ी | Jaipur, Dausa, Tonk, Sawai Madhopur | 'छै'/'छा' auxiliary, 'अठै'/'वठै' directional markers |
| **Mewari** | मेवाड़ी | Udaipur, Chittorgarh, Rajsamand, Bhilwara | 'वै'/'हो' verb systems, 'ग्यो'/'कियो' past markers |

---

## 📊 Master Dataset Summary (100% Complete)

```text
================================================================================
               6-DIALECT MASTER ACCURACY & CONFIDENCE MATRIX                    
================================================================================

Bagri (बागड़ी)         :  96.54%   ████████████████████████████░░   (9,275 pairs)
Dhundhari (ढूँढाड़ी)   :  95.39%   ████████████████████████████░░   (1,171 pairs)
Mewati (मेवाती)        :  95.23%   ████████████████████████████░░   (2,148 pairs)
Hadothi (हाड़ौती)      :  94.51%   ████████████████████████████░░   (6,730 pairs)
Marwari (मारवाड़ी)     :  94.38%   ████████████████████████████░░   (1,802 pairs)
Mewari (मेवाड़ी)       :  94.23%   ████████████████████████████░░   (  109 pairs)

Overall Mean Confidence : 95.51% (Zero conversion to standard Hindi, pure verbatim dialect)
Lossless Slicing Rate  : 100.0% (FFmpeg millisecond precision cuts)
Total Clean Speech     : 2,727.57 minutes (45.46 Hours) across 21,235 segment pairs
Zero-Defect Audit Rate : 100.0% Passed (0 Errors)
================================================================================
```

---

## 📁 Dataset Directory Structure

```
RajVaani/
├── doc/                                 # Comprehensive documentation suite
│   ├── ARCHITECTURE.md                  # System design, multi-threading & flowcharts
│   ├── DATASET_SPECIFICATION.md         # JSON schemas, dialect phonetics & audio specs
│   ├── AUTOMATION_GUIDE.md              # CLI guide, supervisor scripts & execution steps
│   └── QUALITY_ASSURANCE_AND_REMEDIATION.md # Root cause audit & 3 directives resolution
│
├── input_audio/                         # Raw dialect audio master recordings (892 files)
│   ├── bagri/ (261 files)
│   ├── hadothi/ (261 files)
│   ├── mewati/ (232 files)
│   ├── marwari/ (80 files)
│   ├── dhundhari/ (51 files)
│   └── mewari/ (7 files)
│
├── output_dataset/                      # Structured final ASR corpus (21,235 verified pairs)
│   ├── bagri/
│   │   ├── part_001/ ... part_010/      # Partitioned 16 kHz WAV clips and .txt transcripts
│   │   ├── bagri_metadata.jsonl         # 9,275 active training records with SHA-256 provenance
│   │   └── bagri_exclusions.jsonl       # 993 segregated non-speech / music entries
│   ├── hadothi/ (6,730 pairs)
│   ├── mewati/ (2,148 pairs)
│   ├── marwari/ (1,802 pairs)
│   ├── dhundhari/ (1,171 pairs)
│   └── mewari/ (109 pairs)
│
├── config.py                            # Dialect profiles, prompts & Pydantic schemas
├── audio_slicer.py                      # Sub-millisecond PCM16 WAV audio slicing module
├── gemini_processor.py                  # Google GenAI SDK client, fallback & auto-cleanup
├── process_dataset.py                   # Multi-threaded parallel processing orchestrator
├── remediate_4_dialects.py              # Zero-defect quality remediation engine
├── audit_dataset.py                     # 6-dialect compliance inspection & verification
├── accuracy_report.py                   # Confidence matrix and statistics visualizer
├── generate_pdf_report.py               # Executive PDF management report generator
├── old_to_new_mapping.json              # Legacy-to-new segment traceability catalog
└── RajVaani_Executive_Management_Report.pdf # Official executive PDF delivery document
```

---

## ⚙️ Key Technical Pillars & Zero-Defect Architecture

1. **Lossless PCM16 WAV Slicing (Resolution of Directive 1)**:
   - Full stream decoding to uncompressed PCM waveforms before boundary cutting.
   - 100% of exported audio clips standardized to **16 kHz Mono PCM16 WAV** format.
   - Eliminates all bitstream MPEG frame-copy corruption and silent stubs.

2. **Pre-Slice Temporal Clamping & LLM Bounds Gate (Resolution of Directive 2)**:
   - Pre-probes master recording duration with microsecond precision.
   - Enforces $0.0 \le \text{start} < \text{end} \le \text{source\_duration}$, permanently eliminating hallucinated timestamps beyond master EOF.

3. **Spoken Dialect Numerals & Dual-Ledger Isolation (Resolution of Directive 3)**:
   - All numbers, times, and years transcribed purely into phonetic dialect words in Devanagari (0 raw digits).
   - Non-speech audio, hymns, and intro music cleanly isolated into `<dialect>_exclusions.jsonl`.

4. **Multi-Threaded High-Throughput Ingestion**:
   - Parallel worker pool (`ThreadPoolExecutor`) with mutex locks for thread-safe atomic manifest writes and segment ID reservation.
   - Dynamic model fallbacks (`gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.7-flash`, `gemini-3.5-flash-lite`) with exponential backoff.

5. **Cryptographic SHA-256 Provenance**:
   - Master raw inputs and exported WAV clips are cataloged with immutable SHA-256 hashes.

---

## 🚀 Getting Started

### 1. Installation
```bash
git clone https://github.com/dvanhu/RajVaani.git
cd RajVaani
pip install -r requirements.txt
```

### 2. Environment Configuration
Create a `.env` file:
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.6-flash
```

### 3. Pipeline Execution
```bash
# Process all 6 dialects in parallel with 5 worker threads
python process_dataset.py --dialects all --workers 5

# Run complete zero-defect audit
python audit_dataset.py

# Print live accuracy and confidence matrix
python accuracy_report.py

# Compile official executive PDF management report
python generate_pdf_report.py
```

---

## 📖 In-Depth Documentation

For complete technical specifications, flowcharts, schemas, and remediation reports, visit the **[`doc/`](doc/README.md)** directory:
- [System Architecture & Concurrency](doc/ARCHITECTURE.md)
- [Dataset Specification & Schema](doc/DATASET_SPECIFICATION.md)
- [Automation Guide & CLI Reference](doc/AUTOMATION_GUIDE.md)
- [Quality Assurance & Remediation](doc/QUALITY_ASSURANCE_AND_REMEDIATION.md)

---

## 📄 License & Certification

Developed by the **RajVaani Engineering Team**. Certified for ASR training and dialect speech modeling.
