# RajVaani Automation & Pipeline Execution Guide 🚀💻

## 1. Prerequisites & Setup

### Environment Variables
Create a `.env` file in the project root:
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.6-flash
```

### Installation
```bash
# Clone the repository
git clone https://github.com/dvanhu/RajVaani.git
cd RajVaani

# Install Python dependencies
pip install -r requirements.txt
```

---

## 2. CLI Execution & Orchestrator

The main orchestrator script is `process_dataset.py`.

```bash
# Process all 6 dialects in parallel with 5 worker threads
python process_dataset.py --dialects all --workers 5

# Process specific dialects (e.g. Hadothi and Bagri)
python process_dataset.py --dialects hadothi bagri --workers 6

# Dry-run / Transcribe without slicing audio
python process_dataset.py --dialects marwari --no_slice

# Initialize folder structures without processing
python process_dataset.py --init_dirs
```

### CLI Options Reference

| Option | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--input_dir` | `str` | `input_audio` | Path containing raw dialect audio folders. |
| `--output_dir` | `str` | `output_dataset` | Target root path for structured output dataset. |
| `--dialects` | `list` | `all` | Specific dialect names or `all`. |
| `--model` | `str` | `gemini-3.6-flash` | Gemini model for ASR segmentation. |
| `--workers` | `int` | `5` | Number of parallel worker threads. |
| `--skip_existing` | `bool` | `True` | Automatically skip previously processed files. |
| `--overwrite` | `flag` | `False` | Force re-processing and overwrite existing files. |
| `--no_slice` | `flag` | `False` | Disable audio slicing (metadata only). |
| `--max_files` | `int` | `None` | Process up to N files per dialect (for sampling). |

---

## 3. Automated Supervisor & Zero-Defect Runner

For unattended, end-to-end execution, use `auto_supervisor.py`:

```bash
python auto_supervisor.py
```

### Supervisor Execution Phases
1. **Dialect Batch Processing**: Monitors active processing tasks until all raw files are ingested.
2. **Master Remediation**: Executes `remediate_4_dialects.py` to fix formatting and synchronize durations.
3. **Comprehensive Audit**: Runs `audit_dataset.py` across all 21,235 segments.
4. **PDF Certification**: Compiles the executive management PDF report via `generate_pdf_report.py`.

---

## 4. Quality Audit & Compliance Verification

Run the standalone audit suite at any time:

```bash
# Run 6-dialect compliance audit
python audit_dataset.py

# Print accuracy and confidence matrix
python accuracy_report.py

# Generate executive PDF certification report
python generate_pdf_report.py
```

---

## 5. Automated Test Suite

Run the unit and mock testing pipeline:

```bash
python test_pipeline.py
```

### Test Coverage
- Pure tone synthetic WAV generation and boundary validation
- Mock Gemini client response simulation (no API quota consumed)
- Output JSONL schema conformity
- Noise isolation and error recovery
