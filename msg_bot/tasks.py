import asyncio
import datetime
import enum
import functools
import logging
import math
import operator
import random
from pprint import pprint

from faker import Faker
from pyrogram import Client
from pyrogram.enums import ChatType, ChatMembersFilter, UserStatus, ParseMode
from pyrogram.errors import (AuthKeyUnregistered, ChannelPublicGroupNa, ChannelInvalid, UserChannelsTooMuch,
                             UserDeactivatedBan,
                             UsernameOccupied)
from pyrogram.types import InputMediaPhoto, InputMediaAnimation, InputMediaVideo
# from pyrogram.raw import functions
from tortoise import timezone
from tortoise.exceptions import DoesNotExist
from tortoise.functions import Count
from tortoise.models import Q
from tortoise.transactions import in_transaction

from .models import Acc, Msg, MsgTask, Chat, MediaType, SentMsg, SentMedia, User
from .settings import API_ID, API_HASH
from .utils import tg_client, get_full_name


logger = logging.getLogger(__name__)


async def relative_sleep(secs):
    offset = round(secs / 4 * random.random(), 2)
    secs = random.choice((secs - offset, secs + offset))
    await asyncio.sleep(secs)


def user_valid(user, filters):
    return not any([user.is_bot, user.is_deleted, user.is_support]) and all(f.apply(user) for f in filters)


def safe_client(func):

    @functools.wraps(func)
    async def wrapper(client, acc, *args, **kwargs):
        try:
            return await func(client, acc, *args, **kwargs)
        except UserDeactivatedBan:
            logger.info(f'Acc {acc.name} is banned.')
            acc.status = Acc.Status.BANNED
            await acc.save()
        except asyncio.CancelledError:
            pass
        # acc.session = await client.export_session_string()
        # await acc.save()
        await client.disconnect()
    return wrapper


# Dispatcher is needed to be base for tasks, otherwise they will be garbage collected?
async def acc_dispatcher():
    watch_tasks = []
    msg_tasks = []
    while True:
        queryset = Acc.filter(status=Acc.Status.ACTIVE)
        # TODO: Check if OFFLINE/ACTIVE is needed
        try:
            msg_task = await MsgTask.get(status=MsgTask.Status.ACTIVE)
            today = timezone.now() - datetime.timedelta(hours=24)
            accounts = await queryset.annotate(sent_today=Count('sent_messages', _filter=Q(sent_messages__sent_at__gte=today))).order_by('sent_today')
            print('Got task: ', msg_task)
        except DoesNotExist:
            await asyncio.sleep(10)
            continue
        #     msg_task = None
        #     accounts = await queryset.filter(Q(users__blacklisted=False) | Q(users__deactivated=False)).prefetch_related('users')
            # if msg_task:
        # watchers = await queryset.filter(Q(users__blacklisted=False) | Q(users__deactivated=False)).prefetch_related('users')
        await msg_task.fetch_related('msg', 'chat', 'settings')
        task_settings = msg_task.settings
        limit = task_settings.limit
        avg_msgs = 47
        # chat_id = chat_instance.identifier
        lock = asyncio.Lock()
        tasks = []
        first = True
        for acc in iter(accounts):
            client = Client(
                acc.name,
                API_ID,
                API_HASH,
                app_version='1.0',
                device_model=acc.device_model,
                system_version=acc.system_version,
                session_string=acc.session,
                in_memory=True
            )
            authed = await client.connect()
            if not authed:
                logger.info(f'Acc {acc.name} auth failed.')
                acc.status = Acc.Status.NOT_AUTHED
                await acc.save()
                await client.disconnect()
                continue
            if first:
                client = await setup_client(client, acc, msg_task)
                if not client:
                    continue
                chat_obj = msg_task.chat
                count = 0
                async for member in client.get_chat_members(chat_obj.chat_id):
                    user = member.user
                    if user_valid(user, task_settings.user_filters):  # and user_filter(user):
                        count += 1
                if not limit or count < limit:
                    limit = count
                chat_obj.num_users = count
                await chat_obj.save()
                first = False
                msg_task = send_messages(client, acc, msg_task, lock)
            else:
                msg_task = client_task(client, acc, msg_task, lock)
            tasks.append(msg_task)
            break
        if len(tasks) == math.ceil(limit / avg_msgs):
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        # for acc in watchers:

        # try:
        #     task = await MsgTask.get(status=MsgTask.Status.ACTIVE)
        # except DoesNotExist:
        #     await asyncio.sleep(10)
        #     continue


