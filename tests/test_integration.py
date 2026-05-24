import os
import json
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from aiohttp import web

from server.session_manager import session_manager
from server.routes import setup_routes


class MockAvatar:
    def is_speaking(self):
        return False
    recording = False


@pytest.fixture(autouse=True)
def clean_sessions():
    keys = list(session_manager.sessions.keys())
    for k in keys:
        session_manager.remove_session(k)
    session_manager.blocked_ips.clear()
    yield


class TestHumanaudiochatRoute:
    @pytest.mark.asyncio
    async def test_humanaudiochat_returns_error_on_stt_failure(self):
        """STT error message should propagate to client"""
        session_manager.add_session("test-sid", MockAvatar())

        from server.routes import humanaudiochat

        app = web.Application()
        app["llm_response"] = MagicMock()

        request = AsyncMock()
        request.app = app
        mock_form = {"sessionid": "test-sid",
                      "file": MagicMock(file=MagicMock(read=MagicMock(
                          return_value=b"fake-audio")))}
        request.post.return_value = mock_form

        with patch("llm.stt_response",
                   side_effect=RuntimeError("API quota exceeded")):
            resp = await humanaudiochat(request)
            data = json.loads(resp.text)
            assert data["code"] == -1
            assert "API quota exceeded" in data["msg"]

    def test_json_error_includes_message(self):
        from server.routes import json_error
        resp = json_error("custom error message")
        data = json.loads(resp.text)
        assert data["code"] == -1
        assert data["msg"] == "custom error message"


class TestAdminAPI:
    @pytest.mark.asyncio
    async def test_admin_sessions_returns_data(self):
        from server.routes import admin_sessions

        session_manager.add_session("admin-test", MockAvatar())
        session_manager.set_session_metadata("admin-test", ip="5.5.5.5",
                                              user_agent="Mozilla/5.0 Chrome")

        request = MagicMock()
        request.app = web.Application()

        resp = await admin_sessions(request)
        data = json.loads(resp.text)
        assert data["code"] == 0
        sessions = data["data"]["sessions"]
        s = next(s for s in sessions if s["sessionid"] == "admin-test")
        assert s["speaking"] is False
        assert s["recording"] is False
        assert s["ip"] == "5.5.5.5"
        assert "Chrome" in s["device"]
        assert s["created_at"] is not None
        assert s["age_seconds"] is not None
        assert s["idle_seconds"] is not None
        assert data["data"]["active_count"] >= 1

    @pytest.mark.asyncio
    async def test_admin_session_kill_wrong_password(self):
        from server.routes import admin_session_kill

        session_manager.add_session("kill-test", MockAvatar())

        request = AsyncMock()
        request.app = web.Application()
        request.json.return_value = {"password": "wrong",
                                      "sessionid": "kill-test"}

        resp = await admin_session_kill(request)
        data = json.loads(resp.text)
        assert data["code"] == -1
        assert session_manager.has_session("kill-test")

    @pytest.mark.asyncio
    async def test_admin_session_kill_correct_password(self):
        from server.routes import admin_session_kill

        session_manager.add_session("kill-test2", MockAvatar())

        request = AsyncMock()
        request.app = web.Application()
        request.json.return_value = {"password": "Kittu.2002",
                                      "sessionid": "kill-test2"}

        resp = await admin_session_kill(request)
        data = json.loads(resp.text)
        assert data["code"] == 0
        assert not session_manager.has_session("kill-test2")


class TestIPBlockRoutes:
    @pytest.mark.asyncio
    async def test_admin_block_ip(self):
        from server.routes import admin_block_ip

        request = AsyncMock()
        request.app = web.Application()
        request.json.return_value = {"password": "Kittu.2002",
                                      "ip": "1.2.3.4"}

        resp = await admin_block_ip(request)
        data = json.loads(resp.text)
        assert data["code"] == 0
        assert session_manager.is_ip_blocked("1.2.3.4")

    @pytest.mark.asyncio
    async def test_admin_unblock_ip(self):
        from server.routes import admin_unblock_ip

        session_manager.block_ip("5.6.7.8")

        request = AsyncMock()
        request.app = web.Application()
        request.json.return_value = {"password": "Kittu.2002",
                                      "ip": "5.6.7.8"}

        resp = await admin_unblock_ip(request)
        data = json.loads(resp.text)
        assert data["code"] == 0
        assert not session_manager.is_ip_blocked("5.6.7.8")

    @pytest.mark.asyncio
    async def test_admin_blocked_ips(self):
        from server.routes import admin_blocked_ips

        session_manager.block_ip("9.9.9.9")

        request = MagicMock()
        request.app = web.Application()

        resp = await admin_blocked_ips(request)
        data = json.loads(resp.text)
        assert data["code"] == 0
        assert "9.9.9.9" in data["data"]["blocked_ips"]


class TestWebRTCOfferBlock:
    @pytest.mark.asyncio
    async def test_blocked_ip_rejected(self):
        from server.rtc_manager import RTCManager

        session_manager.block_ip("9.9.9.9")

        opt = MagicMock()
        rtc = RTCManager(opt)

        request = AsyncMock()
        request.headers = {"X-Forwarded-For": "9.9.9.9",
                           "User-Agent": "Mozilla/5.0"}
        request.remote = "9.9.9.9"
        request.json.return_value = {"sdp": "", "type": "offer"}

        resp = await rtc.handle_offer(request)
        data = json.loads(resp.text)
        assert data["code"] == -1
        assert data["msg"] == "blocked"
