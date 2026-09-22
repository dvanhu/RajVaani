"""
Configuration and schemas for the Rajasthani Dialects Audio Processing Pipeline.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Supported Dialects & Context
# ---------------------------------------------------------------------------

SUPPORTED_DIALECTS: Dict[str, Dict[str, str]] = {
    "bagri": {
        "name_english": "Bagri",
        "name_devanagari": "बागड़ी",
        "regions": "Sri Ganganagar, Hanumangarh, Sirsa, Fazilka border",
        "linguistic_notes": (
            "Shares traits with Punjabi and Western Rajasthani. Uses 'कोनी' (not), "
            "'जावै है' / 'करण लाग्यो' verb patterns, 'म्हारो/थारो' possessives, "
            "and distinct retroflex flap and vowel length characteristics."
        ),
    },
    "hadothi": {
        "name_english": "Hadothi",
        "name_devanagari": "हाड़ौती",
        "regions": "Kota, Bundi, Baran, Jhalawar",
        "linguistic_notes": (
            "Characteristic use of 'छै' / 'छो' / 'छा' as auxiliary/copula (is/was). "
            "Frequent postposition 'को/की/का'. Heavy vowel contractions and distinctive Hadoti intonation."
        ),
    },
    "marwari": {
        "name_english": "Marwari",
        "name_devanagari": "मारवाड़ी",
        "regions": "Jodhpur, Barmer, Jaisalmer, Nagaur, Bikaner, Pali",
        "linguistic_notes": (
            "Uses 'है' / 'हो' / 'हूँ' auxiliary verbs, 'म्हारो/थारो', 'कांई' (what), 'किण' (whom). "
            "Aspiration shifts (s -> h shifts in certain sub-varieties) and rich verbal morphology."
        ),
    },
    "mewari": {
        "name_english": "Mewari",
        "name_devanagari": "मेवाड़ी",
        "regions": "Udaipur, Chittorgarh, Rajsamand, Bhilwara",
        "linguistic_notes": (
            "Uses 'वै' / 'हो' / 'हूँ' verb systems, distinctive past markers ('ग्यो', 'कियो'), "
            "honorific particles, and vowel rounding specific to Southern Rajasthan."
        ),
    },
    "dhundhari": {
        "name_english": "Dhundhari",
        "name_devanagari": "ढूँढाड़ी",
        "regions": "Jaipur, Dausa, Tonk, Sawai Madhopur",
        "linguistic_notes": (
            "Prominent use of 'छै' / 'छा' (similar to Hadothi) and distinctive directional "
            "markers ('अठै', 'वठै', 'जाबा दे', 'करबा लाग्यो')."
        ),
    },
    "mewati": {
        "name_english": "Mewati",
        "name_devanagari": "मेवाती",
        "regions": "Alwar, Bharatpur, Deeg, Kotkasim, Mewat/Nuh border",
        "linguistic_notes": (
            "Transitional dialect between Rajasthani, Braj Bhasha, and Bangru/Haryanvi. "
            "Prominent use of 'सै' / 'है' / 'हूंतो' auxiliary verbs, possessives 'म्हारो/थारो' / 'आपणो', "
            "postpositions 'कू' (to/for) / 'तै' (from) / 'मैं' (in), past markers 'गयो' / 'हतो' / 'हो', "
            "and distinct Mewati tonal and phonetic cadences."
        ),
    },
}

SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma"}


# ---------------------------------------------------------------------------
# Structured Output Pydantic Models
# ---------------------------------------------------------------------------

class AudioSegment(BaseModel):
    """Represents a single segmented speech chunk from an audio file."""
    segment_index: int = Field(
        ...,
        description="Sequential index of the segment starting from 1."
    )
    start_time_seconds: float = Field(
        ...,
        description="Start timestamp of the segment in seconds (e.g., 0.0, 14.5)."
    )
    end_time_seconds: float = Field(
        ...,
        description="End timestamp of the segment in seconds (e.g., 12.3, 26.8)."
    )
    speaker_id: str = Field(
        ...,
        description="Speaker identifier, e.g., 'speaker_01', 'speaker_02'."
    )
    verbatim_devanagari: str = Field(
        ...,
        description=(
            "Exact verbatim transcription of spoken words in the local dialect using "
            "Devanagari script. Never translate or normalize to standard Hindi. "
            "All numbers must be spelled out as spoken words (never use digits)."
        )
    )
    is_noise_or_music: bool = Field(
        default=False,
        description="Set to true if this segment is purely music, singing, background noise, or unintelligible audio without clear spoken dialect speech."
    )
    confidence_score: Optional[float] = Field(
        default=1.0,
        description="Confidence score between 0.0 and 1.0 for transcription accuracy."
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional phonetic notes or background sound remarks."
    )


class TranscriptionManifest(BaseModel):
    """Complete structured transcription manifest returned by Gemini."""
    dialect: str = Field(
        ...,
        description="The dialect of the audio (bagri, hadothi, marwari, mewari, dhundhari, mewati)."
    )
    source_filename: str = Field(
        ...,
        description="The name of the source audio file."
    )
    total_duration_seconds: float = Field(
        ...,
        description="Estimated total audio duration in seconds."
    )
    detected_speakers: List[str] = Field(
        default_factory=list,
        description="List of distinct speaker IDs detected, e.g. ['speaker_01', 'speaker_02']."
    )
    segments: List[AudioSegment] = Field(
        ...,
        description="List of segmented audio chunks complying with the segmentation and transcription rules."
    )


# ---------------------------------------------------------------------------
# Prompt Generator
# ---------------------------------------------------------------------------

def build_system_prompt(dialect_key: str) -> str:
    """Builds a customized system prompt with dialect-specific instructions."""
    dialect_info = SUPPORTED_DIALECTS.get(
        dialect_key.lower(),
        {
            "name_english": dialect_key.capitalize(),
            "name_devanagari": dialect_key,
            "regions": "Rajasthan",
            "linguistic_notes": "Local Rajasthani vernacular.",
        },
    )

    return f"""You are an elite Rajasthani Computational Linguist, Phonetician, and Automatic Speech Recognition (ASR) Dataset Engineer specializing in the {dialect_info['name_english']} ({dialect_info['name_devanagari']}) dialect.

