from gettext import gettext as _
from typing import Union

from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram import types

from . import keyboards
from .models import Message, Chat


class Main(StatesGroup):
    main = State()
    messages = State()
    accounts = State()
    # groups = State()


class Messages(StatesGroup):
    list = State()
    create = State()
    detail = State()
    start_task = State()
    edit_text = State()
    edit_media = State()
    delete = State()


class Accounts(StatesGroup):
    list = State()
    upload = State()
    detail = State()


async def enter_menu(update=Union[types.Message, types.CallbackQuery]):
    await Main.main.set()
    msg = _('Welcome to <b>MsgBot</b>!')
    if isinstance(update, types.CallbackQuery):
        await update.message.edit_text(msg, reply_markup=keyboards.main())
        await update.answer()
    else:
        await update.answer(msg, reply_markup=keyboards.main())


async def messages(query: types.CallbackQuery):
    await Main.messages.set()
    msg = _('Messages')
    await query.message.edit_text(msg, reply_markup=keyboards.messages())
    await query.answer()


# async def message_detail(message: types.Message=None, query: types.CallbackQuery=None, message: Message):
#     await Messages.main.set()
#     msg_id = (await state.get_data())['msg_id']
#     msg = await Message.get(id=msg_id)
#     msg_name = msg.name
#     edit_text = msg.edit_text
#     edit_media = await msg.get_media()
#     if edit_media:
#         if type(edit_media) == list:
#             media_group = types.MediaGroup()
#             for item in edit_media:
#                 media_group.attach(await item.get_input_media(False))
#             msg = await query.message.answer_media_group(media_group)
#         else:
#             method = getattr(query.message, 'answer_' + edit_media.type.value)
#             msg = await method(edit_media.file_id, caption=edit_text)
#     else:
#         msg = await query.message.edit_text(edit_text)
#     await state.update_data(preview_id=msg.message_id)
#     reply_markup = keyboards.message_detail()
#     await query.message.answer(msg_name, reply_markup=reply_markup)
#     await query.answer()

# async def enter_group(update: Union[types.Message, types.CallbackQuery], msg=None):
#     await MessageDetail.start_task.set()
#     if not msg:
#         msg = _('Please send a link to join the group or its username for public groups.')
#     reply_markup = keyboards.back()
#     if await Chat.exists():
#         msg += _('\n\nOr select previously used group:')
#         reply_markup = await keyboards.groups()
#     await query.message.edit_text(msg, reply_markup=reply_markup)
#     await query.answer()