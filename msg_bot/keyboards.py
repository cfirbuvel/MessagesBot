import asyncio
import functools
from gettext import gettext as _  # TODO: lazy
import inspect
from operator import attrgetter, itemgetter

# from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton as B
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton as B
# from aiogram.utils.parts import paginate

from .models import Message, Chat


def inline_markup(func):

    def wrapper_logic(val):
        return InlineKeyboardMarkup(inline_keyboard=val)

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if asyncio.iscoroutinefunction(func):
            async def coro():
                return wrapper_logic(await func(*args, **kwargs))
            return coro()
        else:
            return wrapper_logic(func(*args, **kwargs))
    return wrapper


# def reverted(func):
#
#     @functools.wraps(func)
#     def wrapper(*args, **kwargs):
#         rows = func(*args, **kwargs)
#         rows.append([B(_('Back'), callback_data='back')])
#         return rows
#
#     return wrapper


# def back_btn():
#     return [B(_('Back'), callback_data='back')]
BACK_BTN = B(_('🠈 Back'), callback_data='back')  # 🔙↩️◀️🡄🢀⯇⮜❮


# def back_btn(as_row=True):
#     res = B(_('Back'), callback_data='back')
#     if as_row:
#         res = [res]
#     return res


@inline_markup
def main():
    return [
        [B(_('✉️ Messages'), callback_data='messages')],
        [B(_('🤖 Accounts'), callback_data='accounts')],
        # [B(_('Groups'), callback_data='groups')],
        [BACK_BTN]
    ]


@inline_markup
def messages():
    return [
        [B(_('🗂 My messages'), callback_data='list')],
        [B(_('✏️ Create'), callback_data='create')],
        [BACK_BTN]
    ]


@inline_markup
def message_detail(msg: Message=None):
    return [
        [B(_('▶️ Start task'), callback_data='start')],
        [B(_('🧾 Stats'), callback_data='stats')],
        [B(_('🎫 Filters'), callback_data='filters')],
        [B(_('📋 Edit text'), callback_data='edit_text')],
        [B(_('📷 Edit media'), callback_data='edit_media')],
        [B(_('🚫 Delete'), callback_data='delete')],
        [BACK_BTN]
    ]


# @inline_markup
# def open_msg(msg_id):
#     return [
#         [B(_('Open message'), callback_data=f'open_msg:{msg_id}')],
#     ]


@inline_markup
def accounts():
    return [
        [B(_('🗂 My accounts'), callback_data='list')],
        [B(_('💾 Upload'), callback_data='upload')],
    ]


@inline_markup
def back():
    return [
        [BACK_BTN]
    ]


def pager(page):
    return [
        B(_('⏪ Prev'), callback_data='prev'),
        B(_('Page {}').format(page + 1), callback_data='null'),
        B(_('Next ⏩'), callback_data='next')
    ]


async def paginate_queryset(queryset,  page=1, per_page=15):
    paginated = False
    count = await queryset.count()
    if count > per_page:
        queryset = queryset.offset((page - 1) * per_page).limit(per_page)  # TODO: check
        paginated = True
    items = await queryset
    return items, paginated


@inline_markup
async def messages_list(page=0):
    queryset = Message.all().only('id', 'name')
    items, paginated = await paginate_queryset(queryset, page=page)
    keyboard = [[B(item.name, callback_data=str(item.id))] for item in items]
    if paginated:
        keyboard.append(pager(page))
    keyboard.append([BACK_BTN])
    return keyboard


@inline_markup
async def chats(page=0):
    queryset = Chat.all()
    items, paginated = await paginate_queryset(queryset, page=page)
    keyboard = []
    for group in items:
        text = str(group)
        num_users = group.num_users
        if num_users is not None:
            text = '{} ({})'.format(text, num_users)
        keyboard.append([B(text, callback_data=str(group.id))])
    if paginated:
        keyboard.append(pager(page))
    keyboard.append([BACK_BTN])
    return keyboard
