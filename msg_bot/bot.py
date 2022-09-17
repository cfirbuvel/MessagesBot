# from pyrogram import Client
# from pyrogram.handlers import CallbackQueryHandler, MessageHandler
# from pyrogram.types import Message, CallbackQuery

from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode
from aiogram.contrib.fsm_storage.memory import MemoryStorage


from . import settings
from .middlewares import MediaGroupMiddleware


bot = Bot(token=settings.BOT_TOKEN, parse_mode=ParseMode.HTML)
dispatcher = Dispatcher(bot, storage=MemoryStorage())  # TODO: Use RedisStorage
dispatcher.middleware.setup(MediaGroupMiddleware())
