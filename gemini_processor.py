"""
Gemini API client and audio transcription processor using the official google-genai SDK.
Features automatic model fallbacks, retry mechanisms, structured schema enforcement, and file cleanup.
"""

import os
import time
import json
import uuid
import shutil
import logging
import random
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

from config import (
    TranscriptionManifest,
    build_system_prompt,
    SUPPORTED_DIALECTS,
)

logger = logging.getLogger("RajVaani.GeminiProcessor")

FALLBACK_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
]


class GeminiAudioProcessor:
    """
    Handles file uploading to Gemini Files API, structured output generation,
    retry mechanisms with model fallback, safe Unicode filename handling, and automatic file cleanup.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        max_retries: int = 4,
        retry_delay_base: float = 2.0,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model_name = model_name or os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
        self.max_retries = max_retries
        self.retry_delay_base = retry_delay_base
        self.client = None

        if not self.api_key:
            logger.warning(
                "No Gemini API key provided. Set GEMINI_API_KEY in .env "
                "or pass --api_key to enable live API processing."
            )
        else:
            self._init_client()

    def _init_client(self):
        """Initializes the google-genai Client."""
        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
            logger.info(f"Initialized Gemini Client (Default model: {self.model_name})")
        except ImportError:
            raise ImportError(
                "The 'google-genai' package is required. Install it using: pip install google-genai"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Gemini Client: {e}")
            raise

    def _get_safe_upload_path(self, file_path: Path) -> Tuple[Path, Optional[Path]]:
        """
        Ensures the file has a clean, safe ASCII filename before uploading to Gemini Files API.
        If the filename has non-ASCII characters, spaces, or special characters, copies to a temporary ASCII file.
        Returns: (upload_path, temp_file_to_cleanup)
        """
        original_name = file_path.name
        try:
            original_name.encode("ascii")
            is_pure_ascii = True
        except UnicodeEncodeError:
            is_pure_ascii = False

        has_special_chars = any(c in original_name for c in " '\"()[]{}*?#&$!@+~`^=;,")

        if not is_pure_ascii or has_special_chars:
            ext = file_path.suffix.lower() or ".mp3"
            safe_filename = f"rajvaani_{uuid.uuid4().hex[:12]}{ext}"
            temp_dir = Path(tempfile.gettempdir())
            temp_path = temp_dir / safe_filename
            shutil.copy2(file_path, temp_path)
            logger.debug(
                f"Created sanitized ASCII temporary copy for upload: '{file_path.name}' -> '{temp_path.name}'"
            )
            return temp_path, temp_path

        return file_path, None

    def upload_file_with_retry(self, file_path: str):
        """
        Uploads audio file using Gemini Files API with exponential backoff retry.
        Safely handles non-ASCII and special character filenames.
        Waits for file to become ACTIVE.
        """
        if not self.client:
            raise RuntimeError("Gemini Client is not initialized (missing API key).")

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        upload_target, temp_cleanup_path = self._get_safe_upload_path(path)

        try:
            retries = 0
            while retries < self.max_retries:
                try:
                    logger.info(f"Uploading '{path.name}' to Gemini Files API...")
                    uploaded_file = self.client.files.upload(file=str(upload_target))

                    # Check file state
                    while uploaded_file.state.name == "PROCESSING":
                        logger.debug(f"File '{path.name}' is processing in Gemini Files API. Waiting 2s...")
                        time.sleep(2)
                        uploaded_file = self.client.files.get(name=uploaded_file.name)

                    if uploaded_file.state.name == "FAILED":
                        raise RuntimeError(f"Gemini file processing failed: {uploaded_file.error}")

                    logger.info(f"File '{path.name}' uploaded successfully (URI: {uploaded_file.uri}).")
                    return uploaded_file

                except Exception as e:
                    retries += 1
                    if retries >= self.max_retries:
                        logger.error(
                            f"Exceeded max upload retries ({self.max_retries}) for '{path.name}'. Error: {e}"
                        )
                        raise

                    delay = (self.retry_delay_base ** retries) + random.uniform(0.5, 1.5)
                    logger.warning(
                        f"Upload attempt {retries} failed for '{path.name}' ({e}). Retrying in {delay:.2f}s..."
                    )
                    time.sleep(delay)
        finally:
            if temp_cleanup_path and temp_cleanup_path.exists():
                try:
                    temp_cleanup_path.unlink()
                except Exception as cleanup_err:
                    logger.debug(f"Could not remove temp file {temp_cleanup_path}: {cleanup_err}")

    def delete_remote_file(self, file_name_or_obj):
        """Deletes uploaded file from Gemini storage to avoid resource leaks."""
        if not self.client or not file_name_or_obj:
            return

        try:
            name = getattr(file_name_or_obj, "name", str(file_name_or_obj))
            self.client.files.delete(name=name)
            logger.debug(f"Deleted remote Gemini file: {name}")
        except Exception as e:
            logger.warning(f"Could not delete remote file {file_name_or_obj}: {e}")

    def process_audio(
        self,
        audio_path: str,
        dialect_key: str,
    ) -> TranscriptionManifest:
        """
        Full workflow: Upload audio, invoke Gemini with structured schema,
        parse result into TranscriptionManifest, and clean up the uploaded file.
        Includes automatic fallback across available Gemini models if high demand (503) occurs.
        """
        if not self.client:
            raise RuntimeError("Gemini Client not initialized. Please set GEMINI_API_KEY in .env.")

        from google.genai import types

        path = Path(audio_path)
        dialect_info = SUPPORTED_DIALECTS.get(dialect_key.lower(), {})
        dialect_name = dialect_info.get("name_english", dialect_key.capitalize())

        system_prompt = build_system_prompt(dialect_key)
        uploaded_file = None

        # Build prioritized model list starting with selected model
        models_to_try: List[str] = [self.model_name]
        for fallback in FALLBACK_MODELS:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        try:
            # 1. Upload audio file (with safe filename handling)
            uploaded_file = self.upload_file_with_retry(str(path))

            # 2. Call generate_content with retries and fallback models
            prompt_text = (
                f"Perform high-precision ASR segmentation and verbatim transcription for this {dialect_name} "
                f"audio recording ({path.name}). Adhere strictly to the verbatim Devanagari dialect rules, "
                f"number spelling, natural speech chunking, speaker tracking, and noise flags."
            )

            last_error = None

            for current_model in models_to_try:
                retries = 0
                max_retries_for_model = 2 if len(models_to_try) > 1 else self.max_retries

                while retries < max_retries_for_model:
                    try:
                        logger.info(
                            f"Requesting structured transcription for '{path.name}' using {current_model}..."
                        )

                        response = self.client.models.generate_content(
                            model=current_model,
                            contents=[
                                uploaded_file,
                                prompt_text,
                            ],
                            config=types.GenerateContentConfig(
                                system_instruction=system_prompt,
                                response_mime_type="application/json",
                                response_schema=TranscriptionManifest,
                                temperature=0.1,
                            ),
                        )

                        # 3. Parse JSON / Pydantic response
                        if not response.text:
                            raise ValueError("Gemini returned an empty response text.")

                        manifest_dict = json.loads(response.text)
                        manifest = TranscriptionManifest(**manifest_dict)

                        # Ensure dialect and source filename match
                        manifest.dialect = dialect_key.lower()
                        manifest.source_filename = path.name

                        logger.info(
                            f"Successfully parsed {len(manifest.segments)} segments for '{path.name}' using {current_model}."
                        )
                        return manifest

                    except Exception as gen_err:
                        last_error = gen_err
                        retries += 1
                        err_str = str(gen_err)

                        # If model is 404 not found or 503 high demand, immediately try next model if available
                        if "404" in err_str or "503" in err_str or "UNAVAILABLE" in err_str:
                            logger.warning(
                                f"Model {current_model} returned temporary issue ({gen_err}). Trying fallback..."
                            )
                            break

                        delay = (self.retry_delay_base ** retries) + random.uniform(1.0, 2.0)
                        logger.warning(
                            f"Generation attempt {retries} on {current_model} failed for '{path.name}' ({gen_err}). Retrying in {delay:.2f}s..."
                        )
                        time.sleep(delay)

            # If all models failed
            logger.error(f"All model attempts failed for '{path.name}': {last_error}")
            raise last_error or RuntimeError(f"Failed to transcribe {path.name}")

        finally:
            # 4. Cleanup remote file from Gemini Files API
            if uploaded_file:
                self.delete_remote_file(uploaded_file)
