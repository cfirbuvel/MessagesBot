import asyncio
import enum

from tortoise import fields, models, Tortoise

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
    text = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)



async def init_db():
    await Tortoise.init(config=settings.TORTOISE_ORM)
    await Tortoise.generate_schemas(safe=True)

