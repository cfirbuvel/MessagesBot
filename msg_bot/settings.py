from pathlib import Path


BASE_DIR = Path(__file__).parent.parent


MONGO_URL = 'mongodb+srv://stone:Nh6nSKLwAR4LU2kY@dev.qewbp.mongodb.net/?retryWrites=true&w=majority'
MONGO_DATABASE = 'tg_spam'



API_ID = 15309611  # AppRobo account
API_HASH = 'b3eea2c3ad5e3b5bb458d6615d8ab7b5'
BOT_TOKEN = '497415901:AAGOGyJ5BqPBUe9zycr355vg98aSFBvV2jI'

# APP_VERSION = '1.0'


# TODO: i18n, timezones
TORTOISE_ORM = {
    'connections': {'default': 'sqlite://db.sqlite3'},
    'apps': {
        'models': {
            'models': ['msg_bot.models'],  # 'aerich.models'
            'default_connection': 'default',
        },
    },
}


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {},
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    # 'loggers': {
    #     'django': {
    #         'handlers': ['console'],
    #         'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
    #         'propagate': False,
    #     },
    # },
}


MEDIA_ROOT = BASE_DIR / 'media'
