import argparse
import asyncio
import logging.config
import os
import sys

# from pyrogram import Client
from aiogram import executor
# from pyrogram.methods.utilities.idle import idle
from tortoise import Tortoise
import uvloop
import watchfiles

from msg_bot import settings
from msg_bot.handlers import *
from msg_bot.models import init_db


logging.config.dictConfig(settings.LOGGING)
# async def msg_bot():
#     await init_db()
#     plugins = {
#         'root': 'msg_bot',
#         'include': ['handlers']
#     }
#     app = Client(
#         'tg_spam_bot',
#         api_id=settings.API_ID,
#         api_hash=settings.API_HASH,
#         app_version='1.0',
#         device_model='PC',
#         system_version='Pop!_OS 22.04 LTS',
#         # lang_code='en'  # TODO: i18n
#         bot_token=settings.BOT_TOKEN,
#         # session_string=,
#         # in_memory=,
#
#         plugins=plugins,
#         # parse_mode='html',
#     )
#     await app.start()
#     await idle()
#     await app.stop()
#     # app.run()
#     # await move_accs()
#     # await spam_it()
#     await Tortoise.close_connections()


async def on_startup(dispatcher):
    await init_db()


async def on_shutdown(dispatcher):
    await Tortoise.close_connections()


def main():
    uvloop.install()
    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown)


async def run_task():
    from msg_bot import tasks
    await on_startup(None)
    await tasks.send_messages()
    await on_shutdown(None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-w', '--watch', action='store_true', help='Watch for changes in files and restart')
    args = parser.parse_args(sys.argv[1:])
    # asyncio.run(run_task())
    if args.watch:
        # path = os.path.abspath(os.path.dirname(__file__))
        watchfiles.run_process(os.path.abspath('msg_bot'), target=main)
    else:
        main()

    # uvloop.install()
    # executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown)
    # asyncio.run(msg_bot())
