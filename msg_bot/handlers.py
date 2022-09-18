import asyncio
from gettext import gettext as _
import io
import logging
import operator
import os
import re
import shutil
from typing import Union
import zipfile
from inspect import getmembers
from pprint import pprint

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text, Regexp
from aiogram.utils import markdown as md
import more_itertools
from tortoise.exceptions import DoesNotExist
from tortoise.transactions import in_transaction

from . import keyboards, settings, states
from .bot import dispatcher as dp
from .models import Account, MediaType, Message, MessageMedia, MessagesTask, Chat, UsersFilter
from .tasks import send_messages
from .utils import get_device_info, session_file_to_string
# from .states import Main, Messages, messages


logger = logging.getLogger(__name__)


@dp.message_handler(commands=['start'], state='*')
async def start(message: types.Message):
    await states.Main.main.set()
    msg = _('Welcome to <b>MsgBot</b>!')
    await message.answer(msg, reply_markup=keyboards.main())


@dp.callback_query_handler(Text('messages'), state=(states.Main.main, None))
async def messages(query: types.CallbackQuery, state: FSMContext):
    await states.Main.messages.set()
    await query.message.edit_text(_('Messages'), reply_markup=keyboards.messages())
    await query.answer()


@dp.callback_query_handler(Text('back'), state=states.Main.messages)
async def messages_back(query: types.CallbackQuery, state: FSMContext):
    await states.Main.main.set()
    msg = _('Welcome to <b>MsgBot</b>!')
    await query.message.edit_text(msg, reply_markup=keyboards.main())
    await query.answer()


@dp.callback_query_handler(Text('list'), state=states.Main.messages)
async def my_messages(query: types.CallbackQuery, state: FSMContext):
    await states.Messages.list.set()
    await state.update_data(page=0)
    # TODO: add indicator if message is sending right now
    reply_markup = await keyboards.messages_list()
    await query.message.edit_text(_('My messages'), reply_markup=reply_markup)
    await query.answer()


@dp.callback_query_handler(Regexp(r'^\d+$'), state=states.Messages.list)
async def select_message(query: types.CallbackQuery, state: FSMContext):
    msg_id = int(query.data)
    try:
        message = await Message.get(id=msg_id)
    except DoesNotExist:
        user_data = await state.get_data()
        reply_markup = await keyboards.messages_list(user_data['page'])
        await query.message.edit_reply_markup(reply_markup=reply_markup)
        await query.answer(_('Message not found!'))
        return
    await state.update_data(msg_id=msg_id)
    await states.Messages.detail.set()
    text = message.text
    media = await message.get_media()
    if media:
        await query.message.delete()
        if type(media) == list:
            media_group = types.MediaGroup()
            for item in media:
                media_group.attach(await item.get_input_media(False))
            msg = await query.message.answer_media_group(media_group)
        else:
            method = getattr(query.message, 'answer_' + media.type.value)
            msg = await method(media.file_id, caption=text, parse_mode=types.ParseMode.MARKDOWN)
        await state.update_data(preview_id=msg.message_id)
    elif text:
        msg = await query.message.edit_text(text, parse_mode=types.ParseMode.MARKDOWN)
        await state.update_data(preview_id=msg.message_id)
    reply_markup = keyboards.message_detail()
    await query.message.answer(message.name, reply_markup=reply_markup)
    await query.answer()


