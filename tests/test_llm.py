import os
import json
import pytest
from unittest.mock import patch, MagicMock, mock_open
import tempfile


class TestDetectAudioFormat:
    def _write_and_detect(self, magic_bytes):
        from llm import _detect_audio_format
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(magic_bytes)
            path = f.name
        try:
            return _detect_audio_format(path)
        finally:
            os.unlink(path)

    def test_wav(self):
        assert self._write_and_detect(b"RIFF....WAVE") == "wav"

    def test_mp3_id3(self):
        assert self._write_and_detect(b"ID3........") == "mp3"

    def test_mp3_raw(self):
        assert self._write_and_detect(b"\xff\xfb\x90\x00") == "mp3"

    def test_ogg(self):
        assert self._write_and_detect(b"OggS....") == "ogg"

    def test_flac(self):
        assert self._write_and_detect(b"fLaC....") == "flac"

    def test_webm(self):
        assert self._write_and_detect(b"\x1a\x45\xdf\xa3webm") == "webm"

    def test_m4a(self):
        assert self._write_and_detect(b"\x00\x00\x00\x1cftypmp42") == "m4a"

    def test_unknown_defaults_to_wav(self):
        assert self._write_and_detect(b"\x00\x01\x02\x03") == "wav"


class TestLLMModule:
    def test_imports(self):
        from llm import get_client, llm_response, stt_response
        assert callable(get_client)
        assert callable(llm_response)
        assert callable(stt_response)

    def test_get_client_returns_openai_client(self):
        from llm import get_client
        from openai import OpenAI
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test-key"}):
            client = get_client()
            assert isinstance(client, OpenAI)
            assert client.api_key == "sk-test-key"
            assert "openrouter.ai" in str(client.base_url)


class TestSTTResponse:
    @patch("llm.requests.post")
    def test_stt_success_wav(self, mock_post):
        from llm import stt_response

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "hello world"}
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}):
            with patch("builtins.open", mock_open(read_data=b"RIFF....WAVE")):
                result = stt_response("/tmp/test.wav")

        assert result == "hello world"
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["model"] == "openai/whisper-large-v3-turbo"
        assert kwargs["json"]["input_audio"]["format"] == "wav"
        assert kwargs["headers"]["Authorization"] == "Bearer sk-test"

    @patch("llm.requests.post")
    def test_stt_success_webm(self, mock_post):
        from llm import stt_response

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "hello"}
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}):
            with patch("builtins.open",
                       mock_open(read_data=b"\x1a\x45\xdf\xa3webmdata")):
                result = stt_response("/tmp/audio.webm")

        assert result == "hello"
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["input_audio"]["format"] == "webm"

    @patch("llm.requests.post")
    def test_stt_api_error_returns_none(self, mock_post):
        from llm import stt_response

        mock_resp = MagicMock()
        mock_resp.status_code = 402
        mock_resp.text = '{"error": "insufficient_credits"}'
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}):
            with patch("builtins.open", mock_open(read_data=b"RIFF....WAVE")):
                result = stt_response("/tmp/test.wav")

        assert result is None

    @patch("llm.requests.post")
    def test_stt_empty_text(self, mock_post):
        from llm import stt_response

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "   "}
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}):
            with patch("builtins.open", mock_open(read_data=b"RIFF....WAVE")):
                result = stt_response("/tmp/test.wav")

        assert result == ""

    def test_stt_no_api_key_returns_none(self):
        from llm import stt_response
        with patch.dict(os.environ, {}, clear=True):
            with patch("builtins.open", mock_open(read_data=b"RIFF....WAVE")):
                result = stt_response("/tmp/test.wav")
        assert result is None


class TestLLMResponse:
    @patch("llm.get_client")
    def test_llm_response_calls_chat(self, mock_get_client):
        from llm import llm_response

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.chat.completions.create.return_value = iter([])

        mock_avatar = MagicMock()
        llm_response("hello", mock_avatar, {})

        mock_client.chat.completions.create.assert_called_once()
        args, kwargs = mock_client.chat.completions.create.call_args
        assert kwargs["model"] == "google/gemma-3-12b-it"
        assert kwargs["stream"] is True
