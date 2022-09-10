import asyncio
import logging.config

# from pyrogram import Client
from pyrogram.methods.utilities.idle import idle
from tortoise import Tortoise
import uvloop

from main import settings
from main.conversation import ConversationClient
from main.models import init_db
from main.tasks import spam_it

logging.config.dictConfig(settings.LOGGING)


async def main():
    await init_db()
    plugins = {
        'root': 'main',
        'include': ['handlers']
    }
    app = ConversationClient(
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
    await app.start()
    await idle()
    await app.stop()
    # app.run()
    # await move_accs()
    # await spam_it()
    await Tortoise.close_connections()


if __name__ == '__main__':
    uvloop.install()
    asyncio.run(main())
