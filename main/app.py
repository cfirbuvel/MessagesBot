import asyncio
import logging.config

from pyrogram import Client
import uvloop
from main import settings


logging.config.dictConfig(settings.LOGGING)


if __name__ == '__main__':
    uvloop.install()
    plugins = {
        'root': 'main',
        'include': ['handlers']
    }
    app = Client(
        'tg_spam_bot',
        api_id=settings.API_ID,
        api_hash=settings.API_HASH,
        app_version='1.0',
        device_model='PC',
        system_version='Pop!_OS 22.04 LTS',
        # lang_code='en'  # TODO: i18n
        bot_token=settings.BOT_TOKEN,
        # session_string=,
        # in_memory=,

        plugins=plugins,
        # parse_mode='html',
    )
    app.run()


