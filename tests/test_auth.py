import pytest
from fastapi.testclient import TestClient

from app import auth, data, main
from app.cache import TTLCache
from app.db import MemoryDB
from tests.test_assistant import FakeClient, call, text

PW = "correct-horse-battery"


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret-" + "x" * 32)


# ---------- primitives ----------
def test_password_hash_roundtrip_and_salting():
    h1, h2 = auth.hash_password(PW), auth.hash_password(PW)
    assert h1 != h2 and auth.verify_password(PW, h1) and not auth.verify_password("wrong", h1)
    assert not auth.verify_password(PW, "garbage") and not auth.verify_password(PW, "md5$aa$bb")


def test_token_roundtrip_expiry_tamper_and_wrong_secret(monkeypatch):
    t = auth.create_token(7, "a@x.com")
    assert auth.decode_token(t)["sub"] == "7"
    with pytest.raises(auth.AuthError):
        auth.decode_token(auth.create_token(7, "a@x.com", ttl_s=-10))      # expired
    with pytest.raises(auth.AuthError):
        auth.decode_token(t[:-3] + ("AAA" if not t.endswith("AAA") else "BBB"))   # tampered signature
    monkeypatch.setenv("JWT_SECRET", "another-secret-" + "y" * 32)
    with pytest.raises(auth.AuthError):
        auth.decode_token(t)                                               # signed with a different secret


def test_missing_secret_is_an_error_not_a_default(monkeypatch):
    monkeypatch.delenv("JWT_SECRET")
    with pytest.raises(auth.AuthError):
        auth.create_token(1, "a@x.com")


# ---------- API with AUTH_REQUIRED=1 ----------
@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    db, cache = MemoryDB(), TTLCache()
    main.app.dependency_overrides[main.get_db] = lambda: db
    main.app.dependency_overrides[main.get_cache] = lambda: cache
    main.app.dependency_overrides[main.get_feed] = lambda: data.DemoFeed()
    yield TestClient(main.app), db
    main.app.dependency_overrides.clear()


def register_login(c, email="a@x.com"):
    assert c.post("/auth/register", json={"email": email, "password": PW}).status_code == 201
    r = c.post("/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_protected_routes_reject_missing_bad_and_expired_tokens(api):
    c, _ = api
    body = {"messages": [{"role": "user", "content": "hi"}]}
    assert c.post("/chat", json=body).status_code == 401
    assert c.post("/tools/get_price", json={"symbol": "EURUSD"}).status_code == 401
    assert c.get("/history").status_code == 401
    assert c.post("/chat", json=body, headers={"Authorization": "Bearer nonsense"}).status_code == 401
    expired = {"Authorization": "Bearer " + auth.create_token(1, "a@x.com", ttl_s=-5)}
    assert c.get("/history", headers=expired).status_code == 401
    assert c.get("/health").json()["auth_required"] is True                # health stays open


def test_register_validation_and_duplicates(api):
    c, _ = api
    assert c.post("/auth/register", json={"email": "a@x.com", "password": "short"}).status_code == 422
    assert c.post("/auth/register", json={"email": "not-an-email", "password": PW}).status_code == 422
    assert c.post("/auth/register", json={"email": "a@x.com", "password": PW}).status_code == 201
    assert c.post("/auth/register", json={"email": "A@X.com", "password": PW}).status_code == 409   # case-insensitive


def test_login_wrong_password_and_unknown_email_look_identical(api):
    c, _ = api
    c.post("/auth/register", json={"email": "a@x.com", "password": PW})
    wrong = c.post("/auth/login", json={"email": "a@x.com", "password": "nope-nope-nope"})
    unknown = c.post("/auth/login", json={"email": "ghost@x.com", "password": PW})
    assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json()


def test_login_is_rate_limited_after_five_failures_and_a_success_resets(api):
    c, _ = api
    c.post("/auth/register", json={"email": "a@x.com", "password": PW})
    bad = {"email": "a@x.com", "password": "wrong-wrong"}
    assert [c.post("/auth/login", json=bad).status_code for _ in range(5)] == [401] * 5
    assert c.post("/auth/login", json=bad).status_code == 429
    assert c.post("/auth/login", json={"email": "a@x.com", "password": PW}).status_code == 429   # even the right one is blocked


def test_successful_login_clears_the_failure_counter(api):
    c, _ = api
    c.post("/auth/register", json={"email": "a@x.com", "password": PW})
    for _ in range(3):
        c.post("/auth/login", json={"email": "a@x.com", "password": "wrong-wrong"})
    assert c.post("/auth/login", json={"email": "a@x.com", "password": PW}).status_code == 200
    for _ in range(4):
        assert c.post("/auth/login", json={"email": "a@x.com", "password": "wrong-wrong"}).status_code == 401


def test_chat_history_is_saved_per_user_and_isolated(api):
    c, db = api
    ha, hb = register_login(c, "a@x.com"), register_login(c, "b@x.com")
    main.app.dependency_overrides[main.get_client] = lambda: FakeClient([[call("get_price", {"symbol": "EURUSD"})], [text("Done now.")]])
    r = c.post("/chat", json={"messages": [{"role": "user", "content": "price of EURUSD?"}]}, headers=ha)
    assert r.status_code == 200 and "done" in r.text
    mine = c.get("/history", headers=ha).json()["messages"]
    assert [(m["role"], m["content"].strip()) for m in mine] == [("user", "price of EURUSD?"), ("assistant", "Done now.")]
    assert c.get("/history", headers=hb).json()["messages"] == []           # user b sees nothing of user a


def test_history_requires_auth_mode_when_auth_is_off(monkeypatch):
    monkeypatch.delenv("AUTH_REQUIRED", raising=False)
    assert TestClient(main.app).get("/history").status_code == 400


def test_tools_endpoint_works_with_a_valid_token(api):
    c, _ = api
    h = register_login(c)
    r = c.post("/tools/get_price", json={"symbol": "EURUSD"}, headers=h)
    assert r.status_code == 200 and r.json()["bid"] > 0


def test_short_jwt_secret_is_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "too-short")
    with pytest.raises(auth.AuthError, match="at least"):
        auth.create_token(1, "a@x.com")