@safe_client
async def setup_client(client, acc, task):
    await relative_sleep(5)
    try:
        me = await client.get_me()
    except AuthKeyUnregistered:
        logger.info(f'Acc {acc.name} auth failed.')
        acc.status = Acc.Status.NOT_AUTHED
        await acc.save()
        return
    await task.accounts.add(acc)
    # TODO: (Later) Add cloud password if not set (SensitiveChangeForbidden)
    fake = Faker(seed=acc.id)
    if not me.username:
        while True:
            await relative_sleep(40)
            username = fake.user_name() + str(random.randint(0, 1000))
            print('Set username: ', username)
            try:
                res = await client.set_username(username)
                break
            except UsernameOccupied:
                logger.info(f'Acc %s username %s is occupied.', acc.name, username)
        print('Set username: ', res)
    if not me.first_name and not me.last_name:
        await relative_sleep(15)
        await client.update_profile(first_name=fake.first_name(), last_name=fake.last_name())
    # TODO: Leave chats if 500 (premium?) limit hit (ChannelsTooMuch)
    await relative_sleep(20)
    client.me = me
    chat_obj = task.chat
    try:
        chat = await client.get_chat(chat_obj.identifier)
    except (ValueError, ChannelInvalid):
        # TODO: Handle chat not found and other errors
        try:
            # TODO: Add delay sync between accs
            chat = await client.join_chat(chat_obj.username)
            # delay = random.randint(60, 120)
            # await asyncio.sleep(delay)
        except Exception as e:
            raise e
    chat_obj.chat_id = chat.id
    chat_obj.name = chat.title
    await chat_obj.save()
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        chat_obj.status = Chat.Status.INVALID_TYPE
        await chat_obj.save()
        # send bot msg
        print('CHAT INVALID TYPE: ', chat.type)
        return
    return client


@safe_client
async def send_messages(client: Client, acc: Acc, task: MsgTask, lock: asyncio.Lock):
    # TODO: Session expired error
    msg = task.msg
    chat = task.chat
    task_settings = task.settings
    filters = task_settings.user_filters
    media = await msg.get_media()
    limit = random.randint(45, 50) - acc.sent_today
    while True:
        async for member in client.get_chat_members(chat.chat_id):
            user = member.user
            if user_valid(user, filters):
                user_id = user.id
                username = user.username
                first_name = user.first_name
                last_name = user.last_name
                text = msg.text
                # import time
                # start = time.time()
                # print('')
                # TODO: Check if can use set of added users instead of db
                async with lock:
                    try:
                        user_obj = await User.get(chat_id=user_id)
                    except DoesNotExist:
                        user_obj = User(chat_id=user_id)
                    else:
                                                   # or user.deactivated
                        if user_obj.blacklisted or (text and await user_obj.sent_messages.filter(Q(task=task) | Q(text=text))):
                            continue
                    user_obj.username = username
                    user_obj.first_name = first_name
                    user_obj.last_name = last_name
                    await user_obj.save()
                    kwargs = {}
                    if text:
                        name = username or get_full_name(user)
                        text = text.replace('{username}', name)
                        kwargs['parse_mode'] = ParseMode.MARKDOWN
                    if media:
                        if text:
                            kwargs['caption'] = text
                        # TODO: Store file id and do not reupload files every time (maybe send to saved messages)
                        if type(media) == list:
                            media_group = []
                            random.shuffle(media)
                            for item in media:
                                media_group.append(item.type.acc_input_class(item.filepath, **kwargs))
                                if kwargs:
                                    kwargs = {}
                            messages = await client.send_media_group(user_id, media_group)
                            print('MEDIA GROUP SENT TO:', user.username or get_full_name(user))
                            # for m in messages:
                            #     print(m)
                        else:
                            method = getattr(client, 'send_{}'.format(media.type.value))
                            # print(method)
                            message = await method(user_id, media.filepath, **kwargs)
                            # message = await client.send_photo(user_id, media.filepath, caption=text, parse_mode=ParseMode.MARKDOWN)
                            print('{} SENT'.format(media.type))
                            # print(message)
                    else:
                        message = await client.send_message(user_id, text, **kwargs)
                        print('MESSAGE SENT')
                    # users.append(user_id)
                    # acc.invites -= 1
                    sent_msg = await SentMsg.create(acc=acc, task=task, user=user_obj, text=msg.text)
                    for i, item in enumerate(media):
                        await SentMedia.create(sent_msg=sent_msg, type=item.type, file_id=item.file_id, filepath=item.filepath, order=i)
                limit -= 1
                if not limit:
                    print('ACC LIMIT EXHAUSTED')
                    break
                await relative_sleep(120)
        await asyncio.sleep(3600 * 24)