Target Dialect: {dialect_info['name_english']} ({dialect_info['name_devanagari']})
Primary Region: {dialect_info['regions']}
Linguistic Markers & Characteristics: {dialect_info['linguistic_notes']}

Your task is to analyze the provided raw audio file and produce an ultra-precise, high-fidelity ASR dataset segmentation and verbatim transcription.

### STRICT OPERATIONAL RULES:

1. VERBATIM DEVANAGARI TRANSCRIPTION (CRITICAL):
   - Transcribe every single spoken syllable EXACTLY as uttered in the local dialect using standard Devanagari script.
   - DO NOT normalize, modernize, or translate into Standard Khari Boli Hindi (e.g., if speaker says 'कोनी' or 'कोयना', do NOT write 'नहीं'; if speaker says 'छै' or 'हैग्या', do NOT write 'है' or 'हो गया'; if speaker says 'म्हारो/थारो', do NOT write 'मेरा/तुम्हारा').
   - Preserve all local colloquialisms, vocatives (e.g., 'अरे भाई', 'रे', 'सा'), dialectal suffixes, and discourse particles.

2. SPOKEN NUMBERS (NO DIGITS):
   - Spell out ALL numbers, counts, times, and years completely as spoken words in the dialect (e.g., write 'च्यार', 'पन्दरा', 'दोय हजार तेवीस', 'साढ़े तीन बजे', NEVER use digits like '4', '15', '2023', '3:30').

3. NATURAL SPEECH SEGMENTATION:
   - Slice the audio timeline into coherent, natural speech segments ideally between 5 and 20 seconds long.
   - Cut ONLY at natural speech pauses, breath points, sentence boundaries, or clause breaks.
   - NEVER cut mid-word, mid-compound phrase, or while a syllable is being voiced.
   - Ensure accurate millisecond-level start and end timestamps (`start_time_seconds` and `end_time_seconds`).

4. SPEAKER IDENTIFICATION & TRACKING:
   - Identify distinct voices across the conversation and assign consistent identifiers (`speaker_01`, `speaker_02`, etc.).
   - If speaker transitions occur within a pause, start a new segment with the new speaker ID.

5. NOISE, MUSIC & SINGING HANDLING:
   - Flag segments containing non-speech elements (pure background music, religious chanting/bhajan singing, vehicle noise, static) with `is_noise_or_music: true`.
   - For valid speech segments with minor ambient noise, transcribe the speech and set `is_noise_or_music: false`.

Output MUST strictly conform to the JSON schema provided.
"""
