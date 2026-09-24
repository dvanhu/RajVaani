# RajVaani Dataset Specification & Linguistic Schema 📜🎙️

## 1. Supported Rajasthani Dialects

The corpus covers 6 distinct linguistic zones across Rajasthan:

| Dialect | Devanagari | Geographic Distribution | Phonetic & Grammatical Markers |
| :--- | :--- | :--- | :--- |
| **Bagri** | बागड़ी | Sri Ganganagar, Hanumangarh, Sirsa, Fazilka border | Heavy use of 'कोनी' (not), progressive 'करण लाग्यो', possessives 'म्हारो/थारो' |
| **Hadothi** | हाड़ौती | Kota, Bundi, Baran, Jhalawar | Distinctive 'छै' / 'छो' / 'छा' copula system, characteristic vowel contractions |
| **Mewati** | मेवाटी | Alwar, Bharatpur, Deeg, Kotkasim, Mewat/Nuh | 'सै'/'है'/'हूंतो' copula, 'कू'/'तै'/'मैं' postpositions, 'गयो'/'हतो' past tense |
| **Marwari** | मारवाड़ी | Jodhpur, Barmer, Jaisalmer, Nagaur, Bikaner, Pali | 'है'/'हो'/'हूँ' verb systems, interrogative 'कांई' (what), 'किण' (whom) |
| **Dhundhari** | ढूँढाड़ी | Jaipur, Dausa, Tonk, Sawai Madhopur | 'छै'/'छा' auxiliary verbs, directional adverbs 'अठै'/'वठै' |
| **Mewari** | मेवाड़ी | Udaipur, Chittorgarh, Rajsamand, Bhilwara | 'वै'/'हो' verb system, past markers 'ग्यो'/'कियो', phonological diphthong shifts |

---

## 2. Directory Hierarchy

```
output_dataset/
├── <dialect_name>/                      # e.g., bagri, hadothi, mewati, marwari, dhundhari, mewari
│   ├── part_001/                        # Partition 1 (segments 1 to 1,000)
│   │   ├── segment_0001.wav             # 16 kHz Mono PCM16 WAV audio clip
│   │   ├── segment_0001.txt             # Verbatim Devanagari transcript
│   │   ├── segment_0002.wav
│   │   └── segment_0002.txt
│   ├── part_002/                        # Partition 2 (segments 1,001 to 2,000)
│   ├── ...
│   ├── <dialect_name>_metadata.jsonl    # Clean training pairs with SHA-256 hashes
│   └── <dialect_name>_exclusions.jsonl  # Segregated non-speech / noise / hymn entries
```

---

## 3. Metadata Manifest Schema (`<dialect>_metadata.jsonl`)

Each line is an atomic, self-contained JSON record:

```json
{
  "segment_id": "segment_0001",
  "source_file": "B01___01_Matthew_____BGQWINN1DA.mp3",
  "source_sha256": "4e74971c26b488730b65fa316d2dbce90786cfba95697666d95368a8677c77c6",
  "dialect": "bagri",
  "audio_file": "part_001/segment_0001.wav",
  "exported_audio_sha256": "8f31b20a44e59174092b3b778749a2cf247ee06e40938bfe4e92a2a7aa341bdc",
  "text_file": "part_001/segment_0001.txt",
  "start_time_seconds": 12.450,
  "end_time_seconds": 21.320,
  "duration_seconds": 8.870,
  "speaker_id": "spk_bagri_B01_01_Matthew_01",
  "verbatim_devanagari": "यीशु मसीह रो वंशावली जो दाऊद रो बेटो अर इब्राहीम रो बेटो है",
  "audio_format": "16kHz_mono_pcm16_wav",
  "is_noise_or_music": false,
  "confidence_score": 0.98,
  "notes": null,
  "human_verification_status": "ai_draft_structurally_verified",
  "reviewer_id": "RAJVAANI_AUTOMATED_QA_GATE",
  "review_date": "2026-09-24"
}
```

### Field Definitions

| Field | Type | Description |
| :--- | :--- | :--- |
| `segment_id` | `string` | Unique global identifier (e.g. `segment_0001`) within the dialect. |
| `source_file` | `string` | Filename of the master raw audio input file. |
| `source_sha256` | `string` | Cryptographic SHA-256 hash of the master input audio file. |
| `dialect` | `string` | Dialect identifier key (`bagri`, `hadothi`, `mewati`, `marwari`, `dhundhari`, `mewari`). |
| `audio_file` | `string` | Relative path to the sliced 16 kHz WAV file (`part_XXX/segment_YYYY.wav`). |
| `exported_audio_sha256` | `string` | Cryptographic SHA-256 hash of the exported WAV clip. |
| `text_file` | `string` | Relative path to the transcript text file (`part_XXX/segment_YYYY.txt`). |
| `start_time_seconds` | `float` | Start timestamp in seconds with millisecond precision. |
| `end_time_seconds` | `float` | End timestamp in seconds with millisecond precision. |
| `duration_seconds` | `float` | Exact duration of the audio clip in seconds. |
| `speaker_id` | `string` | Scoped speaker tag ensuring uniqueness (`spk_<dialect>_<stem>_<id>`). |
| `verbatim_devanagari` | `string` | Strict phonetic Devanagari transcript (zero Hindi normalization). |
| `audio_format` | `string` | Standardized to `16kHz_mono_pcm16_wav`. |
| `is_noise_or_music` | `boolean` | Always `false` in metadata.jsonl. |
| `confidence_score` | `float` | Gemini confidence rating (0.00 to 1.00). |

---

## 4. Exclusions Ledger Schema (`<dialect>_exclusions.jsonl`)

Segments that contain pure intro music, singing, hymns, or unresolvable noise are preserved in the exclusions ledger for audit traceability:

```json
{
  "segment_id": "segment_0003",
  "source_file": "B01___01_Matthew_____BGQWINN1DA.mp3",
  "source_sha256": "4e74971c26b488730b65fa316d2dbce90786cfba95697666d95368a8677c77c6",
  "dialect": "bagri",
  "start_time_seconds": 0.0,
  "end_time_seconds": 12.450,
  "duration_seconds": 12.450,
  "speaker_id": "spk_bagri_B01_01_Matthew_music",
  "verbatim_devanagari": "",
  "exclusion_reason": "Introductory musical instrumental fanfare",
  "is_noise_or_music": true,
  "confidence_score": 0.0
}
```

---

## 5. Audio Acoustic Specifications

| Parameter | Specification | Verification Constraint |
| :--- | :--- | :--- |
| **Container & Codec** | RIFF WAV (PCM signed 16-bit little-endian) | Must be decodable via standard PCM readers |
| **Sampling Rate** | 16,000 Hz (16 kHz) | Exactly 16,000 samples per second |
| **Channel Count** | 1 (Mono) | Channel layout: single mono stream |
| **Energy Gate** | Root-Mean-Square (RMS) &gt; -55.0 dBFS | Rejects silent or muted audio stubs |
| **Segment Length** | 3.0s to 30.0s (Nominal: 5.0s–20.0s) | Rejects clips &lt; 0.3s or overlength monologue spans |