async def client_task(client, acc, task, lock):
    await setup_client(client, acc, task)
    await send_messages(client, acc, task, lock)



# async def acc_task(accounts):
#     for acc in accounts:
#         client = Client(
#             acc.name,
#             settings.API_ID,
#             settings.API_HASH,
#             app_version='1.0',
#             device_model=acc.device_model,
#             system_version=acc.system_version,
#             session_string=acc.session,
#             in_memory=True
#         )
#         authed = await client.connect()
#         if authed:
#             try:
#                 me = await client.get_me()
#             except UserDeactivatedBan:
#                 logger.info(f'Acc {acc.name} is banned.')
#                 acc.status = Acc.Status.BANNED
#             else:
#                 client.me = me
#                 break
#         else:
#             logger.info(f'Acc {acc.name} auth failed.')
#             acc.status = Acc.Status.NOT_AUTHED
#         await acc.save()
#         await client.disconnect()
#     fake = Faker()
#     if not me.username:
#         while True:
#             username = fake.user_name()
#             try:
#                 res = await client.set_username(username)
#             except UsernameOccupied:
#                 continue
#             break
#         print('Set username: ', res)
#     if not me.first_name and not me.last_name:
#         await client.update_profile(first_name=fake.first_name(), last_name=fake.last_name())
#     try:
#         msg_task = await MsgTask.get(status=MsgTask.Status.ACTIVE)
#     except DoesNotExist:
#         # No active task
#         pass
#
#     task = await MsgTask.get(status=MsgTask.Status.ACTIVE)
#     chat_instance = await task.chat
#     chat_id = chat_instance.identifier
#     try:
#         chat = await client.get_chat(chat_id)
#     except ValueError:
#         # TODO: Handle chat not found and other errors
#         try:
#             # TODO: Add delay sync between accs
#             chat = await client.join_chat(chat_id)
#             # delay = random.randint(60, 120)
#             # await asyncio.sleep(delay)
#         except Exception as e:
#             raise e
#         print('CHAT JOINED')
#     if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
#         chat_instance.status = Chat.Status.INVALID_TYPE
#         await chat_instance.save()
#         # send bot msg
#         print('CHAT INVALID TYPE: ', chat.type)
#         return
#     # if first:
#     #     async for member in client.get_chat_members(chat.id):
#     #         user = member.user
#     #         if user_valid(user):  # and user_filter(user):
#     #             users_count += 1
#     #     first = False
#     # task = asyncio.create_task(client_task(client, acc, chat, msg, users))
#     # tasks.append(task)
#     # break
#     msg = await msg_task.msg
#     media = await msg.get_media()
#     media_map = {
#         MediaType.PHOTO: InputMediaPhoto, MediaType.VIDEO: InputMediaVideo, MediaType.ANIMATION: InputMediaAnimation
#     }
#     async for member in client.get_chat_members(chat.id):
#         print()
#         user = member.user
#         if user_valid(user):  # and user_filter(user):
#             user_id = user.id
#             text = msg.text
#             if text:
#                 name = user.username or get_full_name(user)
#                 text = text.replace('{username}', name)
#             if media:
#                 if type(media) == list:
#                     media_group = []
#                     for item in media:
#                         input_media = media_map[item.type](item.filepath, caption=text, parse_mode=ParseMode.MARKDOWN)
#                         media_group.append(input_media)
#                     messages = await client.send_media_group(user_id, media_group)
#                     print('MEDIA GROUP SENT')
#                     for m in messages:
#                         print(m)
#                 else:
#                     method = getattr(client, 'send_{}'.format(media.type.value.lower()))
#                     # print(method)
#                     message = await method(user_id, media.filepath, caption=text, parse_mode=ParseMode.MARKDOWN)
#                     # message = await client.send_photo(user_id, media.filepath, caption=text, parse_mode=ParseMode.MARKDOWN)
#                     print('{} SENT'.format(media.type))
#                     print(message)
#             else:
#                 message = await client.send_message(user_id, text, parse_mode=ParseMode.MARKDOWN)
#                 print('MESSAGE SENT')
#                 print(message)
#             users.append(user_id)
#             acc.invites -= 1
#             if not acc.invites:
#                 print('ACC INVITES EXHAUSTED')
#                 break
#             delay = random.randint(60, 180)
#             await asyncio.sleep(delay)


    # chat_obj = await task_obj.chat
    # msg = await task_obj.message
    # # daily_limit = task_obj.daily_limit
    # daily_limit = 500
    # # user_filter = Filter.HEBREW
    # Faker.seed(13)
    # day_ago = timezone.now() - datetime.timedelta(hours=24)
    # accounts = await Acc.filter(Q(status__in=(Acc.Status.OFFLINE, Acc.Status.ACTIVE)),
    #                             Q(invites__gt=0) | Q(updated_at__lte=day_ago)).order_by('status')
    # accounts = iter(accounts)
    # logger.info('Init accounts')
    # chat_id = chat_obj.identifier
    # users = set()
    # tasks = []
    # first = True
    # users_count = 0
    # for acc in accounts:
    #     if acc.updated_at <= day_ago:
    #         acc.invites = acc.generate_invites_num()
    #         acc.updated_at = timezone.now()
    #         await acc.save()
    #     client = Client(
    #         acc.name,
    #         settings.API_ID,
    #         settings.API_HASH,
    #         app_version='1.0',
    #         device_model=acc.device_model,
    #         system_version=acc.system_version,
    #         session_string=acc.session,
    #         in_memory=True
    #     )
    #     is_authed = await client.connect()
    #     if is_authed:
    #         try:
    #             me = await client.get_me()
    #         except UserDeactivatedBan:
    #             logger.info(f'Acc {acc.name} is banned.')
    #             acc.status = Acc.Status.BANNED
    #             await acc.save()
    #             # return
    #         else:
    #             fake = Faker()
    #             if not me.username:
    #                 while True:
    #                     username = fake.user_name()
    #                     try:
    #                         res = await client.set_username(username)
    #                     except UsernameOccupied:
    #                         continue
    #                     break
    #                 print('Set username: ', res)
    #             if not me.first_name and not me.last_name:
    #                 await client.update_profile(first_name=fake.first_name(), last_name=fake.last_name())
    #             client.me = me
    #             try:
    #                 chat = await client.get_chat(chat_id)
    #             except ValueError:
    #                 chat = await client.join_chat(chat_id)
    #                 print('CHAT JOINED')
    #             if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
    #                 chat_obj.status = Chat.Status.INVALID_TYPE
    #                 await chat_obj.save()
    #                 # send bot msg
    #                 raise Exception
    #                 # return
    #             if first:
    #                 async for member in client.get_chat_members(chat.id):
    #                     user = member.user
    #                     if user_valid(user):  # and user_filter(user):
    #                         users_count += 1
    #                 first = False
    #             # print('ME:')
    #             # print(client.me)
    #             task = asyncio.create_task(client_task(client, acc, chat, msg, users))
    #             tasks.append(task)
    #             delay = random.randint(60, 120)
    #             await asyncio.sleep(delay)
    #             break
    # await asyncio.gather(*tasks)


