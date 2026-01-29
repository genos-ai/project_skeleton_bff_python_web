"""
Unit Tests for run.py Entry Script.

Tests individual functions with mocked dependencies.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from click.testing import CliRunner

# Import after path setup
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from run import main, validate_project_root


class TestValidateProjectRoot:
    """Tests for validate_project_root function."""

    def test_validate_project_root_succeeds_when_marker_exists(self, tmp_path):
        """Should return path when .project_root exists."""
        # Arrange
        marker = tmp_path / ".project_root"
        marker.touch()

        # Act & Assert
        with patch("run.PROJECT_ROOT", tmp_path):
            result = validate_project_root()
            assert result == tmp_path

    def test_validate_project_root_exits_when_marker_missing(self, tmp_path):
        """Should exit with error when .project_root is missing."""
        # Arrange - tmp_path has no .project_root

        # Act & Assert
        with patch("run.PROJECT_ROOT", tmp_path):
            with pytest.raises(SystemExit) as exc_info:
                validate_project_root()
            assert exc_info.value.code == 1


class TestMainCLI:
    """Tests for main CLI entry point."""

    @pytest.fixture
    def runner(self):
        """Create Click test runner."""
        return CliRunner()

    def test_help_displays_usage(self, runner):
        """Should display help text with --help."""
        # Act
        result = runner.invoke(main, ["--help"])

        # Assert
        assert result.exit_code == 0
        assert "BFF Application Entry Point" in result.output
        assert "--action" in result.output
        assert "--verbose" in result.output
        assert "--debug" in result.output

    def test_info_action_displays_app_info(self, runner):
        """Should display application info with --action info."""
        # Act
        result = runner.invoke(main, ["--action", "info"])

        # Assert
        assert result.exit_code == 0
        assert "BFF Python Web Application" in result.output
        assert "Available Actions:" in result.output

    def test_verbose_flag_sets_info_logging(self, runner):
        """Should configure INFO level logging with --verbose."""
        # Arrange
        with patch("run.setup_logging") as mock_setup:
            with patch("run.validate_project_root"):
                # Act
                runner.invoke(main, ["--action", "info", "--verbose"])

        # Assert
        mock_setup.assert_called_once()
        call_kwargs = mock_setup.call_args[1] if mock_setup.call_args[1] else {}
        call_args = mock_setup.call_args[0] if mock_setup.call_args[0] else ()
        # Check level is INFO (could be positional or keyword)
        assert "INFO" in str(mock_setup.call_args)

    def test_debug_flag_sets_debug_logging(self, runner):
        """Should configure DEBUG level logging with --debug."""
        # Arrange
        with patch("run.setup_logging") as mock_setup:
            with patch("run.validate_project_root"):
                # Act
                runner.invoke(main, ["--action", "info", "--debug"])

        # Assert
        mock_setup.assert_called_once()
        assert "DEBUG" in str(mock_setup.call_args)

    def test_config_action_displays_configuration(self, runner):
        """Should display YAML configuration with --action config."""
        # Act - use real config since it's available
        result = runner.invoke(main, ["--action", "config"])

        # Assert
        assert result.exit_code == 0
        assert "Application Settings" in result.output
        assert "BFF Application" in result.output

    def test_health_action_runs_checks(self, runner):
        """Should run health checks with --action health."""
        # Act
        result = runner.invoke(main, ["--action", "health"])

        # Assert
        assert result.exit_code == 0
        assert "Health Check Results" in result.output
        assert "Core imports" in result.output

    def test_invalid_action_shows_error(self, runner):
        """Should show error for invalid action value."""
        # Act
        result = runner.invoke(main, ["--action", "invalid"])

        # Assert
        assert result.exit_code != 0
        assert "Invalid value" in result.output


class TestCLIOptions:
    """Tests for CLI option combinations."""

    @pytest.fixture
    def runner(self):
        """Create Click test runner."""
        return CliRunner()

    def test_server_options_are_available(self, runner):
        """Should accept server-related options."""
        # Act
        result = runner.invoke(main, ["--help"])

        # Assert
        assert "--host" in result.output
        assert "--port" in result.output
        assert "--reload" in result.output

    def test_test_options_are_available(self, runner):
        """Should accept test-related options."""
        # Act
        result = runner.invoke(main, ["--help"])

        # Assert
        assert "--test-type" in result.output
        assert "--coverage" in result.output

    def test_short_flags_work(self, runner):
        """Should accept short flag versions."""
        # Act - use -v for verbose
        result = runner.invoke(main, ["-v", "--action", "info"])

        # Assert
        assert result.exit_code == 0

        # Act - use -d for debug
        result = runner.invoke(main, ["-d", "--action", "info"])

        # Assert
        assert result.exit_code == 0


class TestActionBehavior:
    """Tests for specific action behaviors."""

    @pytest.fixture
    def runner(self):
        """Create Click test runner."""
        return CliRunner()

    def test_info_shows_examples(self, runner):
        """Should show usage examples in info output."""
        # Act
        result = runner.invoke(main, ["--action", "info"])

        # Assert
        assert "python run.py" in result.output
        assert "Examples:" in result.output

    def test_config_shows_all_sections(self, runner):
        """Should show all configuration sections."""
        # Act
        result = runner.invoke(main, ["--action", "config"])

        # Assert
        assert "Application Settings" in result.output
        assert "Database Settings" in result.output
        assert "Logging Settings" in result.output
        assert "Feature Flags" in result.output

    def test_health_shows_pass_fail_status(self, runner):
        """Should show pass/fail status for each check."""
        # Act
        result = runner.invoke(main, ["--action", "health"])

        # Assert
        # Should have either PASS or FAIL indicators
        assert "PASS" in result.output or "FAIL" in result.output
        assert "---" in result.output  # Separator line
