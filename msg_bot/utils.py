from contextlib import asynccontextmanager
import random

from faker import Faker
from pyrogram import Client
from pyrogram.types  import Message

from . import settings


def get_device_info():
    fake = Faker()
    methods = ['ios_platform_token', 'mac_platform_token']
    method = random.choice(methods)
    info = getattr(fake, method)()
    # TODO: Store devices together with session accs in db (STABILITY!)
    device, system = (item.strip() for item in info.rsplit(';', 1))
    return device, system


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