# async def client_task(client, acc, chat, msg, users):
#     media = await msg.get_media()
#     media_map = {
#         MediaType.PHOTO: InputMediaPhoto, MediaType.VIDEO: InputMediaVideo, MediaType.ANIMATION: InputMediaAnimation
#     }
#     try:
#         async for member in client.get_chat_members(chat.id):
#             print()
#             user = member.user
#             if user_valid(user):  # and user_filter(user):
#                 user_id = user.id
#                 text = msg.text
#                 if text:
#                     name = user.username or get_full_name(user)
#                     text = text.replace('{username}', name)
#                 if media:
#                     if type(media) == list:type=item.type
#                         media_group = []
#                         for item in media:
#                             input_media = media_map[item.type](item.filepath, caption=text, parse_mode=ParseMode.MARKDOWN)
#                             media_group.append(input_media)
#                         messages = await client.send_media_group(user_id, media_group)
#                         print('MEDIA GROUP SENT')
#                         for m in messages:
#                             print(m)
#                     else:
#                         method = getattr(client, 'send_{}'.format(media.type.value.lower()))
#                         # print(method)
#                         message = await method(user_id, media.filepath, caption=text, parse_mode=ParseMode.MARKDOWN)
#                         # message = await client.send_photo(user_id, media.filepath, caption=text, parse_mode=ParseMode.MARKDOWN)
#                         print('{} SENT'.format(media.type))
#                         print(message)
#                 else:
#                     message = await client.send_message(user_id, text, parse_mode=ParseMode.MARKDOWN)
#                     print('MESSAGE SENT')
#                     print(message)
#                 users.append(user_id)
#                 acc.invites -= 1
#                 if not acc.invites:
#                     print('ACC INVITES EXHAUSTED')
#                     break
#                 delay = random.randint(60, 180)
#                 await asyncio.sleep(delay)
#     except Exception as ex:
#         raise ex
#     except asyncio.CancelledError:
#         pass
#     finally:
#         acc.updated_at = timezone.now()
#         await acc.save()
#         await client.disconnect()

        # for acc in accounts:
        #     async with tg_client(acc.name, acc.device_model, acc.system_version, acc.session) as client:
        #         if not await init_client(client, acc):
        #             continue
        #         limit = 50
        #         while limit:
        #             user = await queue.get()
        #             queue.task_done()
        #             user_id = user.id
        #             name = user.username or f'{user.first_name} {user.last_name}'
        #             msg = f'Hello {name}!\n{message}'
        #             try:
        #                 await client.send_message(user_id, msg)
        #             except Exception as ex:
        #                 logger.exception(ex)
        #             else:
        #                 limit -= 1
        #                 logger.info(f'Sent message to {user_id}, {limit} left')
        #             await asyncio.sleep(random.randint(60, 120))
        #             # queue.task_done()
        #         print('Done')
        #         break


