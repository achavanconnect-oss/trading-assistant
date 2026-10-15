"""Small TTL cache: in-process by default, Redis when REDIS_URL is set. Used for short-lived quotes and login rate limiting."""
import json
import os
import time

_now = time.monotonic


class TTLCache:
    def __init__(self):
        self._d: dict[str, tuple[float, str]] = {}

    def get(self, key: str):
        item = self._d.get(key)
        if item is None or item[0] <= _now():
            self._d.pop(key, None)
            return None
        return json.loads(item[1])

    def set(self, key: str, value, ttl_s: float) -> None:
        self._d[key] = (_now() + ttl_s, json.dumps(value))

    def incr(self, key: str, ttl_s: float) -> int:
        """Counter that expires ttl_s after its FIRST increment (fixed window)."""
        item = self._d.get(key)
        if item is None or item[0] <= _now():
            self._d[key] = (_now() + ttl_s, "1")
            return 1
        n = int(item[1]) + 1
        self._d[key] = (item[0], str(n))
        return n

    def delete(self, key: str) -> None:
        self._d.pop(key, None)


class RedisCache:
    def __init__(self, url: str, prefix: str = "ta:"):
        import redis
        self.r = redis.Redis.from_url(url, decode_responses=True)
        self.p = prefix

    def get(self, key: str):
        v = self.r.get(self.p + key)
        return None if v is None else json.loads(v)

    def set(self, key: str, value, ttl_s: float) -> None:
        self.r.set(self.p + key, json.dumps(value), px=max(int(ttl_s * 1000), 1))

    def incr(self, key: str, ttl_s: float) -> int:
        k = self.p + key
        pipe = self.r.pipeline()
        pipe.incr(k)
        pipe.pttl(k)
        n, ttl = pipe.execute()
        if ttl < 0:  # first increment (or no expiry yet): start the window
            self.r.pexpire(k, max(int(ttl_s * 1000), 1))
        return int(n)

    def delete(self, key: str) -> None:
        self.r.delete(self.p + key)


class CachedFeed:
    """Wraps a market-data feed and caches get_price for a couple of seconds. Account data is never cached."""

    def __init__(self, feed, cache, ttl_s: float = 2.0):
        self.feed, self.cache, self.ttl_s = feed, cache, ttl_s
        self.source = feed.source

    def price(self, symbol: str) -> dict:
        key = f"price:{self.source}:{symbol.upper()}"
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        res = self.feed.price(symbol)
        self.cache.set(key, res, self.ttl_s)
        return res

    def candles(self, symbol: str, timeframe: str, count: int):
        return self.feed.candles(symbol, timeframe, count)

    def account(self) -> dict:
        return self.feed.account()


def make_cache():
    url = os.getenv("REDIS_URL")
    return RedisCache(url) if url else TTLCache()
