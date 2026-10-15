import time

import pytest

from app import cache as cache_mod
from app.cache import CachedFeed, TTLCache
from app.db import DuplicateUser
from app import data


# ---------- users and chat history (MemoryDB always; PgDB when DATABASE_URL is set) ----------
def test_create_and_get_user_and_duplicate(db):
    uid = db.create_user("a@x.com", "hash1")
    assert db.get_user("a@x.com") == {"id": uid, "email": "a@x.com", "pw_hash": "hash1"}
    assert db.get_user("nobody@x.com") is None
    with pytest.raises(DuplicateUser):
        db.create_user("a@x.com", "hash2")


def test_history_is_per_user_ordered_and_limited(db):
    a, b = db.create_user("a@x.com", "h"), db.create_user("b@x.com", "h")
    for i in range(5):
        db.add_message(a, "user", f"q{i}")
    db.add_message(b, "user", "private")
    assert [m["content"] for m in db.history(a)] == ["q0", "q1", "q2", "q3", "q4"]
    assert [m["content"] for m in db.history(a, limit=2)] == ["q3", "q4"]   # the latest two, oldest first
    assert [m["content"] for m in db.history(b)] == ["private"]


# ---------- cache (TTLCache always; RedisCache when REDIS_URL is set) ----------
def test_cache_set_get_and_expiry(cache):
    assert cache.get("k") is None
    cache.set("k", {"bid": 1.1}, ttl_s=0.2)
    assert cache.get("k") == {"bid": 1.1}
    time.sleep(0.35)
    assert cache.get("k") is None


def test_incr_counts_in_a_window_and_delete_resets(cache):
    assert [cache.incr("c", 5) for _ in range(3)] == [1, 2, 3]
    assert cache.get("c") == 3
    cache.delete("c")
    assert cache.get("c") is None and cache.incr("c", 5) == 1


def test_incr_window_expires(cache):
    cache.incr("w", 0.2)
    time.sleep(0.35)
    assert cache.incr("w", 0.2) == 1


# ---------- quote caching ----------
class CountingFeed(data.DemoFeed):
    def __init__(self):
        self.calls = 0

    def price(self, symbol):
        self.calls += 1
        return super().price(symbol)


def test_cached_feed_serves_repeat_prices_from_cache_until_ttl():
    feed = CountingFeed()
    cf = CachedFeed(feed, TTLCache(), ttl_s=0.2)
    first, second = cf.price("EURUSD"), cf.price("eurusd")
    assert first == second and feed.calls == 1
    time.sleep(0.35)
    cf.price("EURUSD")
    assert feed.calls == 2


def test_cached_feed_never_caches_account_data():
    calls = []

    class F(data.DemoFeed):
        def account(self):
            calls.append(1)
            return super().account()
    cf = CachedFeed(F(), TTLCache())
    cf.account(); cf.account()
    assert len(calls) == 2


def test_failed_price_lookup_is_not_cached():
    class Flaky(data.DemoFeed):
        n = 0

        def price(self, symbol):
            Flaky.n += 1
            if Flaky.n == 1:
                raise RuntimeError("No live quote yet")
            return super().price(symbol)
    cf = CachedFeed(Flaky(), TTLCache())
    with pytest.raises(RuntimeError):
        cf.price("EURUSD")
    assert cf.price("EURUSD")["bid"] > 0


def test_make_cache_defaults_to_in_process(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert isinstance(cache_mod.make_cache(), TTLCache)