#     # chat_id = 'https://t.me/BestWeedCenter'
# TODO: Set status "WORKING" or like that if allowing to send multiple messages
# TODO: leave from chats if there's 500 limit reached
# async def spam_it(chat_id, message='Hello World!', filters=None, limit=None):
# async def send_message(task_obj: MsgTask):
#     chat_obj = await task_obj.chat
#     msg = await task_obj.message
#     # daily_limit = task_obj.daily_limit
#     daily_limit = 500
#     # user_filter = Filter.HEBREW
#     Faker.seed(13)
#     day_ago = timezone.now() - datetime.timedelta(hours=24)
#     accounts = await Acc.filter(Q(status__in=(Acc.Status.OFFLINE, Acc.Status.ACTIVE)),
#                                 Q(invites__gt=0) | Q(updated_at__lte=day_ago)).order_by('status')
#     accounts = iter(accounts)
#     logger.info('Init accounts')
#     chat_id = chat_obj.identifier
#     users = set()
#     tasks = []
#     first = True
#     users_count = 0
#     for acc in accounts:
#         if acc.updated_at <= day_ago:
#             acc.invites = acc.generate_invites_num()
#             acc.updated_at = timezone.now()
#             await acc.save()
#         client = Client(
#             acc.name,
#             settings.API_ID,
#             settings.API_HASH,
#             app_version='1.0',
#             device_model=acc.device_model,
#             system_version=acc.system_version,
#             session_string=acc.session,
#             in_memory=True
#         )
#         is_authed = await client.connect()
#         if is_authed:
#             try:
#                 me = await client.get_me()
#             except UserDeactivatedBan:
#                 logger.info(f'Acc {acc.name} is banned.')
#                 acc.status = Acc.Status.BANNED
#                 await acc.save()
#                 # return
#             else:
#                 fake = Faker()
#                 if not me.username:
#                     while True:
#                         username = fake.user_name()
#                         try:
#                             res = await client.set_username(username)
#                         except UsernameOccupied:
#                             continue
#                         break
#                     print('Set username: ', res)
#                 if not me.first_name and not me.last_name:
#                     await client.update_profile(first_name=fake.first_name(), last_name=fake.last_name())
#                 client.me = me
#                 try:
#                     chat = await client.get_chat(chat_id)
#                 except ValueError:
#                     chat = await client.join_chat(chat_id)
#                     print('CHAT JOINED')
#                 if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
#                     chat_obj.status = Chat.Status.INVALID_TYPE
#                     await chat_obj.save()
#                     # send bot msg
#                     raise Exception
#                     # return
#                 if first:
#                     async for member in client.get_chat_members(chat.id):
#                         user = member.user
#                         if user_valid(user):  # and user_filter(user):
#                             users_count += 1
#                     first = False
#                 # print('ME:')
#                 # print(client.me)
#                 task = asyncio.create_task(client_task(client, acc, chat, msg, users))
#                 tasks.append(task)
#                 delay = random.randint(60, 120)
#                 await asyncio.sleep(delay)
#                 break
#     await asyncio.gather(*tasks)


            # await client.disconnect()
            # continue


        # # async with tg_client(acc.name, acc.device_model, acc.system_version, acc.session) as client:
        #     if not await init_client(client, acc):
        #         continue
        #     # chat_id = chat_obj.identifier
        #     # chat_id = 'https://t.me/+uCn6rUtgJnliZWMy'
        #     chat_id = chat_obj.identifier
        #
        #             # users.add(user)
        #     print('USERS:')
        #     pprint(users)
        #     print('\n\nHEBREW USERS:')
        #     pprint(hebrew_users)
        #     return
        #     # tasks = []
        #     # queue = asyncio.Queue()
        #     # for _ in range(3):
        #     #     task = asyncio.create_task(sender_worker(accounts, message, queue))
        #     #     tasks.append(task)
        #     total_users = 0
        #     limit = 50
        #     async for member in client.get_chat_members(chat.id, filter=ChatMembersFilter.RECENT):
        #         total_users += 1
        #         user = member.user
        #         if not user.is_bot:
        #             # await queue.put(user)
        #             # await queue.join()
        #             user_id = user.id
        #             name = user.username or f'{user.first_name} {user.last_name}'
        #             msg = f'Hello {name}!\n{message}'
        #             try:
        #                 await client.send_message(user_id, msg)
        #             except Exception as e:
        #                 logger.exception(e)
        #             else:
        #                 limit -= 1
        #                 logger.info(f'Sent message to {user_id}, {limit} left')
        #             if not limit:
        #                 break
        #             await asyncio.sleep(random.randint(60, 120))
        #
        #
        #
