import functools
from gettext import gettext as _
from typing import Union

from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, ParseMode

from . import keyboards
from .models import Msg, Chat, MsgMedia


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
    settings = State()
    stats = State()
    edit_text = State()
    edit_media = State()
    delete = State()


class MsgSettings(StatesGroup):
    limit = State()
    filters = State()


class Accounts(StatesGroup):
    list = State()
    upload = State()
    detail = State()


def update_handler(reply=False):

    def decorator(func):

        @functools.wraps(func)
        async def wrapper(update, *args, **kwargs):
            kwargs = await func(update, *args, **kwargs)
            if kwargs:
                if isinstance(update, CallbackQuery):
                    await update.message.edit_text(**kwargs)
                    await update.answer()
                else:
                    await update.answer(**kwargs)
        return wrapper

    return decorator


@update_handler()
async def enter_menu(update=Union[Message, CallbackQuery]):
    await Main.main.set()
    msg = _('Welcome to <b>MsgBot</b>!')
    return dict(text=msg, reply_markup=keyboards.main())


@update_handler()
async def messages(query: CallbackQuery):
    await Main.messages.set()
    msg = _('Messages')
    return dict(text=msg, reply_markup=keyboards.messages())


@update_handler()
async def msg_settings(update, settings=None):
    msg = _('⚙️ Settings') + '\n\n' + settings.get_msg()
    return dict(text=msg, reply_markup=keyboards.message_settings())


@update_handler()
async def message_detail(update: Union[Message, CallbackQuery], state: FSMContext, msg: Msg = None):
    await Messages.detail.set()
    if not msg:
        data = await state.get_data()
        msg = await Msg.get(id=data['msg_id'])
    if await msg.has_content():
        text = msg.text
        media = await msg.get_media()
        # message = getattr(update, 'message', update)
        kwargs = {'parse_mode': ParseMode.MARKDOWN}
        if media:
            if text:
                kwargs['caption'] = text
            if type(media) == list:
                media_group = []
                for item in media:
                    input_class = item.bot_input_class
                    if not item.order:
                        item = input_class(item.file_id, **kwargs)
                    else:
                        item = input_class(item.file_id)
                    media_group.append(item)
                method = 'answer_media_group'
                args = (media_group,)
                kwargs = {}
                # kwargs = {'media': media_group}
            else:
                method = 'answer_{}'.format(media.type.value)
                args = (media.file_id,)
                # res = await getattr(message, 'answer_' + media.type.value)(media.file_id, **kwargs)
        else:
            method = 'answer'
            args = (text,)
            # res = await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        if type(update) == CallbackQuery:
            message = update.message
            await message.delete()
        else:
            message = update
        # res = await
        res = await getattr(message, method)(*args, **kwargs)
        preview = []
        if type(res) == list:
            for item in res:
                preview.append(item.message_id)
        else:
            preview.append(res.message_id)
        await state.update_data(msg_preview=preview)
        await message.answer(msg.name, reply_markup=keyboards.message_detail())
        if type(update) == CallbackQuery:
            await update.answer()
    else:
        return dict(msg.name, reply_markup=keyboards.message_detail())



# async def enter_group(update: Union[types.Msg, types.CallbackQuery], msg=None):
#     await MessageDetail.start_task.set()
#     if not msg:
#         msg = _('Please send a link to join the group or its username for public groups.')
#     reply_markup = keyboards.back()
#     if await Chat.exists():
#         msg += _('\n\nOr select previously used group:')
#         reply_markup = await keyboards.groups()
#     await query.message.edit_text(msg, reply_markup=reply_markup)
#     await query.answer()