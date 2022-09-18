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
    invites = fields.IntField(null=True)
    sleep_until = fields.DatetimeField(null=True)
    # active = fields.BooleanField(default=False)
    # master = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    tasks = fields.ReverseRelation['MessageTask']

    def __str__(self):
        return self.name


class Message(models.Model):
    name = fields.CharField(max_length=64, unique=True)
    text = fields.TextField(null=True)
    created_at = fields.DatetimeField(default=timezone.now)
    edited_at = fields.DatetimeField(default=timezone.now)
    users = fields.ManyToManyField('models.User', related_name='messages')

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


class MediaType(enum.Enum):
    PHOTO = ContentType.PHOTO
    VIDEO = ContentType.VIDEO
    ANIMATION = ContentType.ANIMATION

    @classmethod
    def values(cls):
        return [e.value for e in cls]

    @property
    def input_class(self):
        mapping = {
            self.PHOTO: InputMediaPhoto,
            self.ANIMATION: InputMediaAnimation,
            self.VIDEO: InputMediaVideo,
        }
        return mapping[self]


class AbstractMedia(models.Model):
    type = fields.CharEnumField(MediaType)
    # file_unique_id = fields.CharField(max_length=128)
    file_id = fields.CharField(max_length=256)
    filepath = fields.CharField(max_length=4096, unique=True)
    order = fields.IntField(default=0)

    def get_input_media(self, upload=True):
        media = InputFile(self.filepath) if upload else self.file_id
        kwargs = dict(media=media)
        if not self.order:
            # TODO: Markdown for answers, self.messages field (Is it needed?)
            kwargs.update(caption=self.message.edit_text, parse_mode=ParseMode.MARKDOWN)
        return self.type.input_class(**kwargs)

    class Meta:
        abstract = True


class MessageMedia(AbstractMedia):
    message = fields.ForeignKeyField('models.Message', related_name='media', on_delete=fields.CASCADE)


class User(models.Model):
    chat_id = fields.IntField(unique=True)
    username = fields.CharField(max_length=32, null=True)
    first_name = fields.CharField(max_length=64, null=True)
    last_name = fields.CharField(max_length=64, null=True)

    answers = fields.ReverseRelation['Answer']
    messages = fields.ReverseRelation[Message]
    # created_at = fields.DatetimeField(auto_now_add=True)
    # updated_at = fields.DatetimeField(auto_now=True)

    def name(self):
        return ' '.join(filter(None, (self.first_name, self.last_name))) or None

    def __str__(self):
        return self.username or self.name() or str(self.chat_id)


class Answer(models.Model):
    user = fields.ForeignKeyField('models.User', related_name='answers', on_delete=fields.CASCADE)
    account = fields.ForeignKeyField('models.Account', related_name='answers', on_delete=fields.CASCADE)
    task = fields.ForeignKeyField('models.MessagesTask', related_name='answers', on_delete=fields.CASCADE)
    # message = fields.ForeignKeyField('models.Message', related_name='answers', on_delete=fields.CASCADE)
    msg_id = fields.IntField()
    text = fields.TextField(null=True)
    sent_at = fields.DatetimeField(default=timezone.now)
    edited_at = fields.DatetimeField(default=timezone.now)

    media: fields.ReverseRelation['AnswerMedia']

    async def get_media(self):
        res = self.media.all()
        count = await res.count()
        if count:
            if count == 1:
                res = res.first()
            return await res

    class Meta:
        ordering = ['-edited_at']


class AnswerMedia(AbstractMedia):
    message = fields.ForeignKeyField('models.Answer', related_name='edit_media', on_delete=fields.CASCADE)


class UsersFilter(models.Model):

    class Type(enum.IntEnum):
        RECENT = 0
        HEBREW = 1

    name = fields.IntEnumField(Type, default=Type.RECENT)
    active = fields.BooleanField(default=False)


class MessagesTask(models.Model):

    class Status(enum.IntEnum):
        ACTIVE = 0
        FINISHED = 1
        FAILED = 2
        CANCELLED = 3

    message = fields.ForeignKeyField('models.Message', related_name='tasks', on_delete=fields.CASCADE)
    chat = fields.ForeignKeyField('models.Chat', related_name='tasks', on_delete=fields.CASCADE)
    status = fields.IntEnumField(Status, default=Status.ACTIVE)
    filters = fields.ManyToManyField('models.UsersFilter', related_name='tasks')
    accounts = fields.ManyToManyField('models.Account', related_name='tasks')
    started_at = fields.DatetimeField(auto_now_add=True)
    finished_at = fields.DatetimeField(null=True)
    error = fields.CharField(max_length=512, null=True)
    msg_id = fields.IntField(null=True)  # Statistics bot msg


class Chat(models.Model):

    class Status(enum.Enum):
        OK = 'ok'
        INVALID_LINK = 'invalid_link'
        RESTRICTED = 'restricted'
        HIDDEN = 'hidden'

    chat_id = fields.IntField(null=True)
    name = fields.CharField(max_length=128, null=True)
    link = fields.CharField(max_length=128)
    num_users = fields.IntField(null=True)
    status = fields.CharEnumField(Status, default=Status.OK)
    last_used = fields.DatetimeField(auto_now_add=True)

    @property
    def identifier(self):
        link = self.link.rstrip('/').rsplit('/')

        # if link[-2] == 'joinchat'
        return self.chat_id or self.link

    def __str__(self):
        return self.name or self.link

    class Meta:
        ordering = ['-last_used']


async def init_db():
    await Tortoise.init(config=settings.TORTOISE_ORM)
    await Tortoise.generate_schemas(safe=True)
    await UsersFilter.get_or_create(name=UsersFilter.Type.RECENT, defaults={'active': True})
    await UsersFilter.get_or_create(name=UsersFilter.Type.HEBREW)
