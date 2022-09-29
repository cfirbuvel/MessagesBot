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
from aiogram.utils.exceptions import MessageToDeleteNotFound, MessageCantBeDeleted
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text, Regexp
from aiogram.utils import markdown as md
import more_itertools
from tortoise.exceptions import DoesNotExist
from tortoise.transactions import in_transaction

from . import keyboards, settings, states
from .bot import dispatcher as dp
from .models import Acc, MediaType, Msg, MsgMedia, MsgTask, Chat, MsgSettings, UserFilter
# from .tasks import send_message
from .utils import get_device_info, session_file_to_string
# from .states import Main, Messages, messages


logger = logging.getLogger(__name__)


async def delete_msg_preview(state):
    async with state.proxy() as data:
        msg_ids = data.get('msg_preview')
        if msg_ids:
            bot = dp.bot
            chat_id = state.chat
            for msg_id in msg_ids:
                try:
                    await bot.delete_message(chat_id, msg_id)
                except (MessageToDeleteNotFound, MessageCantBeDeleted):
                    pass
            del data['msg_preview']


@dp.message_handler(commands=['start'], state='*')
async def start(message: types.Message):
    await states.main(message)


@dp.callback_query_handler(Text('messages'), state=(states.Main.main, None))
async def messages(query: types.CallbackQuery, state: FSMContext):
    await states.Main.messages.set()
    await query.message.edit_text(_('Messages'), reply_markup=keyboards.messages())
    await query.answer()


@dp.callback_query_handler(Text('back'), state=states.Main.messages)
async def messages_back(query: types.CallbackQuery, state: FSMContext):
    await states.main(query)


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
        msg = await Msg.get(id=msg_id)
    except DoesNotExist:
        user_data = await state.get_data()
        reply_markup = await keyboards.messages_list(user_data['page'])
        await query.message.edit_reply_markup(reply_markup=reply_markup)
        await query.answer(_('Msg not found!'))
        return
    await state.update_data(msg_id=msg_id)
    await states.message_detail(query, state, msg)


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
        await Msg.get(name=name)
    except DoesNotExist:
        await states.Messages.detail.set()
        msg_settings = await MsgSettings.create()
        msg = await Msg.create(name=name, settings=msg_settings)
        await state.update_data(msg_id=msg.id)
        msg = _('Please enter message text <i>and/or</i> send media.')
        await message.reply(msg, reply_markup=keyboards.message_detail())
    else:
        msg = _('Msg with this name already exists. Please enter another name.')
        await message.reply(msg, reply_markup=keyboards.back())


@dp.callback_query_handler(Text('back'), state=states.Messages.create)
async def create_message_back(query: types.CallbackQuery, state: FSMContext):
    await states.messages(query)


