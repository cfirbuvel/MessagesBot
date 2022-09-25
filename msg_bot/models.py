import asyncio
import enum
import functools
from gettext import gettext as _
from typing import Union, Callable
import os
import random

from aiogram import types
from pyrogram.enums import UserStatus
from pyrogram.types import InputMediaPhoto, InputMediaAnimation, InputMediaVideo, User as PyroUser
from tortoise import fields, models, timezone, Tortoise

from . import settings
from .utils import get_full_name


class Acc(models.Model):

    # @staticmethod
    # def generate_invites_num():
    #     return random.randint(45, 50)

    class Status(enum.IntEnum):
        OFFLINE = 0
        ACTIVE = 1
        NOT_AUTHED = 2
        BANNED = 3

    name = fields.CharField(max_length=32, unique=True)
    session = fields.CharField(max_length=4096)
    device_model = fields.CharField(max_length=128, null=True)
    system_version = fields.CharField(max_length=128, null=True)
    lang = fields.CharField(max_length=8, null=True)
    status = fields.IntEnumField(Status, default=Status.ACTIVE)  #

    # invites = fields.IntField(default=generate_invites_num)
    # invites_reset_at = fields.DatetimeField(null=True)
    # active = fields.BooleanField(default=False)
    # master = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    tasks = fields.ReverseRelation['MsgTask']

    def __str__(self):
        return self.name


class UserFilter(enum.Enum):
    RECENT = 0
    HEBREW = 1

    def get_name(self):
        mapping = {
            self.RECENT: _('Recent'),
            self.HEBREW: _('Hebrew name'),
        }
        return mapping[self]

    async def apply(self, user: PyroUser):
        method = getattr(self, 'filter_{}'.format(self.name.lower()))
        return await method(user)

    def filter_recent(self, user: PyroUser):
        if user.status == UserStatus.OFFLINE:
            today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            return (today - user.last_online_date).days < 7
        return user.status in (UserStatus.ONLINE, UserStatus.RECENTLY, UserStatus.LAST_WEEK)

    def filter_hebrew(self, user: PyroUser):
        name = get_full_name(user)
        return any(c in name for c in 'אבגדהוזחטיכלמנסעפצקרשת')


class MsgSettings(models.Model):

    filters = fields.JSONField(default=list)
    limit = fields.IntField(default=1000)

    @property
    def user_filters(self):
        return [UserFilter(val) for val in self.filters]

    def get_msg(self):
        filters = ', '.join(f.get_name() for f in self.user_filters)
        return _('Daily limit: {}\n'
                 'User filters: {}').format(self.limit, filters)


class Msg(models.Model):
    name = fields.CharField(max_length=64, unique=True)
    text = fields.TextField(null=True)
    settings = fields.OneToOneField('models.MsgSettings', related_name='msg', on_delete=fields.RESTRICT)
    created_at = fields.DatetimeField(default=timezone.now)
    edited_at = fields.DatetimeField(default=timezone.now)
    users = fields.ManyToManyField('models.User', related_name='messages', through='sent_msg')

    media: fields.ReverseRelation['MsgMedia']

    async def has_content(self):
        return bool(self.text) or await self.media.exists()

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
    PHOTO = types.ContentType.PHOTO
    VIDEO = types.ContentType.VIDEO
    ANIMATION = types.ContentType.ANIMATION

    @classmethod
    def values(cls):
        return [e.value for e in cls]

    @property
    def bot_input_class(self):
        mapping = {
            self.PHOTO: types.InputMediaPhoto,
            self.ANIMATION: types.InputMediaAnimation,
            self.VIDEO: types.InputMediaVideo,
        }
        return mapping[self]

    @property
    def acc_input_class(self):
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

    # def get_input_media(self, upload=True):
    #     media = InputFile(self.filepath) if upload else self.file_id
    #     kwargs = dict(media=media)
    #     if not self.order:
    #         # TODO: Markdown for answers, self.messages field (Is it needed?)
    #         kwargs.update(caption=self.message.text, parse_mode=ParseMode.MARKDOWN)
    #     return self.type.input_class(**kwargs)

    class Meta:
        abstract = True


