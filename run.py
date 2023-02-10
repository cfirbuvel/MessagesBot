import argparse
import asyncio
import logging.config
import os
import sys

from aiogram import executor
from tortoise import Tortoise
import watchfiles

from msg_bot import settings
from msg_bot.handlers import *
from msg_bot.models import init_db
from msg_bot.tasks import acc_dispatcher

logging.config.dictConfig(settings.LOGGING)

async def on_startup(dispatcher):
    await init_db()

async def on_shutdown(dispatcher):
    await Tortoise.close_connections()


def main():
    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-w', '--watch', action='store_true', help='Watch for changes in files and restart')
    args = parser.parse_args(sys.argv[1:])
    if args.watch:
        watchfiles.run_process(os.path.abspath('msg_bot'), target=main)
    else:
        main()

