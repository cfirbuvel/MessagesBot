import asyncio
from typing import List, Union

from aiogram.types import ContentType, Message
from aiogram.dispatcher.handler import CancelHandler
from aiogram.dispatcher.middlewares import BaseMiddleware


class MediaGroupMiddleware(BaseMiddleware):
    """This middleware is for capturing edit_media groups."""
    content_types = [
        ContentType.AUDIO,
        ContentType.DOCUMENT,
        ContentType.ANIMATION,
        ContentType.PHOTO,
        ContentType.VIDEO,
    ]
    media_groups: dict = {}

    def __init__(self, latency: Union[int, float] = 0.01):
        """
        You can provide custom latency to make sure
        albums are handled properly in highload.
        """
        self.latency = latency
        super().__init__()

    # def has_media(self, message: Message) -> bool:
    #     return message.content_type in self.content_types

    async def on_process_message(self, message: Message, data: dict):
        media_group_id = message.media_group_id
        if not media_group_id:
            return
        try:
            media_group = self.media_groups[media_group_id]
        except KeyError:
            media_group = [message]
            self.media_groups[media_group_id] = media_group
            await asyncio.sleep(self.latency)
        else:
            media_group.append(message)
            raise CancelHandler()
        message.conf['is_last'] = True
        await data['state'].update_data(media_group=media_group)

    async def on_post_process_message(self, message: Message, result: dict, data: dict):
        """Clean up after handling our album."""
        media_group_id = message.media_group_id
        if media_group_id and message.conf.get('is_last'):
            del self.media_groups[media_group_id]
            async with data['state'].proxy() as user_data:
                del user_data['media_group']


# @dp.message_handler(is_media_group=True, content_types=types.ContentType.ANY)
# async def handle_albums(message: types.Message, album: List[types.Message]):
#     """This handler will receive a complete album of any type."""
#     media_group = types.MediaGroup()
#     for obj in album:
#         if obj.photo:
#             file_id = obj.photo[-1].file_id
#         else:
#             file_id = obj[obj.content_type].file_id
#
#         try:
#             # We can also add a caption to each file by specifying `"caption": "edit_text"`
#             media_group.attach({"edit_media": file_id, "type": obj.content_type})
#         except ValueError:
#             return await message.answer("This type of album is not supported by aiogram.")
#
#     await message.answer_media_group(media_group)
