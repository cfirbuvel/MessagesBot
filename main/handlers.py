from gettext import gettext as _

from pyrogram import Client, filters
from pyrogram.handlers import CallbackQueryHandler

from . import inline_markups


@Client.on_message(filters.command('start'))
async def start(client, message):
    await message.reply(_('Hello!'), reply_markup=inline_markups.main())


@Client.on_callback_query(filters.regex('^menu_msgs$'))
async def messages(client, callback_query):
    await callback_query.edit_message_reply_markup(inline_markups.messages())
    await callback_query.answer()


@Client.on_callback_query(filters.regex('^msgs_my$'))
async def messages_my(client, callback_query):
    pass


@Client.on_callback_query(filters.regex('^msgs_create$'))
async def messages_create(client, callback_query):
    msg = ('Please, enter message text. You can include markdown.\n\n'
           'Message will start with "Hello {username}!" by default.\n'
           'To change it, add `{username}` anywhere in the text.')
    await callback_query.edit_message_text(msg, reply_markup=inline_markups.back('msg_create'))
    await callback_query.answer()


@Client.on_message()
async def messages_create_text(client, message):
    pass


@Client.on_callback_query(filters.regex(r'run'))
async def run(client, callback_query):
    await callback_query.message.reply(_('Started main task!'))
    await callback_query.answer()



# class Menu:
#
#
#
#     # keyboard = [
#     #     [Btn(_('Accounts'), Accounts)]
#     #     [Btn(_('Groups'), Groups)],
#     # ]
#
#
#
# class Menu:
#     accounts = Button(_('Accounts'), 'Accounts')
#     groups = Button(_('Groups'), 'Groups')
#     run = Button(_('Run!'), 'Run')
#     stats = Button(_('Stats'), 'Stats')
#
#     async def on_accounts(self):
#         pass
#
#     async def on_groups(self):
#         pass
#
#
# # class Accounts:
# #     list = Button(_('List'), 'AccountsList')
# class
#
#
# bot = Bot()
#
#
# class Main:
#     markup = [
#         [Accounts],
#         [Groups],
#         [Statistics],
#         [Run]
#     ]
#
#
# class Accounts:
#     markup = [
#         [AddAccount],
#         [DeleteAccount],
#         [EditAccount]
#     ]
#
#
# class Groups:
#     pass
#
#
# class Statistics:
#     pass
#
#
# class Run:
#     pass
#
#
# menu = [
#     []
# ]
