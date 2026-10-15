"""Users and chat history. MemoryDB (tests, demo) and PgDB (PostgreSQL) share one interface."""
import time


class DuplicateUser(Exception):
    pass


class MemoryDB:
    def __init__(self):
        self.users: dict[str, dict] = {}
        self.messages: list[dict] = []

    def create_user(self, email: str, pw_hash: str) -> int:
        if email in self.users:
            raise DuplicateUser(email)
        uid = len(self.users) + 1
        self.users[email] = {"id": uid, "email": email, "pw_hash": pw_hash}
        return uid

    def get_user(self, email: str) -> dict | None:
        return self.users.get(email)

    def add_message(self, user_id: int, role: str, content: str) -> None:
        self.messages.append({"user_id": user_id, "role": role, "content": content, "ts": time.time()})

    def history(self, user_id: int, limit: int = 50) -> list[dict]:
        rows = [m for m in self.messages if m["user_id"] == user_id][-limit:]
        return [{"role": m["role"], "content": m["content"], "ts": m["ts"]} for m in rows]


class PgDB:
    def __init__(self, dsn: str, prefix: str = "ta"):
        import psycopg
        self.errors = psycopg.errors
        self.p = prefix
        self.conn = psycopg.connect(dsn, autocommit=True)
        self.conn.execute(f"""CREATE TABLE IF NOT EXISTS {prefix}_users (
            id bigserial PRIMARY KEY, email text UNIQUE NOT NULL, pw_hash text NOT NULL, created_at timestamptz DEFAULT now())""")
        self.conn.execute(f"""CREATE TABLE IF NOT EXISTS {prefix}_messages (
            id bigserial PRIMARY KEY, user_id bigint NOT NULL REFERENCES {prefix}_users(id) ON DELETE CASCADE,
            role text NOT NULL, content text NOT NULL, created_at timestamptz DEFAULT now())""")
        self.conn.execute(f"CREATE INDEX IF NOT EXISTS {prefix}_messages_user ON {prefix}_messages (user_id, id)")

    def drop(self) -> None:
        self.conn.execute(f"DROP TABLE IF EXISTS {self.p}_messages, {self.p}_users")

    def create_user(self, email: str, pw_hash: str) -> int:
        try:
            return self.conn.execute(f"INSERT INTO {self.p}_users (email, pw_hash) VALUES (%s, %s) RETURNING id",
                                     (email, pw_hash)).fetchone()[0]
        except self.errors.UniqueViolation as e:
            raise DuplicateUser(email) from e

    def get_user(self, email: str) -> dict | None:
        row = self.conn.execute(f"SELECT id, email, pw_hash FROM {self.p}_users WHERE email = %s", (email,)).fetchone()
        return {"id": row[0], "email": row[1], "pw_hash": row[2]} if row else None

    def add_message(self, user_id: int, role: str, content: str) -> None:
        self.conn.execute(f"INSERT INTO {self.p}_messages (user_id, role, content) VALUES (%s, %s, %s)", (user_id, role, content))

    def history(self, user_id: int, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            f"""SELECT role, content, extract(epoch FROM created_at) FROM (
                    SELECT * FROM {self.p}_messages WHERE user_id = %s ORDER BY id DESC LIMIT %s) t ORDER BY id""",
            (user_id, limit)).fetchall()
        return [{"role": r, "content": c, "ts": float(t)} for r, c, t in rows]
