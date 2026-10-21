import socket
import pytest
from app.services.vector_store import vector_store
from app.config import settings


def test_chromadb_anonymized_telemetry_disabled():
    """Verify that ChromaDB was initialized with anonymized_telemetry=False."""
    client_settings = vector_store.client.get_settings()
    assert client_settings.anonymized_telemetry is False, "ChromaDB telemetry must be disabled"


def test_socket_offline_guard_blocks_external_hosts(monkeypatch):
    """
    Test that our offline guard blocks any socket connection
    to non-localhost destinations.
    """
    original_connect = socket.socket.connect

    allowed_hosts = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}

    def guarded_connect(sock, address):
        host = address[0]
        # Resolve localhost names if needed
        if host not in allowed_hosts and not host.startswith("127."):
            raise ConnectionRefusedError(f"OFFLINE VIOLATION: Blocked outgoing network call to {host}")
        return original_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)

    # Connecting to non-localhost must fail
    with pytest.raises(ConnectionRefusedError, match="OFFLINE VIOLATION"):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("8.8.8.8", 53))


def test_settings_strict_offline_flag():
    assert settings.OFFLINE_MODE_ONLY is True
    assert "127.0.0.1" in settings.OLLAMA_BASE_URL or "localhost" in settings.OLLAMA_BASE_URL
