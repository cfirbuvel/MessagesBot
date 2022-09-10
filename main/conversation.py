from typing import List, Union

from pyrogram import Client
from pyrogram.types import Message, CallbackQuery


class ConversationMixin:

    def __init__(self):
        super().__init__()
        self._conversations = {}

    def add_conversation(self, chat_id):
        if chat_id not in self._conversations:
            self._conversations[chat_id] = {'state': None, 'data': {}}

    def set_state(self, chat_id, state):
        self._conversations[chat_id]['state'] = state

    def get_state(self, chat_id):
        return self._conversations[chat_id]['state']

    def get_user_data(self, chat_id):
        return self._conversations[chat_id]['data']

    def set_user_data(self, chat_id, data):
        self._conversations[chat_id]['data'] = data

    def update_user_data(self, chat_id, data):
        self._conversations[chat_id]['data'].update(data)


class ConversationClient(Client, ConversationMixin):
    pass


def state(states: Union[str, List[str]]):

    async def func(flt, client: ConversationClient, update: Union[Message, CallbackQuery]):
        chat_id = message.chat.id
        if chat_id not in client._conversations:
            return False
        if isinstance(states, str):
            states = [states]
        return client.get_state(chat_id) in states
