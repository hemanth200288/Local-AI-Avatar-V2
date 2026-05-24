import os
import time
import numpy as np
import resampy
import soundfile as sf
from io import BytesIO
from openai import OpenAI

from utils.logger import logger
from .base_tts import BaseTTS, State
from registry import register

@register("tts", "openrouter")
class OpenRouterTTS(BaseTTS):
    def __init__(self, opt, parent):
        super().__init__(opt, parent)
        self.model = getattr(opt, "openrouter_model", "openai/gpt-4o-mini-tts-2025-12-15")
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logger.error("OPENROUTER_API_KEY not set. OpenRouter TTS disabled.")
            self.client = None
            return
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

    def txt_to_audio(self, msg: tuple[str, dict]):
        text, textevent = msg
        if not text:
            return

        if self.client is None:
            logger.error('OpenRouter TTS client unavailable (check API key)')
            return

        voicename = textevent.get('tts', {}).get('ref_file', self.opt.REF_FILE)
        t = time.time()
        try:
            response = self.client.audio.speech.create(
                model=self.model,
                voice=voicename,
                input=text,
                response_format="mp3"
            )
            audio_data = response.content
            logger.info(f'-------openrouter tts time:{time.time()-t:.4f}s')

            if not audio_data:
                logger.error('openrouter tts error: no audio data received')
                return

            byte_stream = BytesIO(audio_data)
            stream = self.__create_bytes_stream(byte_stream)
            streamlen = stream.shape[0]
            idx = 0
            while streamlen >= self.chunk and self.state == State.RUNNING:
                eventpoint = {}
                streamlen -= self.chunk
                if idx == 0:
                    eventpoint = {'status': 'start', 'text': text}
                elif streamlen < self.chunk:
                    eventpoint = {'status': 'end', 'text': text}
                eventpoint.update(**textevent)
                self.parent.put_audio_frame(stream[idx:idx+self.chunk], eventpoint)
                idx += self.chunk

        except Exception as e:
            err_str = str(e)
            if '402' in err_str or 'insufficient' in err_str.lower():
                logger.error('OpenRouter TTS: Insufficient credits. Add funds at https://openrouter.ai/settings/credits')
            elif '429' in err_str or 'rate' in err_str.lower():
                logger.error('OpenRouter TTS: Rate limited. Try again later.')
            else:
                logger.exception(f'openrouter tts exception: {e}')

    def __create_bytes_stream(self, byte_stream):
        stream, sample_rate = sf.read(byte_stream)
        logger.info(f'[INFO]tts audio stream {sample_rate}: {stream.shape}')
        stream = stream.astype(np.float32)

        if stream.ndim > 1:
            logger.info(f'[WARN] audio has {stream.shape[1]} channels, only use the first.')
            stream = stream[:, 0]
    
        if sample_rate != self.sample_rate and stream.shape[0] > 0:
            logger.info(f'[WARN] audio sample rate is {sample_rate}, resampling into {self.sample_rate}.')
            stream = resampy.resample(x=stream, sr_orig=sample_rate, sr_new=self.sample_rate)

        return stream
