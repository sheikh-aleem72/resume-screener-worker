import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI_PY")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI_PY not set in env")

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000, maxPoolSize=20)
db = client.get_default_database()  # picks DB from connection string

def ping():
    # quick connectivity check
    return client.server_info()  # will raise on failure

