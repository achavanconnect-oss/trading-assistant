import os
import re

import pytest


@pytest.fixture(params=["memory", "postgres"])
def db(request):
    from app.db import MemoryDB, PgDB
    if request.param == "memory":
        yield MemoryDB()
        return
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL not set (Postgres tests run in CI against a Postgres service)")
    prefix = "t" + re.sub(r"\W", "", request.node.name.split("[")[0])[-10:].lower()
    PgDB(dsn, prefix).drop()
    d = PgDB(dsn, prefix)
    yield d
    d.drop()


@pytest.fixture(params=["memory", "redis"])
def cache(request):
    from app.cache import RedisCache, TTLCache
    if request.param == "memory":
        yield TTLCache()
        return
    url = os.getenv("REDIS_URL")
    if not url:
        pytest.skip("REDIS_URL not set (Redis tests run in CI against a Redis service)")
    c = RedisCache(url, prefix=f"test:{os.getpid()}:{request.node.name[:30]}:")
    yield c
    for k in c.r.scan_iter(c.p + "*"):
        c.r.delete(k)
