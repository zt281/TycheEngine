"""Tests for admin lifecycle hooks."""
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.tyche.engine import TycheEngine
from src.tyche.module import TycheModule
from src.tyche.message import Message, MessageType, serialize, deserialize
from src.tyche.types import (
    Endpoint,
    Interface,
    InterfacePattern,
    BackpressureStrategy,
    DurabilityLevel,
    ModuleInfo,
)


@pytest.fixture
def unstarted_engine(tmp_path):
    """TycheEngine instance WITHOUT started workers. NEVER call .start()."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 20550),
        event_endpoint=Endpoint("127.0.0.1", 20551),
        heartbeat_endpoint=Endpoint("127.0.0.1", 20553),
        data_dir=str(tmp_path / "data"),
    )
    engine._job_router = MagicMock()
    engine._running = True
    yield engine
    # Robust cleanup: stop() joins daemon threads even if start() was never called
    try:
        engine.stop()
    except Exception:
        pass
    engine._running = False
    if engine.context is not None and not engine.context.closed:
        engine.context.destroy(linger=0)


class TestAdminHandlerModule:
    """Tests for admin handlers on the module side."""

    def test_health_check_returns_status(self):
        """health_check returns {'status': 'healthy', ...}."""
        class TestModule(TycheModule):
            def handle_work(self, payload):
                return {"done": True}

        with patch("zmq.Context"):
            module = TestModule(
                engine_endpoint=Endpoint("127.0.0.1", 20550),
                family_name="health_test_mod",
            )

        result = module._admin_health_check()
        assert result["status"] == "healthy"
        assert result["module_id"] == "health_test_mod"
        assert "uptime" in result
        assert result["uptime"] >= 0

    def test_availability_check_returns_handler_info(self):
        """Returns handler availability dict."""
        class TestModule(TycheModule):
            def handle_compute(self, payload):
                return {}

        with patch("zmq.Context"):
            module = TestModule(
                engine_endpoint=Endpoint("127.0.0.1", 20550),
                family_name="avail_test_mod",
            )

        result = module._admin_availability_check()
        assert result["module_id"] == "avail_test_mod"
        assert "handlers" in result
        assert "compute" in result["handlers"]
        assert result["handlers"]["compute"] is True

    def test_decommission_sets_flag(self):
        """After decommission, _decommissioned is True."""
        class TestModule(TycheModule):
            def handle_work(self, payload):
                return {}

        with patch("zmq.Context"):
            module = TestModule(
                engine_endpoint=Endpoint("127.0.0.1", 20550),
                family_name="decom_test_mod",
            )

        assert module._decommissioned is False

        result = module._admin_decommission()
        assert module._decommissioned is True
        assert result["status"] == "decommissioning"
        assert result["module_id"] == "decom_test_mod"

    def test_admin_handlers_registered_on_module_init(self):
        """Module registers admin handlers during setup."""
        class TestModule(TycheModule):
            def handle_work(self, payload):
                return {}

        with patch("zmq.Context"):
            module = TestModule(
                engine_endpoint=Endpoint("127.0.0.1", 20550),
                family_name="init_test_mod",
            )

        # Check admin handler map is populated
        assert hasattr(module, "_admin_handler_map")
        assert "health_check" in module._admin_handler_map
        assert "availability_check" in module._admin_handler_map
        assert "respawn" in module._admin_handler_map
        assert "decommission" in module._admin_handler_map

        # All values should be callable
        for name, handler in module._admin_handler_map.items():
            assert callable(handler)


class TestAdminHandlerEngine:
    """Tests for admin handler invocation from the engine side."""

    def test_engine_invoke_admin_handler(self, unstarted_engine):
        """Engine can send admin commands to specific modules."""
        # Register a module with admin handlers
        unstarted_engine._module_admin_handlers["target_mod"] = [
            "health_check", "availability_check", "respawn", "decommission"
        ]

        result = unstarted_engine.invoke_admin_handler("target_mod", "health_check")

        # Should return sent confirmation
        assert result is not None
        assert result["status"] == "sent"
        assert "correlation_id" in result

        # Verify the job router was called
        unstarted_engine._job_router.send_multipart.assert_called_once()
        sent_frames = unstarted_engine._job_router.send_multipart.call_args[0][0]
        assert sent_frames[0] == b"target_mod"
        assert sent_frames[2] == b"admin.health_check"

        # Verify message contents
        sent_msg = deserialize(sent_frames[3])
        assert sent_msg.msg_type == MessageType.REQUEST
        assert sent_msg.event == "admin.health_check"
        assert sent_msg.payload["command"] == "health_check"

    def test_unknown_admin_handler_ignored(self, unstarted_engine):
        """Unknown admin command doesn't crash."""
        # Module registered but with limited handlers
        unstarted_engine._module_admin_handlers["target_mod"] = ["health_check"]

        # Try to invoke an unregistered handler
        result = unstarted_engine.invoke_admin_handler("target_mod", "unknown_command")
        assert result is None

        # Job router should NOT have been called
        unstarted_engine._job_router.send_multipart.assert_not_called()

    def test_invoke_unregistered_module_returns_none(self, unstarted_engine):
        """Invoking admin handler on unregistered module returns None."""
        result = unstarted_engine.invoke_admin_handler("nonexistent_mod", "health_check")
        assert result is None

    def test_module_handles_admin_job_request(self):
        """Module dispatches admin commands to the correct admin handler."""
        class TestModule(TycheModule):
            def handle_work(self, payload):
                return {}

        with patch("zmq.Context"):
            module = TestModule(
                engine_endpoint=Endpoint("127.0.0.1", 20550),
                family_name="admin_dispatch_mod",
            )

        # Mock job socket
        module._job_socket = MagicMock()

        # Create an admin request message
        admin_msg = Message(
            msg_type=MessageType.REQUEST,
            sender="engine",
            event="admin.health_check",
            payload={"command": "health_check"},
            correlation_id=str(uuid.uuid4()),
        )

        # Handle the request
        module._handle_job_request(admin_msg)

        # Verify response was sent
        module._job_socket.send_multipart.assert_called_once()
        sent_frames = module._job_socket.send_multipart.call_args[0][0]
        response_msg = deserialize(sent_frames[2])
        assert response_msg.msg_type == MessageType.RESPONSE
        assert response_msg.correlation_id == admin_msg.correlation_id
        assert "result" in response_msg.payload
        assert response_msg.payload["result"]["status"] == "healthy"
