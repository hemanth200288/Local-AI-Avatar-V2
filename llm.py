import time
import os
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from avatars.base_avatar import BaseAvatar
from utils.logger import logger
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def get_client():
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = "https://openrouter.ai/api/v1"
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

def llm_response(message, avatar_session:'BaseAvatar', datainfo:dict={}):
    try:
        start = time.perf_counter()
        client = get_client()
        
        end = time.perf_counter()
        logger.info(f"llm Time init: {end-start}s,{message}")
        
        completion = client.chat.completions.create(
            model="google/gemma-3-12b-it",
            messages=[
                {'role': 'system', 'content': 'You are a 20-year-old Indian male assistant. You must respond ONLY in English. Keep your responses concise, conversational, and helpful.'},
                {'role': 'user', 'content': message}
            ],
            stream=True,
        )
        
        result = ""
        first = True
        for chunk in completion:
            if len(chunk.choices) > 0:
                if first:
                    end = time.perf_counter()
                    logger.info(f"llm Time to first chunk: {end-start}s")
                    first = False
                msg = chunk.choices[0].delta.content
                if msg is None:
                    continue
                lastpos = 0
                for i, char in enumerate(msg):
                    if char in ",.!;:，。！？：；":
                        result = result + msg[lastpos:i+1]
                        lastpos = i + 1
                        if len(result) > 10:
                            logger.info(result)
                            avatar_session.put_msg_txt(result, datainfo)
                            result = ""
                result = result + msg[lastpos:]
        
        end = time.perf_counter()
        logger.info(f"llm Time to last chunk: {end-start}s")
        if result:
            avatar_session.put_msg_txt(result, datainfo)
            
    except Exception as e:
        logger.exception('llm exception:')
        return

import requests
import base64

def _detect_audio_format(filepath: str) -> str:
    """
    Detect audio format from magic bytes (ignores file extension).
    Browser MediaRecorder produces WebM/Opus but often labels it 'audio/wav'.
    """
    with open(filepath, "rb") as f:
        header = f.read(16)
    if header.startswith(b"RIFF"):
        return "wav"
    if header.startswith(b"ID3") or header[:2] == b"\xff\xfb":
        return "mp3"
    if header.startswith(b"OggS"):
        return "ogg"
    if header.startswith(b"fLaC"):
        return "flac"
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    if header[4:8] == b"ftyp":
        return "m4a"
    return "wav"

def stt_response(audio_file_path):
    """
    Transcribe audio using OpenRouter's Whisper model via JSON/Base64.
    Detects real audio format from magic bytes (not file extension).
    """
    try:
        api_key = os.getenv("OPENROUTER_API_KEY")

        with open(audio_file_path, "rb") as audio_file:
            base64_audio = base64.b64encode(audio_file.read()).decode("utf-8")

        audio_format = _detect_audio_format(audio_file_path)
        logger.info("STT detected format=%s for %s", audio_format, audio_file_path)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "model": "openai/whisper-large-v3-turbo",
            "input_audio": {
                "data": base64_audio,
                "format": audio_format,
            },
        }

        logger.info("Starting STT for %s via OpenRouter JSON API", audio_file_path)
        response = requests.post(
            "https://openrouter.ai/api/v1/audio/transcriptions",
            headers=headers,
            json=data,
            timeout=60,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"STT API error {response.status_code}: {response.text[:500]}"
            )

        result = response.json()
        text = (result.get("text") or "").strip()
        logger.info("STT result: %s", text)
        return text

    except Exception as e:
        logger.error(f"STT exception: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None