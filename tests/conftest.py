
import asyncio
import os
import tempfile

import pytest

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
