import os
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from backend.app.config import settings

class MongoDBManager:
    _instance: Optional["MongoDBManager"] = None
    _client: Optional[MongoClient] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBManager, cls).__new__(cls)
        return cls._instance

    def get_client(self) -> MongoClient:
        if self._client is None:
            connect_kwargs = {
                "serverSelectionTimeoutMS": 10000,
                "retryWrites": True,
            }
            # Check if using X.509 authentication with a client certificate
            if "MONGODB-X509" in settings.MONGODB_URI or (settings.MONGODB_CERT_PATH and os.path.exists(settings.MONGODB_CERT_PATH)):
                connect_kwargs["tls"] = True
                connect_kwargs["tlsCertificateKeyFile"] = settings.MONGODB_CERT_PATH

            self._client = MongoClient(settings.MONGODB_URI, **connect_kwargs)
        return self._client

    def get_database(self, db_name: Optional[str] = None) -> Database:
        client = self.get_client()
        name = db_name or settings.MONGODB_DATABASE
        return client[name]

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

mongodb = MongoDBManager()

def get_db() -> Database:
    return mongodb.get_database()
