"""Unit tests for samba_cli - CLI adapter (Phase 7).

Tests use both subprocess-based invocation (end-to-end) and
:class:`typer.testing.CliRunner` (in-process) for faster unit coverage.

No solver is invoked in these tests — integration tests that actually call the
solver are marked ``@pytest.mark.integration`` and excluded from the default
test run.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from samba_cli.main import app

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXAMPLES_DIR: Path = Path(__file__).parent.parent.parent / "examples"
BASE_SCENARIO: Path = EXAMPLES_DIR / "base_scenario.yaml"

# Use ``sys.executable -m samba_cli`` so tests always use the active interpreter
# (works even if the ``samba`` entry-point is not on PATH after an editable install).
CLI_BASE = [sys.executable, "-m", "samba_cli"]

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a CLI command via subprocess and return the result."""
    # PYTHONUTF8=1 forces UTF-8 I/O on Windows (avoids cp1252 UnicodeEncodeError
    # when Rich emits Unicode symbols like ✓/✗ to a piped stdout/stderr).
    # COLUMNS pins the Rich/Typer render width so help text renders at a stable
    # width across environments (headless CI terminals otherwise vary).
    env = {
        **os.environ,
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "COLUMNS": "200",
        "LINES": "50",
    }
    return subprocess.run(
        [*CLI_BASE, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def _minimal_scenario_yaml() -> str:
    """Return a minimal but schema-valid scenario YAML string."""
    return textwrap.dedent("""\
        schema_version: "1.0"
        project:
          name: "CLI Test"
          discount_rate_nominal: 0.06
        location:
          latitude: 0.0
          longitude: 0.0
          timezone: "UTC"
        weather:
          source: "csv"
          csv_path: "weather.csv"
        load:
          source: "hourly_csv"
          csv_path: "load.csv"
        components:
          inverter:
            capex_per_kw: 200.0
          pv:
            capex_per_kw: 900.0
          battery:
            capex_per_kwh: 350.0
        tariff:
          buy:
            type: "flat"
            rate_per_kwh: 0.15
    """)


# ---------------------------------------------------------------------------
# Subprocess tests — help / meta
# ---------------------------------------------------------------------------


class TestHelp:
    """``samba --help`` and sub-command help flags."""

    def test_root_help_exit_0(self) -> None:
        proc = _cli("--help")
        assert proc.returncode == 0

    def test_root_help_mentions_commands(self) -> None:
        proc = _cli("--help")
        output = proc.stdout + proc.stderr
        assert "run" in output
        assert "validate" in output
        assert "info" in output

    def test_run_help_exit_0(self) -> None:
        proc = _cli("run", "--help")
        assert proc.returncode == 0

    def test_run_help_mentions_options(self) -> None:
        # Introspect the registered command rather than scraping rendered --help
        # text: Rich/Typer wraps option names at the terminal width, which made
        # this substring assertion flaky on headless CI runners (surfaced when CI
        # was re-enabled). Same intent — the `run` command exposes `--output-dir`
        # and `--solver` — without any rendering dependency.
        run_cmd = typer.main.get_command(app).commands["run"]
        option_names = {opt for param in run_cmd.params for opt in getattr(param, "opts", [])}
        assert "--output-dir" in option_names
        assert "--solver" in option_names

    def test_validate_help_exit_0(self) -> None:
        proc = _cli("validate", "--help")
        assert proc.returncode == 0

    def test_info_help_exit_0(self) -> None:
        proc = _cli("info", "--help")
        assert proc.returncode == 0


# ---------------------------------------------------------------------------
# Subprocess tests — validate command
# ---------------------------------------------------------------------------


class TestValidateSubprocess:
    """``samba validate`` via subprocess."""

    def test_validate_valid_scenario_exit_0(self) -> None:
        proc = _cli("validate", str(BASE_SCENARIO))
        assert proc.returncode == 0, proc.stderr

    def test_validate_nonexistent_file_exit_1(self) -> None:
        proc = _cli("validate", "/nonexistent/path.yaml")
        assert proc.returncode == 1

    def test_validate_nonexistent_prints_error(self) -> None:
        proc = _cli("validate", "/nonexistent/path.yaml")
        output = proc.stdout + proc.stderr
        # Should mention the missing path in some form
        assert "not found" in output.lower() or "error" in output.lower()

    def test_validate_invalid_yaml_exit_1(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(
            "project:\n  name: Test\n  discount_rate_nominal: not_a_float\n",
            encoding="utf-8",
        )
        proc = _cli("validate", str(bad_yaml))
        assert proc.returncode == 1

    def test_validate_missing_required_field_exit_1(self, tmp_path: Path) -> None:
        # Missing 'location' field entirely
        bad_yaml = tmp_path / "incomplete.yaml"
        bad_yaml.write_text(
            textwrap.dedent("""\
                project:
                  name: "test"
                  discount_rate_nominal: 0.06
                weather:
                  source: "csv"
                  csv_path: "w.csv"
            """),
            encoding="utf-8",
        )
        proc = _cli("validate", str(bad_yaml))
        assert proc.returncode == 1

    def test_validate_success_prints_valid(self) -> None:
        proc = _cli("validate", str(BASE_SCENARIO))
        output = proc.stdout + proc.stderr
        assert "valid" in output.lower()


# ---------------------------------------------------------------------------
# Subprocess tests — info command
# ---------------------------------------------------------------------------


class TestInfoSubprocess:
    """``samba info`` via subprocess."""

    def test_info_exit_0(self) -> None:
        proc = _cli("info")
        assert proc.returncode == 0

    def test_info_prints_version(self) -> None:
        from samba._version import __version__

        proc = _cli("info")
        output = proc.stdout + proc.stderr
        assert __version__ in output

    def test_info_prints_python_version(self) -> None:
        proc = _cli("info")
        output = proc.stdout + proc.stderr
        python_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        assert python_ver in output

    def test_info_mentions_solver(self) -> None:
        proc = _cli("info")
        output = proc.stdout + proc.stderr
        # Should mention at least one solver
        assert "highs" in output.lower() or "cbc" in output.lower()


# ---------------------------------------------------------------------------
# Subprocess tests — run command (error paths only; no solver)
# ---------------------------------------------------------------------------


class TestRunSubprocess:
    """``samba run`` error-path tests that do not invoke the solver."""

    def test_run_nonexistent_scenario_exit_1(self) -> None:
        proc = _cli("run", "/nonexistent/scenario.yaml")
        assert proc.returncode == 1

    def test_run_nonexistent_prints_error(self) -> None:
        proc = _cli("run", "/nonexistent/scenario.yaml")
        output = proc.stdout + proc.stderr
        assert "not found" in output.lower() or "error" in output.lower()

    def test_run_invalid_yaml_exit_1(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(
            "project:\n  name: Test\n  discount_rate_nominal: not_a_float\n",
            encoding="utf-8",
        )
        proc = _cli("run", str(bad_yaml))
        assert proc.returncode == 1


# ---------------------------------------------------------------------------
# CliRunner unit tests — info command
# ---------------------------------------------------------------------------


class TestInfoCliRunner:
    """In-process CliRunner tests for ``info``."""

    def test_info_exit_code_0(self) -> None:
        result = runner.invoke(app, ["info"])
        assert result.exit_code == 0, result.output

    def test_info_output_contains_version(self) -> None:
        from samba._version import __version__

        result = runner.invoke(app, ["info"])
        assert __version__ in result.output

    def test_info_output_contains_samba_location(self) -> None:
        result = runner.invoke(app, ["info"])
        # Should contain a path to the samba package
        assert "samba" in result.output.lower()


# ---------------------------------------------------------------------------
# CliRunner unit tests — validate command
# ---------------------------------------------------------------------------


class TestValidateCliRunner:
    """In-process CliRunner tests for ``validate``."""

    def test_validate_valid_scenario_exit_0(self) -> None:
        result = runner.invoke(app, ["validate", str(BASE_SCENARIO)])
        assert result.exit_code == 0, result.output

    def test_validate_valid_scenario_output(self) -> None:
        result = runner.invoke(app, ["validate", str(BASE_SCENARIO)])
        assert "valid" in result.output.lower()

    def test_validate_nonexistent_exit_1(self) -> None:
        result = runner.invoke(app, ["validate", "/nonexistent/path.yaml"])
        assert result.exit_code == 1

    def test_validate_invalid_schema_exit_1(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(
            "project:\n  name: Test\n  discount_rate_nominal: not_a_float\n",
            encoding="utf-8",
        )
        result = runner.invoke(app, ["validate", str(bad_yaml)])
        assert result.exit_code == 1

    def test_validate_good_temp_yaml_exit_0(self, tmp_path: Path) -> None:
        good_yaml = tmp_path / "good.yaml"
        good_yaml.write_text(_minimal_scenario_yaml(), encoding="utf-8")
        result = runner.invoke(app, ["validate", str(good_yaml)])
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# CliRunner unit tests — run command (error paths)
# ---------------------------------------------------------------------------


class TestRunCliRunner:
    """In-process CliRunner tests for ``run`` (error paths, no solver)."""

    def test_run_nonexistent_file_exit_1(self) -> None:
        result = runner.invoke(app, ["run", "/nonexistent/scenario.yaml"])
        assert result.exit_code == 1

    def test_run_invalid_yaml_exit_1(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(
            "project:\n  name: Test\n  discount_rate_nominal: not_a_float\n",
            encoding="utf-8",
        )
        result = runner.invoke(app, ["run", str(bad_yaml)])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# CliRunner unit tests — formatting helpers
# ---------------------------------------------------------------------------


class TestFormatting:
    """Unit tests for samba_cli.formatting helpers."""

    def test_format_currency_usd(self) -> None:
        from samba_cli.formatting import format_currency

        assert format_currency(125432.0) == "$125,432"

    def test_format_currency_custom_symbol(self) -> None:
        from samba_cli.formatting import format_currency

        assert format_currency(1200.0, symbol="€") == "€1,200"

    def test_format_currency_zero(self) -> None:
        from samba_cli.formatting import format_currency

        assert format_currency(0.0) == "$0"

    def test_format_currency_nan(self) -> None:
        from samba_cli.formatting import format_currency

        assert format_currency(float("nan")) == "$?"

    def test_print_error_does_not_raise(self, capsys: pytest.CaptureFixture[str]) -> None:
        from samba_cli.formatting import print_error

        # Should not raise; output goes to console (captured by capsys)
        print_error("Test Title", "Test detail message")

    def test_print_validation_errors_does_not_raise(self) -> None:
        from samba_cli.formatting import print_validation_errors

        print_validation_errors(["field.name: some error", "field.other: another"])
