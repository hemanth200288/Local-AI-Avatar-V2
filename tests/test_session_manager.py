import pytest
import time

from server.session_manager import (
    session_manager,
    ADMIN_PASSWORD,
    SESSION_IDLE_TIMEOUT,
)


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
    session_manager._created_at.clear()
    session_manager._last_active.clear()
    session_manager._metadata.clear()
    yield


class TestSessionLifecycle:
    def test_add_and_has_session(self):
        session_manager.add_session("s1", MockAvatar())
        assert session_manager.has_session("s1")
        assert session_manager.active_count() == 1

    def test_remove_session(self):
        session_manager.add_session("s2", MockAvatar())
        session_manager.remove_session("s2")
        assert not session_manager.has_session("s2")
        assert session_manager.active_count() == 0

    def test_remove_unknown_session_does_not_raise(self):
        session_manager.remove_session("nonexistent")

    def test_get_session(self):
        av = MockAvatar()
        session_manager.add_session("s3", av)
        assert session_manager.get_session("s3") is av


class TestTimestamps:
    def test_update_active_sets_timestamps(self):
        session_manager.add_session("t1", MockAvatar())
        assert "t1" in session_manager._created_at
        assert "t1" in session_manager._last_active

    def test_update_active_refreshes_last_active(self):
        session_manager.add_session("t2", MockAvatar())
        old = session_manager._last_active["t2"]
        time.sleep(0.01)
        session_manager.update_active("t2")
        assert session_manager._last_active["t2"] > old

    def test_set_session_metadata(self):
        session_manager.add_session("t3", MockAvatar())
        session_manager.set_session_metadata("t3", ip="1.2.3.4", user_agent="Mozilla/5.0 Chrome/120")
        meta = session_manager._metadata["t3"]
        assert meta["ip"] == "1.2.3.4"
        assert "Chrome" in meta["device"]

    def test_remove_cleans_tracking_dicts(self):
        session_manager.add_session("t4", MockAvatar())
        session_manager.set_session_metadata("t4", ip="9.9.9.9")
        session_manager.remove_session("t4")
        assert "t4" not in session_manager._created_at
        assert "t4" not in session_manager._last_active
        assert "t4" not in session_manager._metadata


class TestIPBlock:
    def test_block_and_unblock(self):
        assert not session_manager.is_ip_blocked("9.9.9.9")
        session_manager.block_ip("9.9.9.9")
        assert session_manager.is_ip_blocked("9.9.9.9")
        session_manager.unblock_ip("9.9.9.9")
        assert not session_manager.is_ip_blocked("9.9.9.9")

    def test_block_ip_twice_is_idempotent(self):
        session_manager.block_ip("1.1.1.1")
        session_manager.block_ip("1.1.1.1")
        assert session_manager.get_blocked_ips() == ["1.1.1.1"]

    def test_list_blocked_ips(self):
        session_manager.block_ip("2.2.2.2")
        session_manager.block_ip("3.3.3.3")
        assert session_manager.get_blocked_ips() == ["2.2.2.2", "3.3.3.3"]


class TestAllSessionsInfo:
    def test_returns_basic_info(self):
        session_manager.add_session("i1", MockAvatar())
        info = session_manager.all_sessions_info()
        assert len(info) == 1
        entry = info[0]
        assert entry["sessionid"] == "i1"
        assert "speaking" in entry
        assert "recording" in entry

    def test_empty_when_no_sessions(self):
        assert session_manager.all_sessions_info() == []

    def test_excludes_none_sessions(self):
        session_manager.sessions["orphan"] = None
        assert session_manager.all_sessions_info() == []

    def test_includes_ip_device_timestamps(self):
        session_manager.add_session("i2", MockAvatar())
        session_manager.set_session_metadata("i2", ip="6.6.6.6", user_agent="TestAgent/1.0")
        info = session_manager.all_sessions_info()
        entry = info[0]
        assert entry["ip"] == "6.6.6.6"
        assert entry["device"] == "TestAgent/1.0"
        assert entry["created_at"] is not None
        assert entry["age_seconds"] is not None
        assert entry["idle_seconds"] is not None


class TestExpiry:
    def test_cleanup_expired_removes_idle_sessions(self):
        session_manager.add_session("e1", MockAvatar())
        session_manager._last_active["e1"] = time.time() - SESSION_IDLE_TIMEOUT - 10
        removed = session_manager.cleanup_expired_sessions()
        assert removed == 1
        assert not session_manager.has_session("e1")

    def test_cleanup_keeps_active_sessions(self):
        session_manager.add_session("e2", MockAvatar())
        session_manager.update_active("e2")
        removed = session_manager.cleanup_expired_sessions()
        assert removed == 0
        assert session_manager.has_session("e2")

    def test_cleanup_runs_safely_on_empty(self):
        assert session_manager.cleanup_expired_sessions() == 0


class TestADMIN_PASSWORD:
    def test_password_constant(self):
        assert ADMIN_PASSWORD == "Kittu.2002"
