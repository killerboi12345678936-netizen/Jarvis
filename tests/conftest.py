
import asyncio
import os
import tempfile

import pytest

# Unit tests call endpoints directly without pairing. Device auth has
# its own dedicated suite (tests/test_device_auth.py) which builds the
# middleware with enabled=True; must be set before backend imports.
os.environ.setdefault("JARVIS_DEVICE_AUTH", "0")

from backend.memory import database
from backend.tools import permissions


@pytest.fixture()
def temp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    monkeypatch.setattr(database, "DB_PATH", path)
    monkeypatch.setattr(permissions, "DB_PATH", path)

    asyncio.run(database.init_db())

    return path
