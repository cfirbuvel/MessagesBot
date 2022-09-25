import asyncio
import datetime
import enum
import logging
import random
from pprint import pprint

from faker import Faker
from pyrogram import Client
from pyrogram.enums import ChatType, ChatMembersFilter, UserStatus, ParseMode
from pyrogram.errors import UserDeactivatedBan, UsernameOccupied
from pyrogram.types import InputMediaPhoto, InputMediaAnimation, InputMediaVideo
# from pyrogram.raw import functions
from tortoise import timezone
from tortoise.exceptions import DoesNotExist
from tortoise.functions import Count
from tortoise.models import Q

from . import settings
from .bot import lock
from .models import Acc, Msg, MsgTask, Chat, MediaType
from .utils import tg_client, get_full_name


logger = logging.getLogger(__name__)


def user_valid(user):
    return not any([user.is_bot, user.is_deleted, user.is_support])


# async def init_client(client, acc):
    # try:
    #     me = await client.get_me()
    # except UserDeactivatedBan:
    #     logger.info(f'Acc {acc.name} is banned.')
    #     acc.status = Acc.Status.BANNED
    #     await acc.save()
    #     return
    # fake = Faker()
    # if not me.username:
    #     while True:
    #         username = fake.user_name()
    #         try:
    #             res = await client.set_username(username)
    #         except UsernameOccupied:
    #             continue
    #         break
    #     print('Set username: ', res)
    # if not me.first_name and not me.last_name:
    #     await client.update_profile(first_name=fake.first_name(), last_name=fake.last_name())
    # return True

# async def


async def acc_dispatcher():
    while True:
        try:
            task = await MsgTask.get(status=MsgTask.Status.ACTIVE)
        except DoesNotExist:
            await asyncio.sleep(10)
            continue
        today = timezone.now() - datetime.timedelta(hours=24)
        # TODO: Check if OFFLINE/ACTIVE is needed
        accounts = (await Acc.filter(status__in=[Acc.Status.ACTIVE, Acc.Status.OFFLINE])
                    .annotate(sent_today=Count('sent_messages', _filter=Q(sent_messages__created_at__gte=today)))
                    .order_by('sent_today'))
        for acc in accounts:
            client = Client(
                acc.name,
                settings.API_ID,
                settings.API_HASH,
                app_version='1.0',
                device_model=acc.device_model,
                system_version=acc.system_version,
                session_string=acc.session,
                in_memory=True
            )
            authed = await client.connect()
            if authed:
                try:
                    me = await client.get_me()
                except UserDeactivatedBan:
                    logger.info(f'Acc {acc.name} is banned.')
                    acc.status = Acc.Status.BANNED
                else:
                    client.me = me
                    # break
            else:
                logger.info(f'Acc {acc.name} auth failed.')
                acc.status = Acc.Status.NOT_AUTHED
            await acc.save()
            await client.disconnect()

            fake = Faker()
            if not me.username:
                while True:
                    username = fake.user_name()
                    try:
                        res = await client.set_username(username)
                    except UsernameOccupied:
                        continue
                    break
                print('Set username: ', res)
            if not me.first_name and not me.last_name:
                await client.update_profile(first_name=fake.first_name(), last_name=fake.last_name())
            try:
                msg_task = await MsgTask.get(status=MsgTask.Status.ACTIVE)
            except DoesNotExist:
                # No active task
                pass

            task = await MsgTask.get(status=MsgTask.Status.ACTIVE)
            chat_instance = await task.chat
            chat_id = chat_instance.identifier
            try:
                chat = await client.get_chat(chat_id)
            except ValueError:
                # TODO: Handle chat not found and other errors
                try:
                    # TODO: Add delay sync between accs
                    chat = await client.join_chat(chat_id)
                    # delay = random.randint(60, 120)
                    # await asyncio.sleep(delay)
                except Exception as e:
                    raise e
                print('CHAT JOINED')
            if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
                chat_instance.status = Chat.Status.INVALID_TYPE
                await chat_instance.save()
                # send bot msg
                print('CHAT INVALID TYPE: ', chat.type)
                return
            # if first:
    #     async for member in client.get_chat_members(chat.id):
    #         user = member.user
    #         if user_valid(user):  # and user_filter(user):
    #             users_count += 1
    #     first = False
    # task = asyncio.create_task(client_task(client, acc, chat, msg, users))
    # tasks.append(task)
    # break
    # msg = await msg_task.msg
    # media = await msg.get_media()
    # media_map = {
    #     MediaType.PHOTO: InputMediaPhoto, MediaType.VIDEO: InputMediaVideo, MediaType.ANIMATION: InputMediaAnimation
    # }
    # async for member in client.get_chat_members(chat.id):
    #     print()
    #     user = member.user
    #     if user_valid(user):  # and user_filter(user):
    #         user_id = user.id
    #         text = msg.text
    #         if text:
    #             name = user.username or get_full_name(user)
    #             text = text.replace('{username}', name)
    #         if media:
    #             if type(media) == list:
    #                 media_group = []
    #                 for item in media:
    #                     input_media = media_map[item.type](item.filepath, caption=text, parse_mode=ParseMode.MARKDOWN)
    #                     media_group.append(input_media)
    #                 messages = await client.send_media_group(user_id, media_group)
    #                 print('MEDIA GROUP SENT')
    #                 for m in messages:
    #                     print(m)
    #             else:
    #                 method = getattr(client, 'send_{}'.format(media.type.value.lower()))
    #                 # print(method)
    #                 message = await method(user_id, media.filepath, caption=text, parse_mode=ParseMode.MARKDOWN)
    #                 # message = await client.send_photo(user_id, media.filepath, caption=text, parse_mode=ParseMode.MARKDOWN)
    #                 print('{} SENT'.format(media.type))
    #                 print(message)
    #         else:
    #             message = await client.send_message(user_id, text, parse_mode=ParseMode.MARKDOWN)
    #             print('MESSAGE SENT')
    #             print(message)
    #         users.append(user_id)
    #         acc.invites -= 1
    #         if not acc.invites:
    #             print('ACC INVITES EXHAUSTED')
    #             break
    #         delay = random.randint(60, 180)
    #         await asyncio.sleep(delay)



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


