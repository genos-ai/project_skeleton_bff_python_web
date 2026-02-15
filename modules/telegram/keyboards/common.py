"""
Common Keyboard Builders.

Reusable keyboard builders for common UI patterns.
"""

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from modules.telegram.callbacks.common import ActionCallback, PaginationCallback


def get_main_menu_keyboard(user_role: str = "viewer") -> ReplyKeyboardMarkup:
    """
    Build the main menu reply keyboard.

    Args:
        user_role: User's role for conditional buttons

    Returns:
        ReplyKeyboardMarkup with main menu options
    """
    builder = ReplyKeyboardBuilder()

    # Row 1: Common actions
    builder.button(text="📊 Status")
    builder.button(text="ℹ️ Info")

    # Row 2: Help and settings
    builder.button(text="❓ Help")
    builder.button(text="⚙️ Settings")

    # Row 3: Role-specific actions
    if user_role in ("trader", "admin"):
        builder.button(text="💰 Balance")
        builder.button(text="📜 History")

    if user_role == "admin":
        builder.button(text="👥 Users")
        builder.button(text="📋 Logs")

    # Adjust layout: 2 buttons per row
    builder.adjust(2)

    return builder.as_markup(
        resize_keyboard=True,
        input_field_placeholder="Choose an action...",
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """
    Build a simple cancel keyboard for FSM flows.

    Returns:
        ReplyKeyboardMarkup with cancel button
    """
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Cancel")

    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_confirmation_keyboard(action_id: str) -> InlineKeyboardMarkup:
    """
    Build a confirmation inline keyboard.

    Args:
        action_id: Identifier for the action being confirmed

    Returns:
        InlineKeyboardMarkup with confirm/cancel buttons
    """
    builder = InlineKeyboardBuilder()

    builder.button(
        text="✅ Confirm",
        callback_data=ActionCallback(action="confirm", action_id=action_id),
    )
    builder.button(
        text="❌ Cancel",
        callback_data=ActionCallback(action="cancel", action_id=action_id),
    )

    builder.adjust(2)

    return builder.as_markup()


def get_pagination_keyboard(
    list_type: str,
    current_page: int,
    total_pages: int,
    per_page: int = 10,
) -> InlineKeyboardMarkup:
    """
    Build a pagination inline keyboard.

    Args:
        list_type: Type of list being paginated
        current_page: Current page number (0-indexed)
        total_pages: Total number of pages
        per_page: Items per page

    Returns:
        InlineKeyboardMarkup with pagination controls
    """
    builder = InlineKeyboardBuilder()

    # Previous button
    if current_page > 0:
        builder.button(
            text="⬅️ Previous",
            callback_data=PaginationCallback(
                list_type=list_type,
                page=current_page - 1,
                per_page=per_page,
            ),
        )
    else:
        builder.button(text="⬅️", callback_data="noop")

    # Page indicator
    builder.button(
        text=f"{current_page + 1}/{total_pages}",
        callback_data="noop",
    )

    # Next button
    if current_page < total_pages - 1:
        builder.button(
            text="Next ➡️",
            callback_data=PaginationCallback(
                list_type=list_type,
                page=current_page + 1,
                per_page=per_page,
            ),
        )
    else:
        builder.button(text="➡️", callback_data="noop")

    builder.adjust(3)

    return builder.as_markup()


def get_yes_no_keyboard(action_id: str) -> InlineKeyboardMarkup:
    """
    Build a simple Yes/No inline keyboard.

    Args:
        action_id: Identifier for the action

    Returns:
        InlineKeyboardMarkup with Yes/No buttons
    """
    builder = InlineKeyboardBuilder()

    builder.button(
        text="👍 Yes",
        callback_data=ActionCallback(action="yes", action_id=action_id),
    )
    builder.button(
        text="👎 No",
        callback_data=ActionCallback(action="no", action_id=action_id),
    )

    builder.adjust(2)

    return builder.as_markup()


def get_back_keyboard(menu: str) -> InlineKeyboardMarkup:
    """
    Build a back button keyboard.

    Args:
        menu: Menu to return to

    Returns:
        InlineKeyboardMarkup with back button
    """
    from modules.telegram.callbacks.common import MenuCallback

    builder = InlineKeyboardBuilder()

    builder.button(
        text="⬅️ Back",
        callback_data=MenuCallback(menu=menu),
    )

    return builder.as_markup()
