import datetime
import functools

import motor.motor_asyncio as motor

from . import settings


MONGO_URL = 'mongodb+srv://stone:Nh6nSKLwAR4LU2kY@dev.qewbp.mongodb.net/?retryWrites=true&w=majority'
MONGO_DATABASE = 'tg_spam'


client = motor.AsyncIOMotorClient(settings.MONGO_URL)
db = client[settings.MONGO_DATABASE]


class Collection(motor.AsyncIOMotorCollection):

    def __init__(self, codec_options=None, read_preference=None, write_concern=None, read_concern=None, _delegate=None):
        super().__init__(self.Meta.db, self.Meta.name, codec_options, read_preference, write_concern, read_concern, _delegate)

    def all(self, **kwargs):
        return self.find(dict(**kwargs))

    async def get(self, **kwargs):
        return await self.find_one(dict(**kwargs))

    class Meta:
        db = db
        name = None


class AccountsCollection(Collection):

    class Meta(Collection.Meta):
        name = 'accounts'

    async def create(self, name, session_str, device_model, system_version, lang, master=False):
        now = datetime.datetime.now()
        return await self.collection.insert_one(dict(
            name=name,
            session=session_str,
            device_model=device_model,
            system_version=system_version,
            lang=lang,
            master=master,
            created_at=now,
            updated_at=now,
        ))


Accounts = AccountsCollection()



