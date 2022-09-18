import base64
from contextlib import asynccontextmanager
import random
import struct

import aiosqlite
from faker import Faker
from pyrogram import Client
from pyrogram.types import Message
# from tortoise import Tortoise

from . import settings


@asynccontextmanager
async def tg_client(name, device_model, system_version, session_string=None):
    client = Client(
        name,
        settings.API_ID,
        settings.API_HASH,
        app_version='1.0',
        device_model=device_model,
        system_version=system_version,
        session_string=session_string,
        in_memory=True
    )
    try:
        await client.connect()
        yield client
    finally:
        await client.disconnect()


async def session_file_to_string(filepath):
    async with aiosqlite.connect(filepath) as db:
        try:
            c = await db.execute('select * from sessions')
        except aiosqlite.OperationalError:
            raise
            return
        row = await c.fetchone()
        row_len = len(row)
        if row_len:
            print(row)
            if row_len == 6:
                dc_id, test_mode, auth_key, date, user_id, is_bot = row
            elif row_len == 5:
                dc_id, ip, port, auth_key, takeout_id = row
                test_mode = 0
                user_id = 0
                is_bot = 0
                # self._server_adderss = ipaddress.ip_address(ip).compressed
                # self._loaded = True
                # conn.close()
            user_id = user_id or 999999999
            is_bot = is_bot or 0
            return base64.urlsafe_b64encode(struct.pack(">B?256sI?", dc_id, test_mode, auth_key, int(user_id), int(is_bot),)).decode().rstrip("=")


def get_device_info():
    fake = Faker(seed=random.random() * 1000)
    methods = ['ios_platform_token', 'mac_platform_token']
    method = random.choice(methods)
    info = getattr(fake, method)()
    # TODO: Store devices together with session accs in db (STABILITY!)
    device, system = (item.strip() for item in info.rsplit(';', 1))
    return device, system
