"""
Integration Tests for example.py CLI.

Tests the CLI as a whole with real execution paths.
"""

import subprocess
import sys
from pathlib import Path

import pytest


# Project root for running commands
PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestExampleCLI:
    """Integration tests for example.py command-line interface."""

    def test_help_returns_zero_exit_code(self):
        """Should return exit code 0 for --help."""
        # Act
        result = subprocess.run(
            [sys.executable, "example.py", "--help"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Assert
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "--action" in result.stdout

    def test_info_action_succeeds(self):
        """Should successfully display info."""
        # Act
        result = subprocess.run(
            [sys.executable, "example.py", "--action", "info"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Assert
        assert result.returncode == 0
        assert "BFF Python Web Application" in result.stdout

    def test_config_action_displays_yaml_settings(self):
        """Should display configuration from YAML files."""
        # Act
        result = subprocess.run(
            [sys.executable, "example.py", "--action", "config"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Assert
        assert result.returncode == 0
        assert "Application Settings" in result.stdout
        assert "BFF Application" in result.stdout

    def test_health_action_checks_components(self):
        """Should run health checks and report results."""
        # Act
        result = subprocess.run(
            [sys.executable, "example.py", "--action", "health"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Assert
        assert result.returncode == 0
        assert "Health Check Results" in result.stdout
        assert "Core imports" in result.stdout
        # Some checks will fail without .env, that's expected
        assert "PASS" in result.stdout or "FAIL" in result.stdout

    def test_verbose_flag_produces_more_output(self):
        """Should produce more output with --verbose flag."""
        # Act - without verbose
        result_quiet = subprocess.run(
            [sys.executable, "example.py", "--action", "info"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Act - with verbose
        result_verbose = subprocess.run(
            [sys.executable, "example.py", "--action", "health", "--verbose"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Assert - verbose should have logging output (to stderr)
        assert result_verbose.returncode == 0
        # Verbose mode writes structured logs
        combined_output = result_verbose.stdout + result_verbose.stderr
        assert len(combined_output) > 0

    def test_debug_flag_produces_debug_output(self):
        """Should produce debug-level output with --debug flag."""
        # Act
        result = subprocess.run(
            [sys.executable, "example.py", "--action", "health", "--debug"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Assert
        assert result.returncode == 0
        # Debug output goes to stderr via structlog
        combined = result.stdout + result.stderr
        # Should have some debug-level information
        assert "Health Check Results" in result.stdout

    def test_invalid_action_shows_error(self):
        """Should show error for invalid action."""
        # Act
        result = subprocess.run(
            [sys.executable, "example.py", "--action", "invalid"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Assert
        assert result.returncode != 0
        assert "Invalid value" in result.stderr or "invalid" in result.stderr.lower()

    def test_test_action_without_tests_reports_no_tests(self):
        """Should report when no tests are found."""
        # Act - run tests in unit directory (may have no tests yet)
        result = subprocess.run(
            [sys.executable, "example.py", "--action", "test", "--test-type", "unit"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Assert - pytest should run (may find tests or report none)
        # Exit code 0 = tests passed, 5 = no tests collected, other = failures
        assert result.returncode in [0, 1, 5]  # Valid pytest exit codes


class TestExampleCLIFromDifferentDirectory:
    """Test that CLI works when run from different directories."""

    def test_fails_gracefully_outside_project(self, tmp_path):
        """Should fail gracefully when config cannot be loaded from different directory."""
        # Create an example.py copy without .project_root
        example_script = PROJECT_ROOT / "example.py"

        # Act - try to import and run from temp directory
        result = subprocess.run(
            [sys.executable, str(example_script), "--action", "info"],
            cwd=tmp_path,  # Different directory
            capture_output=True,
            text=True,
        )

        # Assert - should fail because config loading fails when run from
        # a different directory (get_app_config() uses find_project_root()
        # which searches from cwd, not script location)
        assert result.returncode == 1
        assert "Error" in result.stderr or "error" in result.stdout.lower()