@dp.callback_query_handler(Text('start'), state=states.Messages.detail)
async def start_task(query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    message = await Msg.get(id=data['msg_id'])
    if not await message.has_content():
        await query.answer(_('Add text and/or media first.'))
        return
    await states.Messages.start_task.set()
    await delete_msg_preview(state)
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
        link = update.text.lower()
        match = re.match(r'^(https?://)?(?:t(?:elegram)?\.me/)?(?:joinchat/+)?\w+$', link)
        if not match:
            msg = _('Invalid link. Valid domains are https://t.me/ and https://telegram.me/. Please try again.')
            reply_markup = keyboards.back()
            if await Chat.exists():
                msg += _('\n\nOr select previously used group:')
                reply_markup = await keyboards.chats()
            await message.reply(msg, reply_markup=reply_markup, disable_web_page_preview=True)
            return
        if not match.groups()[0]:
            link = 'https://' + link
        # TODO: handle duplicate links in case it was changed in one
        # try:
        #     await Chat.get(link=link)
        chat = await Chat.create(link=link)
    user_data = await state.get_data()
    msg = await Msg.get(id=user_data['msg_id'])
    await MsgTask.filter(status=MsgTask.Status.ACTIVE).update(status=MsgTask.Status.CANCELED)
    msg_settings = await msg.settings
    task_settings = await MsgSettings.create(filters=msg_settings.filters, limit=msg_settings.limit)

    task = await MsgTask.create(chat=chat, msg=msg, settings=task_settings)
    # await task.filters.add(await UsersFilter.get(name=UsersFilter.Type.RECENT))
    # task_name = 'send_message'
    # task = asyncio.create_task(send_message(task), name=task_name)
    # await state.update_data(msgs_task=task_name)
    if is_query:
        await message.edit_text(_('Task started!'))
    else:
        await message.reply(_('Task started!'))
    await states.main(update)


@dp.callback_query_handler(Regexp(r'^task|\d+$'), state=(states.Messages.detail, states.Main.main, None))
async def task_detail(query: types.CallbackQuery, state: FSMContext):
    await states.Task.detail.set()
    await delete_msg_preview(state)
    task_id = int(query.data.split('|')[1])
    task = await MsgTask.get(id=task_id)
    await state.update_data(task_id=task_id)
    msg = await task.get_details_msg()
    await query.message.edit_text(msg, reply_markup=keyboards.task_detail(), disable_web_page_preview=True)
    await query.answer()

#TODO: Task detail handlers


@dp.callback_query_handler(Text('settings'), state=states.Messages.detail)
async def message_settings(query: types.CallbackQuery, state: FSMContext):
    await states.Messages.settings.set()
    await delete_msg_preview(state)
    data = await state.get_data()
    msg = await Msg.get(id=data['msg_id'])
    await states.msg_settings(query, await msg.settings)


@dp.callback_query_handler(Text('limit'), state=states.Messages.settings)
async def msg_limit(query: types.CallbackQuery, state: FSMContext):
    await states.MsgSettings.limit.set()
    msg = _('Please enter the number of messages to send daily.')
            # 'Enter 0 to set no limit.')
    await query.message.edit_text(msg, reply_markup=keyboards.back())
    await query.answer()


@dp.message_handler(state=states.MsgSettings.limit)
async def msg_limit_entered(message: types.Message, state: FSMContext):
    try:
        val = int(message.text)
    except ValueError:
        msg = _('Please enter a number.')
        await message.reply(msg, reply_markup=keyboards.back())
    else:
        await states.Messages.settings.set()
        data = await state.get_data()
        # msg = await Msg.get(id=data['msg_id'])
        msg_settings = await MsgSettings.get(msg__id=data['msg_id'])
        msg_settings.limit = max(1, val)
        await msg_settings.save()
        await states.msg_settings(message, msg_settings)


@dp.callback_query_handler(Text('back'), state=states.MsgSettings.limit)
async def msg_limit_back(query: types.CallbackQuery, state: FSMContext):
    await states.Messages.settings.set()
    data = await state.get_data()
    msg = await Msg.get(id=data['msg_id'])
    await states.msg_settings(query, await msg.settings)


@dp.callback_query_handler(Text('filters'), state=states.Messages.settings)
async def msg_filters(query: types.CallbackQuery, state: FSMContext):
    await states.MsgSettings.filters.set()
    data = await state.get_data()
    msg = await Msg.get(id=data['msg_id'])
    reply_markup = keyboards.filters(await msg.settings)
    msg = _('Please select filters to filter out users.')
    await query.message.edit_text(msg, reply_markup=reply_markup)
    await query.answer()


@dp.callback_query_handler(Text(UserFilter.names), state=states.MsgSettings.filters)
async def msg_filters_toggle(query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg = await Msg.get(id=data['msg_id'])
    msg_settings = await msg.settings
    val = UserFilter[query.data].value
    filters = msg_settings.filters
    try:
        filters.remove(val)
    except ValueError:
        filters.append(val)
    await msg_settings.save()
    reply_markup = keyboards.filters(msg_settings)
    await query.message.edit_reply_markup(reply_markup=reply_markup)
    await query.answer()


@dp.callback_query_handler(Text('back'), state=states.MsgSettings.filters)
async def msg_filters_back(query: types.CallbackQuery, state: FSMContext):
    await states.Messages.settings.set()
    data = await state.get_data()
    msg = await Msg.get(id=data['msg_id'])
    await states.msg_settings(query, await msg.settings)


@dp.callback_query_handler(Text('back'), state=states.Messages.settings)
async def msg_settings_back(query: types.CallbackQuery, state: FSMContext):
    await states.message_detail(query, state)


@dp.callback_query_handler(Text('edit_text'), state=states.Messages.detail)
async def message_text(query: types.CallbackQuery, state: FSMContext):
    await states.Messages.edit_text.set()
    await delete_msg_preview(state)
    msg = ('Please, enter message text. You can include markdown.\n\n'
           'Msg will start with "Hello {username}!" by default.\n'
           'To change it, add <code>{username}</code> anywhere in the text.')
    await query.message.edit_text(msg, reply_markup=keyboards.back())
    await query.answer()


@dp.message_handler(state=states.Messages.edit_text)
async def message_text_entered(message: types.Message, state: FSMContext):
    text = message.text
    if '{username}' not in text:
        text = 'Hello {username}!\n' + text
    if len(text) > 4096:
        await message.reply(_('Msg is too long. Please enter another text.'))
        return
    await state.reset_state(with_data=False)
    data = await state.get_data()
    msg = await Msg.get(id=data['msg_id'])
    msg.text = text
    await msg.save()
    await states.message_detail(message, state, msg)


@dp.callback_query_handler(Text('back'), state=states.Messages.edit_text)
async def message_text_back(query: types.CallbackQuery, state: FSMContext):
    await states.message_detail(query, state)


@dp.callback_query_handler(Text('edit_media'), state=states.Messages.detail)
async def message_media(query: types.CallbackQuery, state: FSMContext):
    await states.Messages.edit_media.set()
    await delete_msg_preview(state)
    msg = _('Please send single photo or video, or multiple as media group.')
    await query.message.edit_text(msg, reply_markup=keyboards.back())
    await query.answer()


@dp.message_handler(content_types=MediaType.values(), state=states.Messages.edit_media)
async def message_media(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    try:
        msg = await Msg.get(id=user_data['msg_id'])
    except DoesNotExist:
        await message.reply(_('Msg not found!'))  # FIXME
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
        objects.append(MsgMedia(
            msg=msg,
            type=content_type,
            file_id=file_id,
            filepath=filepath.absolute(),
            order=order
        ))
    async with in_transaction() as connection:
        await msg.media.all().using_db(connection).delete()
        await MsgMedia.bulk_create(objects)
    # TODO: Msg main refresh
    await message.answer(_('Media for <i>{}</i> saved.').format(msg.name))
    await states.message_detail(message, state, msg)


@dp.callback_query_handler(Text('back'), state=states.Messages.edit_media)
async def message_media_back(query: types.CallbackQuery, state: FSMContext):
    await states.message_detail(query, state)


@dp.callback_query_handler(Text('back'), state=states.Messages.detail)
async def message_detail_back(query: types.CallbackQuery, state: FSMContext):
    await states.Messages.list.set()
    data = await state.get_data()
    # TODO: add indicator if message is sending right now
    reply_markup = await keyboards.messages_list(data['page'])
    await query.message.edit_text(_('My messages'), reply_markup=reply_markup)
    await query.answer()


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
        if await Acc.filter(name=name).exists():
            msg = '🚫 This account already exists. Please upload another file.'
            await message.reply(msg, reply_markup=keyboards.back())
        else:
            file_path = os.path.join(temp_dir, document.file_name)
            await document.download(destination_file=file_path)
            sessions[name] = file_path
    created = 0
    exist = 0
    invalid = 0
    for i, data in enumerate(sessions.items()):
        name, filepath = data
        session = await session_file_to_string(filepath)
        if not session:
            invalid += 1
        elif not await Acc.filter(name=name).exists():
            device, system = get_device_info()
            await Acc.create(
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
    if invalid:
        msg += '\n<i>{} sessions are not valid.</i>'.format(invalid)
    await message.answer(msg)
    shutil.rmtree(temp_dir)
    await states.Main.accounts.set()
    msg = _('Accounts')
    await message.answer(msg, reply_markup=keyboards.accounts())


@dp.callback_query_handler(Text('back'), state=states.Main.accounts)
async def accounts_back(query: types.CallbackQuery, state: FSMContext):
    await states.main(query)
