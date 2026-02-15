"""
Unit tests for Telegram keyboard builders.

Tests keyboard construction and button layout.
"""

import pytest


class TestMainMenuKeyboard:
    """Tests for main menu keyboard builder."""

    def test_returns_reply_keyboard(self):
        """Test that function returns a ReplyKeyboardMarkup."""
        from aiogram.types import ReplyKeyboardMarkup

        from modules.telegram.keyboards.common import get_main_menu_keyboard

        keyboard = get_main_menu_keyboard()
        assert isinstance(keyboard, ReplyKeyboardMarkup)

    def test_viewer_role_has_basic_buttons(self):
        """Test that viewer role gets basic buttons."""
        from modules.telegram.keyboards.common import get_main_menu_keyboard

        keyboard = get_main_menu_keyboard(user_role="viewer")

        # Flatten all button texts
        button_texts = [btn.text for row in keyboard.keyboard for btn in row]

        assert "📊 Status" in button_texts
        assert "ℹ️ Info" in button_texts
        assert "❓ Help" in button_texts
        assert "⚙️ Settings" in button_texts

    def test_trader_role_has_trading_buttons(self):
        """Test that trader role gets trading buttons."""
        from modules.telegram.keyboards.common import get_main_menu_keyboard

        keyboard = get_main_menu_keyboard(user_role="trader")
        button_texts = [btn.text for row in keyboard.keyboard for btn in row]

        assert "💰 Balance" in button_texts
        assert "📜 History" in button_texts

    def test_admin_role_has_admin_buttons(self):
        """Test that admin role gets admin buttons."""
        from modules.telegram.keyboards.common import get_main_menu_keyboard

        keyboard = get_main_menu_keyboard(user_role="admin")
        button_texts = [btn.text for row in keyboard.keyboard for btn in row]

        assert "👥 Users" in button_texts
        assert "📋 Logs" in button_texts

    def test_resize_keyboard_enabled(self):
        """Test that resize_keyboard is enabled."""
        from modules.telegram.keyboards.common import get_main_menu_keyboard

        keyboard = get_main_menu_keyboard()
        assert keyboard.resize_keyboard is True


class TestCancelKeyboard:
    """Tests for cancel keyboard builder."""

    def test_returns_reply_keyboard(self):
        """Test that function returns a ReplyKeyboardMarkup."""
        from aiogram.types import ReplyKeyboardMarkup

        from modules.telegram.keyboards.common import get_cancel_keyboard

        keyboard = get_cancel_keyboard()
        assert isinstance(keyboard, ReplyKeyboardMarkup)

    def test_has_cancel_button(self):
        """Test that keyboard has cancel button."""
        from modules.telegram.keyboards.common import get_cancel_keyboard

        keyboard = get_cancel_keyboard()
        button_texts = [btn.text for row in keyboard.keyboard for btn in row]

        assert "❌ Cancel" in button_texts

    def test_one_time_keyboard(self):
        """Test that one_time_keyboard is enabled."""
        from modules.telegram.keyboards.common import get_cancel_keyboard

        keyboard = get_cancel_keyboard()
        assert keyboard.one_time_keyboard is True


class TestConfirmationKeyboard:
    """Tests for confirmation keyboard builder."""

    def test_returns_inline_keyboard(self):
        """Test that function returns an InlineKeyboardMarkup."""
        from aiogram.types import InlineKeyboardMarkup

        from modules.telegram.keyboards.common import get_confirmation_keyboard

        keyboard = get_confirmation_keyboard("test_action")
        assert isinstance(keyboard, InlineKeyboardMarkup)

    def test_has_confirm_and_cancel_buttons(self):
        """Test that keyboard has confirm and cancel buttons."""
        from modules.telegram.keyboards.common import get_confirmation_keyboard

        keyboard = get_confirmation_keyboard("test_action")
        button_texts = [btn.text for row in keyboard.inline_keyboard for btn in row]

        assert "✅ Confirm" in button_texts
        assert "❌ Cancel" in button_texts

    def test_callback_data_includes_action_id(self):
        """Test that callback data includes the action ID."""
        from modules.telegram.callbacks.common import ActionCallback
        from modules.telegram.keyboards.common import get_confirmation_keyboard

        keyboard = get_confirmation_keyboard("my_action_123")

        # Get the confirm button's callback data
        confirm_btn = keyboard.inline_keyboard[0][0]
        callback_data = ActionCallback.unpack(confirm_btn.callback_data)

        assert callback_data.action_id == "my_action_123"


class TestPaginationKeyboard:
    """Tests for pagination keyboard builder."""

    def test_returns_inline_keyboard(self):
        """Test that function returns an InlineKeyboardMarkup."""
        from aiogram.types import InlineKeyboardMarkup

        from modules.telegram.keyboards.common import get_pagination_keyboard

        keyboard = get_pagination_keyboard("items", 0, 5)
        assert isinstance(keyboard, InlineKeyboardMarkup)

    def test_first_page_has_disabled_previous(self):
        """Test that first page has disabled previous button."""
        from modules.telegram.keyboards.common import get_pagination_keyboard

        keyboard = get_pagination_keyboard("items", current_page=0, total_pages=5)
        buttons = keyboard.inline_keyboard[0]

        # First button should be disabled (callback_data = "noop")
        assert buttons[0].callback_data == "noop"

    def test_last_page_has_disabled_next(self):
        """Test that last page has disabled next button."""
        from modules.telegram.keyboards.common import get_pagination_keyboard

        keyboard = get_pagination_keyboard("items", current_page=4, total_pages=5)
        buttons = keyboard.inline_keyboard[0]

        # Last button should be disabled
        assert buttons[2].callback_data == "noop"

    def test_middle_page_has_both_buttons_active(self):
        """Test that middle page has both navigation buttons active."""
        from modules.telegram.keyboards.common import get_pagination_keyboard

        keyboard = get_pagination_keyboard("items", current_page=2, total_pages=5)
        buttons = keyboard.inline_keyboard[0]

        # Both buttons should have real callback data
        assert buttons[0].callback_data != "noop"
        assert buttons[2].callback_data != "noop"

    def test_page_indicator_shows_correct_page(self):
        """Test that page indicator shows correct page number."""
        from modules.telegram.keyboards.common import get_pagination_keyboard

        keyboard = get_pagination_keyboard("items", current_page=2, total_pages=5)
        buttons = keyboard.inline_keyboard[0]

        # Middle button is page indicator (1-indexed display)
        assert "3/5" in buttons[1].text
