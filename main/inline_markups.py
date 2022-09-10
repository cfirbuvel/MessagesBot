import asyncio
import functools
from gettext import gettext as _  # TODO: lazy

from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton as B


def inline_markup(func):

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return InlineKeyboardMarkup(func(*args, **kwargs))
    return wrapper


@inline_markup
def main():
    return [
        [B(_('Messages'), 'menu_msgs')],
        # [B(_('Groups'), callback_data='groups')],
        [B(_('Run!'), callback_data='run')],
    ]


@inline_markup
def messages():
    return [
        [B(_('My messages'), callback_data='msgs_my')],
        [B(_('Create'), 'msgs_create')],
        [B(_('Back'), 'msgs_back')]
    ]


@inline_markup
def back(prefix=None):
    callback_data = f'{prefix}_back' if prefix else 'back'
    return [
        [B(_('Back'), callback_data)]
    ]