@dp.callback_query_handler(Text(['prev', 'next']), state=states.Messages.list)
async def my_messages_page(query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    page = data.get('page')
    op = operator.sub if query.data == 'prev' else operator.add
    page = op(page, 1)
    # TODO


@dp.callback_query_handler(Text('back'), state=states.Messages.list)
async def my_messages_back(query: types.CallbackQuery, state: FSMContext):
    await states.messages(query)


@dp.callback_query_handler(Text('create'), state=states.Main.messages)
async def create_message(query: types.CallbackQuery, state: FSMContext):
    await states.Messages.create.set()
    msg = _('Please enter the name of the message.')
    await query.message.edit_text(msg, reply_markup=keyboards.back())
    await query.answer()


@dp.message_handler(state=states.Messages.create)
async def message_name(message: types.Message, state: FSMContext):
    name = message.text
    try:
        await Message.get(name=name)
    except DoesNotExist:
        msg = await Message.create(name=name)
        await state.update_data(msg_id=msg.id)
        await states.Messages.detail.set()
        msg = _('Please enter message edit_text <i>and/or</i> send media.')
        await message.reply(msg, reply_markup=keyboards.message_detail())
    else:
        msg = _('Message with this name already exists. Please enter another name.')
        await message.reply(msg, reply_markup=keyboards.back())


@dp.callback_query_handler(Text('back'), state=states.Messages.create)
async def create_message_back(query: types.CallbackQuery, state: FSMContext):
    await states.messages(query)


@dp.callback_query_handler(Text('start'), state=states.Messages.detail)
async def start_task(query: types.CallbackQuery, state: FSMContext):
    await states.Messages.start_task.set()
    msg = _('Please send a link to join the group or its username for public groups.')
    reply_markup = keyboards.back()
    if await Chat.exists():
        msg += _('\n\nOr select previously used group:')
        reply_markup = await keyboards.chats()
    await query.message.edit_text(msg, reply_markup=reply_markup)
    await query.answer()


@dp.message_handler(state=states.Messages.start_task)
@dp.callback_query_handler(Regexp(r'^\d+$'), state=states.Messages.start_task)
async def task_group(update: Union[types.Message, types.CallbackQuery], state: FSMContext):
    is_query = type(update) == types.CallbackQuery
    if is_query:
        message = update.message
        chat = await Chat.get(id=int(update.data))
    else:
        message = update
        link = update.text
        match = re.match(r'^(https?://)?(?:t(?:elegram)?\.me/)?(?:joinchat/+)?\w+$', link)
        if not match:
            msg = _('Invalid link. Valid domains are t.me and telegram.me. Please try again.')
            reply_markup = keyboards.back()
            if await Chat.exists():
                msg += _('\n\nOr select previously used group:')
                reply_markup = await keyboards.chats()
            await message.reply(msg, reply_markup=reply_markup)
            return
        chat = await Chat.create(link=link)
    user_data = await state.get_data()
    msg = await Message.get(id=user_data['msg_id'])
    task = await MessagesTask.create(chat=chat, message=msg)
    await task.filters.add(await UsersFilter.get(name=UsersFilter.Type.RECENT))
    task_name = 'send_messages'
    task = asyncio.create_task(send_messages(task), name=task_name)
    await state.update_data(msgs_task=task_name)
    if is_query:
        await message.edit_text(_('Task started!'))
    else:
        await message.reply(_('Task started!'))
    await states.enter_menu(update)


@dp.callback_query_handler(Text('edit_text'), state=states.Messages.detail)
async def message_text(query: types.CallbackQuery, state: FSMContext):
    await states.Messages.edit_text.set()
    msg = ('Please, enter message text. You can include markdown.\n\n'
           'Message will start with "Hello {username}!" by default.\n'
           'To change it, add <code>{username}</code> anywhere in the text.')
    await query.message.edit_text(msg, reply_markup=keyboards.back())
    await query.answer()


@dp.message_handler(state=states.Messages.edit_text)
async def message_text_entered(message: types.Message, state: FSMContext):
    text = message.text
    if '{username}' not in text:
        text = 'Hello {username}!\n' + text
    if len(text) > 4096:
        await message.reply(_('Message is too long. Please enter another text.'))
        return
    await states.Messages.detail.set()
    msg_id = (await state.get_data())['msg_id']
    msg = await Message.get(id=msg_id)
    msg.text = message.text
    await msg.save()
    await states.Messages.detail.set()
    msg_name = msg.name
    text = msg.text
    media = await msg.get_media()
    if media:
        if type(media) == list:
            media_group = types.MediaGroup()
            for item in media:
                media_group.attach(await item.get_input_media(False))
            msg = await message.answer_media_group(media_group)
        else:
            method = getattr(message, 'answer_' + media.type.value)
            msg = await method(media.file_id, caption=text, parse_mode=types.ParseMode.MARKDOWN)
    else:
        msg = await message.answer(text, parse_mode=types.ParseMode.MARKDOWN)
    await state.update_data(preview_id=msg.message_id)
    reply_markup = keyboards.message_detail()
    await message.answer(msg_name, reply_markup=reply_markup)


@dp.callback_query_handler(Text('back'), state=states.Messages.detail)
async def message_text_back(query: types.CallbackQuery, state: FSMContext):
    await states.Messages.detail.set()
    msg_id = (await state.get_data())['msg_id']
    msg = await Message.get(id=msg_id)
    msg_name = msg.name
    text = msg.text
    media = await msg.get_media()
    if media:
        if type(media) == list:
            media_group = types.MediaGroup()
            for item in media:
                media_group.attach(await item.get_input_media(False))
            msg = await query.message.answer_media_group(media_group)
        else:
            method = getattr(query.message, 'answer_' + media.type.value)
            msg = await method(media.file_id, caption=text, parse_mode=types.ParseMode.MARKDOWN)
    else:
        msg = await query.message.edit_text(text, parse_mode=types.ParseMode.MARKDOWN)
    await state.update_data(preview_id=msg.message_id)
    reply_markup = keyboards.message_detail()
    await query.message.answer(msg_name, reply_markup=reply_markup)
    await query.answer()


@dp.callback_query_handler(Text('edit_media'), state=states.Messages.detail)
async def message_media(query: types.CallbackQuery, state: FSMContext):
    await states.Messages.edit_media.set()
    msg = _('Please send single photo or video, or multiple as media group.')
    await query.message.edit_text(msg, reply_markup=keyboards.back())
    await query.answer()


@dp.message_handler(content_types=MediaType.values(), state=states.Messages.edit_media)
async def message_media(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    try:
        msg = await Message.get(id=user_data['msg_id'])
    except DoesNotExist:
        await message.reply(_('Message not found!'))  # FIXME
        return
    await state.reset_state(with_data=False)
    await message.reply(_('Downloading media...'))
    # TODO: Add "Menu" bot button to not do shit here
    if message.media_group_id:
        data = user_data['media_group']
    else:
        data = [message]
    objects = []
    for order, message in enumerate(data):
        content_type = message.content_type
        media = getattr(message, content_type)
        if type(media) == list:
            media = media[-1]
        file = await media.get_file()
        file_id = file.file_id
        filepath = settings.MEDIA_ROOT / msg.name / (file_id + os.path.splitext(file.file_path)[1])
        await file.download(timeout=3000, destination_file=filepath)
        objects.append(MessageMedia(
            message=msg,
            type=content_type,
            file_id=file_id,
            filepath=filepath.absolute(),
            order=order
        ))
    async with in_transaction() as connection:
        await msg.media.all().delete()
        await MessageMedia.bulk_create(objects)
    # TODO: Msg main refresh
    msg_name = msg.name
    await message.answer(_('Media for <i>{}</i> saved.').format(msg.name))
    text = msg.text
    media = await msg.get_media()
    if media:
        if type(media) == list:
            media_group = types.MediaGroup()
            for item in media:
                media_group.attach(await item.get_input_media(False))
            msg = await message.answer_media_group(media_group)
        else:
            method = getattr(message, 'answer_' + media.type.value)
            msg = await method(media.file_id, caption=text, parse_mode=types.ParseMode.MARKDOWN)
    else:
        msg = await message.answer(text, parse_mode=types.ParseMode.MARKDOWN)
    await state.update_data(preview_id=msg.message_id)
    reply_markup = keyboards.message_detail()
    await message.answer(msg_name, reply_markup=reply_markup)


@dp.callback_query_handler(Text('back'), state=states.Messages.edit_media)
async def message_media_back(query: types.CallbackQuery, state: FSMContext):
    await states.Messages.detail.set()
    msg_id = (await state.get_data())['msg_id']
    msg = await Message.get(id=msg_id)
    msg_name = msg.name
    text = msg.text
    media = await msg.get_media()
    if media:
        if type(media) == list:
            media_group = types.MediaGroup()
            for item in media:
                media_group.attach(await item.get_input_media(False))
            msg = await query.message.answer_media_group(media_group)
        else:
            method = getattr(query.message, 'answer_' + media.type.value)
            msg = await method(media.file_id, caption=text)
    else:
        msg = await query.message.edit_text(text)
    await state.update_data(preview_id=msg.message_id)
    reply_markup = keyboards.message_detail()
    await query.message.answer(msg_name, reply_markup=reply_markup)
    await query.answer()


# @dp.callback_query_handler(Text(startswith='open_msg'), state='*')
# async def open_msg(query: types.CallbackQuery, state: FSMContext):
#     msg_id = int(query.data.split(':')[1])
#     msg = await Message.get(id=msg_id)
#     await query.message.edit_text(msg.edit_text, reply_markup=keyboards.message_detail())
#     await query.answer()

@dp.callback_query_handler(Text('accounts'), state=(states.Main.main, None))
async def accounts(query: types.CallbackQuery, state: FSMContext):
    await states.Main.accounts.set()
    await query.message.edit_text(_('Accounts'), reply_markup=keyboards.accounts())
    await query.answer()


@dp.callback_query_handler(Text('upload'), state=states.Main.accounts)
async def upload_accounts(query: types.CallbackQuery, state: FSMContext):
    await states.Accounts.upload.set()
    msg = _('Please upload <i>.zip</i> archive with session files or <i>.session</i> file.')
    await query.message.edit_text(msg, reply_markup=keyboards.back())
    await query.answer()


@dp.message_handler(content_types=types.ContentType.DOCUMENT, state=states.Accounts.upload)
async def upload_accounts_files(message: types.Message, state: FSMContext):
    document = message.document
    name, ext = os.path.splitext(document.file_name)
    if ext not in ('.zip', '.session'):
        msg = '🚫 Unsupported file format. Valid are: <b>.session</b>, <b>.zip</b>.'
        await message.reply(msg, reply_markup=keyboards.back())
        return
    sessions = {}
    temp_dir = settings.BASE_DIR / 'temp' / str(message.chat.id)
    if os.path.isdir(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)
    file = io.BytesIO()
    document = message.document
    if ext == '.zip':
        await document.download(destination_file=file)
        try:
            archive = zipfile.ZipFile(file)
        except zipfile.BadZipfile:
            msg = '🚫 Invalid file.\nPlease upload solid <b>.zip</b> archive.'
            await message.reply(msg, reply_markup=keyboards.back())
            return
        else:
            message = await message.answer('Creating accounts from sessions...')
            # task = asyncio.create_task(tasks.show_loading(message))  # TODO?
            archive.extractall(path=temp_dir)
            for dirpath, dirnames, filenames in os.walk(temp_dir):
                for filename in filenames:
                    phone, ext = os.path.splitext(filename)
                    if ext == '.session':
                        sessions[phone] = os.path.join(dirpath, filename)
            # task.cancel()
    elif ext == '.session':
        if await Account.filter(name=name).exists():
            msg = '🚫 This account already exists. Please upload another file.'
            await message.reply(msg, reply_markup=keyboards.back())
        else:
            file_path = os.path.join(temp_dir, document.file_name)
            await document.download(destination_file=file_path)
            sessions[name] = file_path
    created = 0
    exist = 0
    for i, data in enumerate(sessions.items()):
        name, filepath = data
        session = await session_file_to_string(filepath)
        if not await Account.filter(name=name).exists():
            device, system = get_device_info()
            await Account.create(
                name=name,
                session=session,
                device_model=device,
                system_version=system,
                invites=50,
            )
            created += 1
        else:
            exist += 1
    msg = '{} accounts exists been created.'.format(created)
    if exist:
        msg += '\n<i>{} accounts already exist.</i>'.format(exist)
    await message.answer(msg)
    shutil.rmtree(temp_dir)
    await states.Main.accounts.set()
    msg = _('Accounts')
    await message.answer(msg, reply_markup=keyboards.accounts())


@dp.callback_query_handler(Text('back'), state=states.Main.accounts)
async def accounts_back(query: types.CallbackQuery, state: FSMContext):
    await states.enter_menu(query)
