import asyncio
import datetime
import logging
import random
from pprint import pprint

from faker import Faker
from pyrogram.enums import ChatType, ChatMembersFilter
from pyrogram.errors import UserDeactivatedBan, UsernameOccupied
from pyrogram.raw import functions

from . import settings
from .models import Account
from .utils import tg_client


logger = logging.getLogger(__name__)


# async def move_accs():
#     from motor.motor_asyncio import AsyncIOMotorClient
#     mongo = AsyncIOMotorClient(settings.MONGO_URL)
#     db = mongo[settings.MONGO_DATABASE]
#     accounts = db.accounts
#     items = accounts.find()
#     items = await items.to_list(length=None)
#     for doc in items:
#         await Account.create(
#             name=doc['name'],
#             session=doc['session'],
#             device_model=doc['device_model'],
#             system_version=doc['system_version'],
#             lang=doc['lang'],
#         )
#     print('Done')


async def init_client(client, acc):
    try:
        me = await client.get_me()
    except UserDeactivatedBan:
        logger.info(f'Account {acc.name} is banned.')
        acc.status = Account.Status.BANNED
        await acc.save()
        return
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
    return True


async def sender_worker(accounts, message, queue):
    for acc in accounts:
        async with tg_client(acc.name, acc.device_model, acc.system_version, acc.session) as client:
            if not await init_client(client, acc):
                continue
            limit = 50
            while limit:
                user = await queue.get()
                queue.task_done()
                user_id = user.id
                name = user.username or f'{user.first_name} {user.last_name}'
                msg = f'Hello {name}!\n{message}'
                try:
                    await client.send_message(user_id, msg)
                except Exception as e:
                    logger.exception(e)
                else:
                    limit -= 1
                    logger.info(f'Sent message to {user_id}, {limit} left')
                await asyncio.sleep(random.randint(60, 120))
                # queue.task_done()
            print('Done')
            break


# TODO: Set status "WORKING" or like that if allowing to send multiple messages
# TODO: leave from chats if there's 500 limit reached
# async def spam_it(chat_id, message='Hello World!', filters=None, limit=None):
async def spam_it():
    # chat_id = 'https://t.me/BestWeedCenter'
    chat_id = 'https://t.me/canex_A'
    message = 'I am as stupid as a piece of metal.'
    Faker.seed(13)
    accounts = await Account.filter(status=Account.Status.ACTIVE)
    accounts = iter(accounts)
    logger.info('Starting spamming')
    for acc in accounts:
        async with tg_client(acc.name, acc.device_model, acc.system_version, acc.session) as client:
            if not await init_client(client, acc):
                continue
            chat = await client.join_chat('BestWeedCenter')
            # print(chat)
            # return
            # chat = await client.join_chat(chat_id)
            if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
                # send bot msg
                return
            # tasks = []
            # queue = asyncio.Queue()
            # for _ in range(3):
            #     task = asyncio.create_task(sender_worker(accounts, message, queue))
            #     tasks.append(task)
            total_users = 0
            limit = 50
            async for member in client.get_chat_members(chat.id, filter=ChatMembersFilter.RECENT):
                total_users += 1
                user = member.user
                if not user.is_bot:
                    # await queue.put(user)
                    # await queue.join()
                    user_id = user.id
                    name = user.username or f'{user.first_name} {user.last_name}'
                    msg = f'Hello {name}!\n{message}'
                    try:
                        await client.send_message(user_id, msg)
                    except Exception as e:
                        logger.exception(e)
                    else:
                        limit -= 1
                        logger.info(f'Sent message to {user_id}, {limit} left')
                    if not limit:
                        break
                    await asyncio.sleep(random.randint(60, 120))



