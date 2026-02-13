"""
Unit tests for example background tasks.

Tests task logic in isolation without requiring Redis.
Task functions are imported directly from the example module,
bypassing the broker registration which requires Redis.
"""

import pytest

from modules.backend.tasks.example import (
    send_notification,
    process_data,
    cleanup_expired_records,
    generate_report,
    TASK_CONFIG,
)


class TestSendNotification:
    """Tests for send_notification task."""

    @pytest.mark.asyncio
    async def test_send_notification_returns_delivery_status(self):
        """Task returns delivery status with metadata."""
        result = await send_notification(
            user_id="user-123",
            message="Test message",
            channel="email",
        )

        assert result["status"] == "delivered"
        assert result["user_id"] == "user-123"
        assert result["channel"] == "email"
        assert "sent_at" in result

    @pytest.mark.asyncio
    async def test_send_notification_default_channel_is_email(self):
        """Default channel is email."""
        result = await send_notification(
            user_id="user-123",
            message="Test message",
        )

        assert result["channel"] == "email"

    @pytest.mark.asyncio
    async def test_send_notification_supports_different_channels(self):
        """Task supports different notification channels."""
        for channel in ["email", "sms", "push"]:
            result = await send_notification(
                user_id="user-123",
                message="Test",
                channel=channel,
            )
            assert result["channel"] == channel


class TestProcessData:
    """Tests for process_data task."""

    @pytest.mark.asyncio
    async def test_process_data_transform_operation(self):
        """Transform operation uppercases string values."""
        result = await process_data(
            data={"key": "value", "name": "test"},
            operation="transform",
        )

        assert result["status"] == "completed"
        assert result["operation"] == "transform"
        assert result["result"]["key"] == "VALUE"
        assert result["result"]["name"] == "TEST"

    @pytest.mark.asyncio
    async def test_process_data_validate_operation(self):
        """Validate operation returns validation result."""
        result = await process_data(
            data={"field1": "value1", "field2": "value2"},
            operation="validate",
        )

        assert result["status"] == "completed"
        assert result["operation"] == "validate"
        assert result["result"]["valid"] is True
        assert "field1" in result["result"]["fields_checked"]
        assert "field2" in result["result"]["fields_checked"]

    @pytest.mark.asyncio
    async def test_process_data_aggregate_operation(self):
        """Aggregate operation returns count and keys."""
        result = await process_data(
            data={"a": 1, "b": 2, "c": 3},
            operation="aggregate",
        )

        assert result["status"] == "completed"
        assert result["operation"] == "aggregate"
        assert result["result"]["count"] == 3
        assert set(result["result"]["keys"]) == {"a", "b", "c"}

    @pytest.mark.asyncio
    async def test_process_data_unknown_operation_returns_original(self):
        """Unknown operation returns original data."""
        original_data = {"key": "value"}
        result = await process_data(
            data=original_data,
            operation="unknown",
        )

        assert result["status"] == "completed"
        assert result["result"] == original_data

    @pytest.mark.asyncio
    async def test_process_data_includes_timing_metadata(self):
        """Result includes timing metadata."""
        result = await process_data(
            data={"key": "value"},
            operation="transform",
        )

        assert "started_at" in result
        assert "completed_at" in result
        assert "duration_ms" in result
        assert result["duration_ms"] >= 0


class TestCleanupExpiredRecords:
    """Tests for cleanup_expired_records task."""

    @pytest.mark.asyncio
    async def test_cleanup_returns_completion_status(self):
        """Cleanup task returns completion status."""
        result = await cleanup_expired_records(
            table_name="test_table",
            older_than_days=30,
        )

        assert result["status"] == "completed"
        assert result["table_name"] == "test_table"
        assert result["older_than_days"] == 30
        assert "deleted_count" in result
        assert "completed_at" in result

    @pytest.mark.asyncio
    async def test_cleanup_default_retention_is_30_days(self):
        """Default retention period is 30 days."""
        result = await cleanup_expired_records(table_name="test_table")

        assert result["older_than_days"] == 30


class TestGenerateReport:
    """Tests for generate_report task."""

    @pytest.mark.asyncio
    async def test_generate_report_returns_report_metadata(self):
        """Report generation returns metadata."""
        result = await generate_report(
            report_type="monthly_summary",
            parameters={"month": "2024-01"},
            user_id="user-123",
        )

        assert result["status"] == "completed"
        assert result["report_type"] == "monthly_summary"
        assert result["user_id"] == "user-123"
        assert "report_id" in result
        assert "file_path" in result
        assert "generated_at" in result

    @pytest.mark.asyncio
    async def test_generate_report_id_includes_type_and_timestamp(self):
        """Report ID includes type and timestamp."""
        result = await generate_report(
            report_type="sales",
            parameters={},
            user_id="user-123",
        )

        assert "sales" in result["report_id"]
        assert result["report_id"].startswith("report_")

    @pytest.mark.asyncio
    async def test_generate_report_file_path_format(self):
        """File path follows expected format."""
        result = await generate_report(
            report_type="inventory",
            parameters={},
            user_id="user-123",
        )

        assert result["file_path"].startswith("/reports/")
        assert result["file_path"].endswith(".pdf")


class TestTaskConfiguration:
    """Tests for task configuration metadata."""

    def test_send_notification_has_retry_config(self):
        """send_notification is configured with retries."""
        config = TASK_CONFIG["send_notification"]
        assert config["retry_on_error"] is True
        assert config["max_retries"] == 3

    def test_process_data_has_retry_config(self):
        """process_data is configured with retries."""
        config = TASK_CONFIG["process_data"]
        assert config["retry_on_error"] is True
        assert config["max_retries"] == 2

    def test_cleanup_has_no_retry(self):
        """cleanup_expired_records does not retry."""
        config = TASK_CONFIG["cleanup_expired_records"]
        assert config["retry_on_error"] is False
        assert config["max_retries"] == 0

    def test_generate_report_has_retry_config(self):
        """generate_report is configured with retries."""
        config = TASK_CONFIG["generate_report"]
        assert config["retry_on_error"] is True
        assert config["max_retries"] == 1

    def test_all_tasks_have_descriptions(self):
        """All tasks have descriptions."""
        for task_name, config in TASK_CONFIG.items():
            assert "description" in config, f"{task_name} missing description"
            assert len(config["description"]) > 0