class MsgMedia(AbstractMedia):
    msg = fields.ForeignKeyField('models.Msg', related_name='media', on_delete=fields.CASCADE)

    class Meta:
        ordering = ['order']


class SentMsg(models.Model):
    msg = fields.ForeignKeyField('models.Msg', related_name='sent_messages', on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', related_name='sent_messages', on_delete=fields.CASCADE)
    sent_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = 'sent_msg'
        unique_together = ('msg', 'user')


class User(models.Model):
    chat_id = fields.IntField(unique=True)
    username = fields.CharField(max_length=32, null=True)
    first_name = fields.CharField(max_length=64, null=True)
    last_name = fields.CharField(max_length=64, null=True)

    answers = fields.ReverseRelation['Answer']
    msgs = fields.ReverseRelation[Msg]
    # created_at = fields.DatetimeField(auto_now_add=True)
    # updated_at = fields.DatetimeField(auto_now=True)

    def name(self):
        return ' '.join(filter(None, (self.first_name, self.last_name))) or None

    def __str__(self):
        return self.username or self.name() or str(self.chat_id)


class Answer(models.Model):
    user = fields.ForeignKeyField('models.User', related_name='answers', on_delete=fields.CASCADE)
    account = fields.ForeignKeyField('models.Acc', related_name='answers', on_delete=fields.CASCADE)
    task = fields.ForeignKeyField('models.MsgTask', related_name='answers', on_delete=fields.CASCADE)
    # message = fields.ForeignKeyField('models.Msg', related_name='answers', on_delete=fields.CASCADE)
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
    msg = fields.ForeignKeyField('models.Answer', related_name='media', on_delete=fields.CASCADE)


class MsgTask(models.Model):

    class Status(enum.IntEnum):
        ACTIVE = 0
        FINISHED = 1
        FAILED = 2
        CANCELED = 3

    msg = fields.ForeignKeyField('models.Msg', related_name='tasks', on_delete=fields.CASCADE)
    chat = fields.ForeignKeyField('models.Chat', related_name='tasks', on_delete=fields.CASCADE)
    status = fields.IntEnumField(Status, default=Status.ACTIVE)
    settings = fields.ForeignKeyField('models.MsgSettings', related_name='tasks')
    # filters = fields.ManyToManyField('models.UsersFilter', related_name='tasks')
    accounts = fields.ManyToManyField('models.Acc', related_name='tasks')
    started_at = fields.DatetimeField(auto_now_add=True)
    finished_at = fields.DatetimeField(null=True)
    error = fields.CharField(max_length=512, null=True)
    # msg_id = fields.IntField(null=True)  # Runtime statistics bot msg


class Chat(models.Model):

    class Status(enum.Enum):
        OK = 'ok'
        INVALID_LINK = 'invalid_link'
        INVALID_TYPE = 'invalid_type'
        RESTRICTED = 'restricted'
        HIDDEN = 'hidden'

    chat_id = fields.IntField(null=True, unique=True)
    name = fields.CharField(max_length=128, null=True)
    link = fields.CharField(max_length=128)
    num_users = fields.IntField(null=True)
    status = fields.CharEnumField(Status, default=Status.OK)
    last_used = fields.DatetimeField(auto_now_add=True)

    @property
    def username(self):
        parts = self.link.rstrip('/').rsplit('/')
        end = parts[-1]
        if parts[-2] == 'joinchat' or end.startswith('+'):
            return self.link
        return end

    @property
    def identifier(self):
        return self.chat_id or self.username

    def __str__(self):
        return self.name or self.link

    class Meta:
        ordering = ['-last_used']


async def init_db():
    await Tortoise.init(config=settings.TORTOISE_ORM)
    await Tortoise.generate_schemas(safe=True)
    # await UsersFilter.get_or_create(name=UsersFilter.Type.RECENT, defaults={'active': True})
    # await UsersFilter.get_or_create(name=UsersFilter.Type.HEBREW)
