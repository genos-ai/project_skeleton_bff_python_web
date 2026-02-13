"""
Unit Tests for Pagination Utilities.

Tests the pagination helpers and utilities.
"""

import pytest
from unittest.mock import MagicMock

from modules.backend.core.pagination import (
    PaginationParams,
    PagedResult,
    create_paginated_response,
    decode_cursor,
    encode_cursor,
    paginate_query,
)


class TestCursorEncoding:
    """Tests for cursor encoding/decoding."""

    def test_encode_string_value(self):
        """Should encode string values."""
        cursor = encode_cursor("abc-123")
        assert cursor is not None
        assert isinstance(cursor, str)

    def test_encode_int_value(self):
        """Should encode integer values."""
        cursor = encode_cursor(12345)
        assert cursor is not None

    def test_decode_cursor(self):
        """Should decode encoded cursor back to original value."""
        original = "my-unique-id"
        encoded = encode_cursor(original)
        decoded = decode_cursor(encoded)
        assert decoded == original

    def test_decode_int_cursor(self):
        """Should decode integer cursor as string."""
        original = 12345
        encoded = encode_cursor(original)
        decoded = decode_cursor(encoded)
        assert decoded == str(original)

    def test_decode_invalid_cursor_raises(self):
        """Should raise ValueError for invalid cursor."""
        with pytest.raises(ValueError, match="Invalid cursor"):
            decode_cursor("not-valid-base64!!!")

    def test_roundtrip_preserves_value(self):
        """Should preserve value through encode/decode cycle."""
        values = ["uuid-123", "special/chars+test", "12345", ""]
        for value in values:
            encoded = encode_cursor(value)
            decoded = decode_cursor(encoded)
            assert decoded == value


class TestPaginationParams:
    """Tests for PaginationParams dataclass."""

    def test_is_cursor_based_with_cursor(self):
        """Should return True when cursor is set."""
        params = PaginationParams(limit=20, offset=0, cursor="abc")
        assert params.is_cursor_based is True

    def test_is_cursor_based_without_cursor(self):
        """Should return False when cursor is None."""
        params = PaginationParams(limit=20, offset=0, cursor=None)
        assert params.is_cursor_based is False


class TestCreatePaginatedResponse:
    """Tests for create_paginated_response function."""

    def test_creates_valid_response_structure(self):
        """Should create response with correct structure."""
        from pydantic import BaseModel

        class ItemSchema(BaseModel):
            id: str
            name: str

        items = [{"id": "1", "name": "Item 1"}, {"id": "2", "name": "Item 2"}]

        response = create_paginated_response(
            items=items,
            item_schema=ItemSchema,
            total=10,
            limit=2,
            offset=0,
        )

        assert response["success"] is True
        assert response["data"] is not None
        assert len(response["data"]) == 2
        assert "pagination" in response
        assert "metadata" in response

    def test_includes_pagination_info(self):
        """Should include correct pagination info."""
        from pydantic import BaseModel

        class ItemSchema(BaseModel):
            id: str

        response = create_paginated_response(
            items=[{"id": "1"}],
            item_schema=ItemSchema,
            total=100,
            limit=20,
            offset=40,
        )

        pagination = response["pagination"]
        assert pagination["total"] == 100
        assert pagination["limit"] == 20
        assert pagination["has_more"] is True

    def test_has_more_false_at_end(self):
        """Should set has_more to False when at end of results."""
        from pydantic import BaseModel

        class ItemSchema(BaseModel):
            id: str

        response = create_paginated_response(
            items=[{"id": "1"}],
            item_schema=ItemSchema,
            total=1,
            limit=20,
            offset=0,
        )

        assert response["pagination"]["has_more"] is False

    def test_includes_request_id(self):
        """Should include request_id in metadata."""
        from pydantic import BaseModel

        class ItemSchema(BaseModel):
            id: str

        response = create_paginated_response(
            items=[{"id": "1"}],
            item_schema=ItemSchema,
            request_id="test-request-123",
        )

        assert response["metadata"]["request_id"] == "test-request-123"

    def test_validates_items_through_schema(self):
        """Should validate items through provided schema."""
        from pydantic import BaseModel

        class ItemSchema(BaseModel):
            id: str
            name: str

        # Items with extra fields should be filtered by schema
        items = [{"id": "1", "name": "Test", "extra_field": "ignored"}]

        response = create_paginated_response(
            items=items,
            item_schema=ItemSchema,
        )

        # Extra field should not be in response
        assert "extra_field" not in response["data"][0]

    def test_handles_empty_items(self):
        """Should handle empty items list."""
        from pydantic import BaseModel

        class ItemSchema(BaseModel):
            id: str

        response = create_paginated_response(
            items=[],
            item_schema=ItemSchema,
            total=0,
        )

        assert response["data"] == []
        assert response["pagination"]["has_more"] is False


class TestPaginateQuery:
    """Tests for paginate_query function."""

    @pytest.mark.asyncio
    async def test_returns_paged_result(self):
        """Should return PagedResult with items."""
        items = [MagicMock(id="1"), MagicMock(id="2")]

        async def query_func(limit, offset):
            return items

        params = PaginationParams(limit=20, offset=0, cursor=None)
        result = await paginate_query(query_func, params)

        assert isinstance(result, PagedResult)
        assert len(result.items) == 2

    @pytest.mark.asyncio
    async def test_detects_has_more(self):
        """Should detect when there are more items."""
        # Return limit + 1 items to indicate more exist
        items = [MagicMock(id=str(i)) for i in range(21)]

        async def query_func(limit, offset):
            return items[:limit]

        params = PaginationParams(limit=20, offset=0, cursor=None)
        result = await paginate_query(query_func, params)

        assert result.has_more is True
        assert len(result.items) == 20  # Should trim to limit

    @pytest.mark.asyncio
    async def test_no_more_when_under_limit(self):
        """Should set has_more False when under limit."""
        items = [MagicMock(id="1")]

        async def query_func(limit, offset):
            return items

        params = PaginationParams(limit=20, offset=0, cursor=None)
        result = await paginate_query(query_func, params)

        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_calls_count_func(self):
        """Should call count function when provided."""
        async def query_func(limit, offset):
            return []

        async def count_func():
            return 100

        params = PaginationParams(limit=20, offset=0, cursor=None)
        result = await paginate_query(query_func, params, count_func=count_func)

        assert result.total == 100

    @pytest.mark.asyncio
    async def test_generates_next_cursor(self):
        """Should generate next cursor when has_more."""
        items = [MagicMock(id=str(i)) for i in range(21)]

        async def query_func(limit, offset):
            return items[:limit]

        params = PaginationParams(limit=20, offset=0, cursor=None)
        result = await paginate_query(query_func, params)

        assert result.next_cursor is not None
        # Decode cursor should give last item's ID
        decoded = decode_cursor(result.next_cursor)
        assert decoded == "19"  # Last item in trimmed list
