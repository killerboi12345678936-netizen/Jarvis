
import subprocess

import pytest

from backend.core.config import settings
from backend.tools.registry import run_tool


@pytest.fixture()
def fake_popen(monkeypatch):
    launched = []

    def fake(command, shell=False, cwd=None):
        launched.append(command)
        return None

    monkeypatch.setattr(subprocess, "Popen", fake)

    return launched


def test_open_application_launches_allowlisted(fake_popen):
    result = _run_open(settings.desktop_allowed_apps)

    command = settings.desktop_allowed_apps[result["launched"]]

    assert fake_popen == [command]


def _run_open(allowed_apps):
    name = next(iter(allowed_apps))

    return _run(name)


def _run(name):
    import asyncio

    return asyncio.run(run_tool("open_application", {"name": name}))


def test_open_application_rejects_unknown(fake_popen):
    with pytest.raises(ValueError, match="not in the allowed list"):
        _run("definitely_not_allowed_app_xyz")

    assert fake_popen == []


def test_open_application_is_case_insensitive(fake_popen):
    allowed = settings.desktop_allowed_apps

    if not allowed:
        pytest.skip("No desktop apps configured")

    name = next(iter(allowed))

    result = _run(name.upper())

    assert result["launched"] == name


def test_system_info_tool():
    import asyncio

    result = asyncio.run(run_tool("system_info", {}))

    assert result["system"]
    assert result["python"]


def test_allowed_apps_parsing():
    from backend.core.config import parse_allowed_apps

    parsed = parse_allowed_apps(
        "Notepad = notepad++, files=explorer,broken"
    )

    assert parsed == {"notepad": "notepad++", "files": "explorer"}
