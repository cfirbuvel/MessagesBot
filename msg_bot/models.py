import asyncio
import enum
from typing import Union, Callable
import os

from aiogram.types import ContentType, InputFile, InputMediaPhoto, InputMediaAnimation, InputMediaVideo, ParseMode
from tortoise import fields, models, timezone, Tortoise

from . import settings


class Account(models.Model):

    class Status(enum.IntEnum):
        ACTIVE = 0
        NOT_AUTHED = 1
        BANNED = 2

    name = fields.CharField(max_length=32, unique=True)
    session = fields.CharField(max_length=4096)
    device_model = fields.CharField(max_length=128, null=True)
    system_version = fields.CharField(max_length=128, null=True)
    lang = fields.CharField(max_length=8, null=True)
    status = fields.IntEnumField(Status, default=Status.ACTIVE)  #
    # active = fields.BooleanField(default=False)
    # master = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    def __str__(self):
        return self.name


class Message(models.Model):
    name = fields.CharField(max_length=64, unique=True)
    text = fields.TextField(null=True)
    created_at = fields.DatetimeField(default=timezone.now)
    edited_at = fields.DatetimeField(default=timezone.now)

    media: fields.ReverseRelation['MessageMedia']

    async def get_media(self):
        res = self.media.all()
        count = await res.count()
        if count:
            if count == 1:
                res = res.first()
            return await res

    class Meta:
        ordering = ['-edited_at']


class MessageMedia(models.Model):

    class Type(enum.Enum):
        PHOTO = ContentType.PHOTO
        VIDEO = ContentType.VIDEO
        ANIMATION = ContentType.ANIMATION

        @classmethod
        def values(cls):
            return [e.value for e in cls]

        # @classmethod
        @property
        def input_class(self):
            mapping = {
                self.PHOTO: InputMediaPhoto,
                self.ANIMATION: InputMediaAnimation,
                self.VIDEO: InputMediaVideo,
            }
            return mapping[self]

    message = fields.ForeignKeyField('models.Message', related_name='media', on_delete=fields.CASCADE)
    type = fields.CharEnumField(Type)
    # file_unique_id = fields.CharField(max_length=128)
    file_id = fields.CharField(max_length=256)
    filepath = fields.CharField(max_length=4096, unique=True)
    order = fields.IntField(default=0)

    def get_input_media(self, upload=True):
        media = InputFile(self.filepath) if upload else self.file_id
        kwargs = dict(media=media)
        if not self.order:
            kwargs.update(caption=self.message.text, parse_mode=ParseMode.MARKDOWN)
        return self.type.input_class(**kwargs)

    class Meta:
        ordering = ['order']


class User(models.Model):
    chat_id = fields.IntField(unique=True)
    username = fields.CharField(max_length=32, null=True)
    first_name = fields.CharField(max_length=64, null=True)
    last_name = fields.CharField(max_length=64, null=True)

    # created_at = fields.DatetimeField(auto_now_add=True)
    # updated_at = fields.DatetimeField(auto_now=True)

    def name(self):
        return ' '.join(filter(None, (self.first_name, self.last_name))) or None

    def __str__(self):
        return self.username or self.name() or str(self.chat_id)


class Chat(models.Model):
    chat_id = fields.IntField(null=True)
    name = fields.CharField(max_length=128, null=True)
    link = fields.CharField(max_length=128)
    num_users = fields.IntField(null=True)
    last_used = fields.DatetimeField(auto_now_add=True)

    @property
    def identifier(self):
        return self.chat_id or self.link

    def __str__(self):
        return self.name or self.link

    class Meta:
        ordering = ['-last_used']


async def init_db():
    await Tortoise.init(config=settings.TORTOISE_ORM)
    await Tortoise.generate_schemas(safe=True)

