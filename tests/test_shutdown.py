import sys
import asyncio
from unittest.mock import patch, MagicMock
import os

def test_session_manager_force_shutdown():
    # Set small timeouts for the test execution
    os.environ["SESSION_IDLE_TIMEOUT"] = "1"
    os.environ["CLEANUP_GRACE_PERIOD"] = "1"
    os.environ["CLEANUP_INTERVAL"] = "1"

    # Let's mock the `os._exit` so it raises an exception we can catch instead of actually killing pytest.
    with patch("os._exit") as mock_exit:
        mock_exit.side_effect = SystemExit("Force shutdown triggered")
        
        # Directly import what we need
        from server.session_manager import session_manager
        
        # Create a mock session to simulate the manager being active then going idle
        session_manager.sessions.clear() # Ensure it's empty
        
        # Add a dummy session
        dummy_avatar = MagicMock()
        session_manager.add_session("test_session_1", dummy_avatar)
        
        assert session_manager.active_count() == 1

        # Define the local cleanup_loop that app.py uses exactly as written
        async def dummy_cleanup():
            import time
            import os
            interval = int(os.environ.get("CLEANUP_INTERVAL", 10))
            project_timeout = int(os.environ.get("PROJECT_EMPTY_TIMEOUT", 120))
            zero_sessions_start_time = time.time() # Start counting from server boot
            
            while True:
                session_manager.cleanup_expired_sessions()
                if session_manager.active_count() == 0:
                    if zero_sessions_start_time is None:
                        zero_sessions_start_time = time.time()
                    elif time.time() - zero_sessions_start_time > project_timeout:
                        os._exit(0)
                else:
                    zero_sessions_start_time = None
                await asyncio.sleep(interval)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # We give it slightly longer than the grace period + interval to process
            loop.run_until_complete(asyncio.wait_for(dummy_cleanup(), timeout=10.0))
        except SystemExit as e:            assert str(e) == "Force shutdown triggered"
            assert session_manager.active_count() == 0, "Session manager should be empty"
            print("Successfully verified force shutdown logic. The inactive session was cleaned up and shutdown triggered.")
        except asyncio.TimeoutError:
            import pytest
            pytest.fail("The cleanup loop did not trigger force shutdown within the timeout.")
