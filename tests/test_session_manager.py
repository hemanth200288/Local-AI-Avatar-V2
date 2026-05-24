import pytest

from server.session_manager import (
    session_manager,
    ADMIN_PASSWORD,
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


class TestADMIN_PASSWORD:
    def test_password_constant(self):
        assert ADMIN_PASSWORD == "Kittu.2002"
