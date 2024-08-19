# Inspired by requests-cache, but much simpler

import sqlite3
from abc import abstractmethod
from dataclasses import dataclass
from typing import Literal

CacheBackend = Literal["memory", "file", "sqlite", "redis"]


@dataclass
class CacheSettings:
    backend: CacheBackend


class BaseBackend:
    def __init__(self):
        self.type = type

    @abstractmethod
    def __getitem__(self, key):
        raise NotImplementedError()

    @abstractmethod
    def __setitem__(self, key, value):
        raise NotImplementedError()

    @abstractmethod
    def __delitem__(self, key, value):
        raise NotImplementedError()

    @abstractmethod
    def __iter__(self, key, value):
        raise NotImplementedError()

    @abstractmethod
    def __len__(self, key, value):
        raise NotImplementedError()

    @abstractmethod
    def clear(self, key, value):
        raise NotImplementedError()


class MemeoryBackend(BaseBackend):
    pass


class FileBackend(BaseBackend):
    pass


class SqliteBackend(BaseBackend):
    def __init__(self, filename: str, **kwargs):
        self.filename = filename
        self._db = sqlite3.connect(**kwargs)


class RedisBackend(BaseBackend):
    def ___init__(self, host: str, port: int):
        self.host = host
        self.port = port
