"""Tests for the runner of commands with a fixed argument list."""

import sys
from pathlib import Path

from scripts.fixed_command import run_fixed


def test_the_output_and_the_exit_code_come_back(tmp_path: Path) -> None:
    result = run_fixed([sys.executable, "-c", "import sys; print('out'); sys.exit(3)"], cwd=tmp_path)
    assert result.returncode == 3
    assert result.stdout.strip() == "out"


def test_the_environment_reaches_the_command() -> None:
    program = "import os; print(os.environ['SMOKE'])"
    result = run_fixed([sys.executable, "-c", program], env={"SMOKE": "yes", "PATH": ""})
    assert result.stdout.strip() == "yes"
