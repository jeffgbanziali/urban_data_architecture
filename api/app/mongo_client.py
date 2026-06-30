import os
from motor.motor_asyncio import AsyncIOMotorClient

_client: AsyncIOMotorClient | None = None
_db = None


def get_mongo_db():
    return _db


async def connect():
    global _client, _db
    uri = os.environ.get("MONGO_URI", "mongodb://mongo_user:mongo_pass@mongo:27017/urban?authSource=admin")
    _client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    _db = _client.get_default_database()


async def close():
    global _client
    if _client is not None:
        _client.close()
        _client = None
