"""
Unit tests for scheduled background tasks.

Tests task logic in isolation without requiring Redis.
Task functions are imported directly from the scheduled module,
bypassing the broker registration which requires Redis.
"""

import pytest

from modules.backend.tasks.scheduled import (
    daily_cleanup,
    hourly_health_check,
    weekly_report_generation,
    metrics_aggregation,
    SCHEDULED_TASKS,
)


class TestDailyCleanup:
    """Tests for daily_cleanup task."""

    @pytest.mark.asyncio
    async def test_daily_cleanup_returns_completion_status(self):
        """Task returns completion status with metadata."""
        result = await daily_cleanup(older_than_days=30)

        assert result["status"] == "completed"
        assert result["older_than_days"] == 30
        assert "tables_cleaned" in result
        assert "completed_at" in result

    @pytest.mark.asyncio
    async def test_daily_cleanup_default_retention(self):
        """Default retention is 30 days."""
        result = await daily_cleanup()

        assert result["older_than_days"] == 30

    @pytest.mark.asyncio
    async def test_daily_cleanup_custom_retention(self):
        """Custom retention period is respected."""
        result = await daily_cleanup(older_than_days=7)

        assert result["older_than_days"] == 7


class TestHourlyHealthCheck:
    """Tests for hourly_health_check task."""

    @pytest.mark.asyncio
    async def test_hourly_health_check_returns_status(self):
        """Task returns health check status."""
        result = await hourly_health_check()

        assert result["status"] in ("healthy", "degraded")
        assert "checks" in result
        assert "checked_at" in result

    @pytest.mark.asyncio
    async def test_hourly_health_check_includes_services(self):
        """Health check includes expected services."""
        result = await hourly_health_check()

        checks = result["checks"]
        assert "database" in checks
        assert "redis" in checks


class TestWeeklyReportGeneration:
    """Tests for weekly_report_generation task."""

    @pytest.mark.asyncio
    async def test_weekly_report_returns_status(self):
        """Task returns report generation status."""
        result = await weekly_report_generation()

        assert result["status"] == "completed"
        assert "reports_generated" in result
        assert "generated_at" in result

    @pytest.mark.asyncio
    async def test_weekly_report_generates_multiple_reports(self):
        """Multiple reports are generated."""
        result = await weekly_report_generation()

        assert len(result["reports_generated"]) > 0


class TestMetricsAggregation:
    """Tests for metrics_aggregation task."""

    @pytest.mark.asyncio
    async def test_metrics_aggregation_returns_status(self):
        """Task returns aggregation status."""
        result = await metrics_aggregation(interval_minutes=15)

        assert result["status"] == "completed"
        assert result["interval_minutes"] == 15
        assert "metrics_aggregated" in result
        assert "aggregated_at" in result

    @pytest.mark.asyncio
    async def test_metrics_aggregation_default_interval(self):
        """Default interval is 15 minutes."""
        result = await metrics_aggregation()

        assert result["interval_minutes"] == 15

    @pytest.mark.asyncio
    async def test_metrics_aggregation_custom_interval(self):
        """Custom interval is respected."""
        result = await metrics_aggregation(interval_minutes=5)

        assert result["interval_minutes"] == 5


class TestScheduledTasksConfiguration:
    """Tests for scheduled task configuration metadata."""

    def test_all_tasks_have_schedule(self):
        """All scheduled tasks have a schedule defined."""
        for task_name, config in SCHEDULED_TASKS.items():
            assert "schedule" in config, f"{task_name} missing schedule"
            assert len(config["schedule"]) > 0, f"{task_name} has empty schedule"

    def test_all_schedules_have_cron(self):
        """All schedules have a cron expression."""
        for task_name, config in SCHEDULED_TASKS.items():
            for schedule in config["schedule"]:
                assert "cron" in schedule, f"{task_name} schedule missing cron"

    def test_all_tasks_have_function(self):
        """All tasks have a function reference."""
        for task_name, config in SCHEDULED_TASKS.items():
            assert "function" in config, f"{task_name} missing function"
            assert callable(config["function"]), f"{task_name} function not callable"

    def test_all_tasks_have_description(self):
        """All tasks have descriptions."""
        for task_name, config in SCHEDULED_TASKS.items():
            assert "description" in config, f"{task_name} missing description"
            assert len(config["description"]) > 0

    def test_daily_cleanup_schedule(self):
        """daily_cleanup runs at 2 AM UTC."""
        config = SCHEDULED_TASKS["daily_cleanup"]
        assert config["schedule"][0]["cron"] == "0 2 * * *"

    def test_hourly_health_check_schedule(self):
        """hourly_health_check runs every hour."""
        config = SCHEDULED_TASKS["hourly_health_check"]
        assert config["schedule"][0]["cron"] == "0 * * * *"

    def test_weekly_report_schedule(self):
        """weekly_report_generation runs on Sunday at 6 AM."""
        config = SCHEDULED_TASKS["weekly_report_generation"]
        assert config["schedule"][0]["cron"] == "0 6 * * 0"

    def test_metrics_aggregation_schedule(self):
        """metrics_aggregation runs every 15 minutes."""
        config = SCHEDULED_TASKS["metrics_aggregation"]
        assert config["schedule"][0]["cron"] == "*/15 * * * *"

    def test_scheduled_tasks_no_retry_by_default(self):
        """Most scheduled tasks don't retry (run on next schedule instead)."""
        no_retry_tasks = ["daily_cleanup", "hourly_health_check", "metrics_aggregation"]
        for task_name in no_retry_tasks:
            config = SCHEDULED_TASKS[task_name]
            assert config.get("retry_on_error", False) is False

    def test_weekly_report_has_retry(self):
        """weekly_report_generation has retry enabled."""
        config = SCHEDULED_TASKS["weekly_report_generation"]
        assert config["retry_on_error"] is True
        assert config["max_retries"] == 2