async def client_task(client, acc, chat, msg, users):
    media = await msg.get_media()
    media_map = {
        MediaType.PHOTO: InputMediaPhoto, MediaType.VIDEO: InputMediaVideo, MediaType.ANIMATION: InputMediaAnimation
    }
    try:
        async for member in client.get_chat_members(chat.id):
            print()
            user = member.user
            if user_valid(user):  # and user_filter(user):
                user_id = user.id
                text = msg.text
                if text:
                    name = user.username or get_full_name(user)
                    text = text.replace('{username}', name)
                if media:
                    if type(media) == list:
                        media_group = []
                        for item in media:
                            input_media = media_map[item.type](item.filepath, caption=text, parse_mode=ParseMode.MARKDOWN)
                            media_group.append(input_media)
                        messages = await client.send_media_group(user_id, media_group)
                        print('MEDIA GROUP SENT')
                        for m in messages:
                            print(m)
                    else:
                        method = getattr(client, 'send_{}'.format(media.type.value.lower()))
                        # print(method)
                        message = await method(user_id, media.filepath, caption=text, parse_mode=ParseMode.MARKDOWN)
                        # message = await client.send_photo(user_id, media.filepath, caption=text, parse_mode=ParseMode.MARKDOWN)
                        print('{} SENT'.format(media.type))
                        print(message)
                else:
                    message = await client.send_message(user_id, text, parse_mode=ParseMode.MARKDOWN)
                    print('MESSAGE SENT')
                    print(message)
                users.append(user_id)
                acc.invites -= 1
                if not acc.invites:
                    print('ACC INVITES EXHAUSTED')
                    break
                delay = random.randint(60, 180)
                await asyncio.sleep(delay)
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
    except Exception as ex:
        raise ex
    except asyncio.CancelledError:
        pass
    finally:
        acc.updated_at = timezone.now()
        await acc.save()
        await client.disconnect()


#     # chat_id = 'https://t.me/BestWeedCenter'
# TODO: Set status "WORKING" or like that if allowing to send multiple messages
# TODO: leave from chats if there's 500 limit reached
# async def spam_it(chat_id, message='Hello World!', filters=None, limit=None):
async def send_message(task_obj: MsgTask):
    chat_obj = await task_obj.chat
    msg = await task_obj.message
    # daily_limit = task_obj.daily_limit
    daily_limit = 500
    # user_filter = Filter.HEBREW
    Faker.seed(13)
    day_ago = timezone.now() - datetime.timedelta(hours=24)
    accounts = await Acc.filter(Q(status__in=(Acc.Status.OFFLINE, Acc.Status.ACTIVE)),
                                Q(invites__gt=0) | Q(updated_at__lte=day_ago)).order_by('status')
    accounts = iter(accounts)
    logger.info('Init accounts')
    chat_id = chat_obj.identifier
    users = set()
    tasks = []
    first = True
    users_count = 0
    for acc in accounts:
        if acc.updated_at <= day_ago:
            acc.invites = acc.generate_invites_num()
            acc.updated_at = timezone.now()
            await acc.save()
        client = Client(
            acc.name,
            settings.API_ID,
            settings.API_HASH,
            app_version='1.0',
            device_model=acc.device_model,
            system_version=acc.system_version,
            session_string=acc.session,
            in_memory=True
        )
        is_authed = await client.connect()
        if is_authed:
            try:
                me = await client.get_me()
            except UserDeactivatedBan:
                logger.info(f'Acc {acc.name} is banned.')
                acc.status = Acc.Status.BANNED
                await acc.save()
                # return
            else:
                fake = Faker()
                if not me.username:
                    while True:
                        username = fake.user_name()
                        try:
                            res = await client.set_username(username)
                        except UsernameOccupied:
                            continue
                        break
                    print('Set username: ', res)
                if not me.first_name and not me.last_name:
                    await client.update_profile(first_name=fake.first_name(), last_name=fake.last_name())
                client.me = me
                try:
                    chat = await client.get_chat(chat_id)
                except ValueError:
                    chat = await client.join_chat(chat_id)
                    print('CHAT JOINED')
                if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
                    chat_obj.status = Chat.Status.INVALID_TYPE
                    await chat_obj.save()
                    # send bot msg
                    raise Exception
                    # return
                if first:
                    async for member in client.get_chat_members(chat.id):
                        user = member.user
                        if user_valid(user):  # and user_filter(user):
                            users_count += 1
                    first = False
                # print('ME:')
                # print(client.me)
                task = asyncio.create_task(client_task(client, acc, chat, msg, users))
                tasks.append(task)
                delay = random.randint(60, 120)
                await asyncio.sleep(delay)
                break
    await asyncio.gather(*tasks)
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
