"""scripts/refresh-task.ps1: preview only, never registers; no credentials; safe settings."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "refresh-task.ps1"
PWSH = shutil.which("pwsh")
needs_pwsh = pytest.mark.skipif(PWSH is None, reason="PowerShell 7 (pwsh) not installed")


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-File", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def _xml(out: str) -> str:
    return out[out.index("<?xml") : out.index("</Task>") + len("</Task>")]


@needs_pwsh
def test_preview_is_the_default_and_registers_nothing():
    result = _run()
    assert result.returncode == 0, result.stderr
    assert "Preview only: nothing was registered." in result.stdout
    assert "Task Scheduler parsed this definition (not registered)." in result.stdout


@needs_pwsh
def test_preview_settings_are_least_privilege_bounded_and_non_overlapping():
    xml = _xml(_run("-Action", "Preview").stdout)
    for fragment in (
        "<LogonType>InteractiveToken</LogonType>",
        "<RunLevel>LeastPrivilege</RunLevel>",
        "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>",
        "<ExecutionTimeLimit>PT30M</ExecutionTimeLimit>",
        "<WakeToRun>false</WakeToRun>",
        "<RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>",
        "<StartWhenAvailable>true</StartWhenAvailable>",
        "<Arguments>refresh</Arguments>",
        r"<URI>\mambo-electricity-explorer\refresh</URI>",
    ):
        assert fragment in xml, fragment
    command = re.search(r"<Command>(.*)</Command>", xml).group(1)
    workdir = re.search(r"<WorkingDirectory>(.*)</WorkingDirectory>", xml).group(1)
    assert re.match(r"^[A-Za-z]:\\", command) and command.endswith(
        r"\.venvs\py314\Scripts\mambo.exe"
    )
    assert re.match(r"^[A-Za-z]:\\", workdir)


@needs_pwsh
def test_preview_contains_no_credentials_or_elevation():
    xml = _xml(_run().stdout).lower()
    for forbidden in (
        "eia_api_key",
        "api_key",
        "password",
        "highestavailable",
        "s-1-5-18",
        "<logontype>password",
        "nt authority\\system",
        "token>",
    ):
        assert forbidden not in xml.replace("interactivetoken", ""), forbidden


@needs_pwsh
def test_options_change_only_the_documented_settings():
    xml = _xml(
        _run("-NoCatchUpStart", "-TimeLimitMinutes", "15", "-At", "05:30", "-Python", "3.11").stdout
    )
    assert "<StartWhenAvailable>false</StartWhenAvailable>" in xml
    assert "<ExecutionTimeLimit>PT15M</ExecutionTimeLimit>" in xml
    assert "T05:30:00</StartBoundary>" in xml and r"\.venvs\py311\Scripts\mambo.exe" in xml


@needs_pwsh
@pytest.mark.parametrize(
    "args", [("-Action", "Delete"), ("-At", "25:00"), ("-TimeLimitMinutes", "600")]
)
def test_invalid_arguments_are_rejected(args):
    assert _run(*args).returncode != 0


def test_script_only_ever_touches_its_own_task_name():
    text = SCRIPT.read_text("utf-8")
    assert (
        '$TaskPath = "\\mambo-electricity-explorer\\"' in text and '$TaskName = "refresh"' in text
    )
    for verb in (
        "Register-ScheduledTask",
        "Disable-ScheduledTask",
        "Unregister-ScheduledTask",
        "Get-ScheduledTask ",
        "Get-ScheduledTaskInfo",
    ):
        for line in (ln for ln in text.splitlines() if verb in ln):
            assert "-TaskPath $TaskPath -TaskName $TaskName" in line, line
    assert '[string]$Action = "Preview"' in text
    for forbidden in (
        "powercfg",
        "Set-ScheduledTask",
        "-RunLevel Highest",
        "SYSTEM",
        "Credential",
        "Read-Host",
        "-Password",
    ):
        assert forbidden not in text, forbidden
