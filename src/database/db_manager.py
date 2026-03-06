import logging
import os

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from src.core.config import Config

logger = logging.getLogger("DatabaseManager")


class DatabaseManager:
    def __init__(self, host=None, database=None, user=None, password=None, port=None, sslmode=None):
        self.config = {
            "host": host or Config.POSTGRES_HOST,
            "port": port or Config.POSTGRES_PORT,
            "database": database or Config.POSTGRES_DB,
            "user": user or Config.POSTGRES_USER,
            "password": Config.POSTGRES_PASSWORD if password is None else password,
            "sslmode": sslmode or Config.POSTGRES_SSLMODE,
            "cursor_factory": RealDictCursor,
        }
        self.conn = None

    def connect(self):
        if self.conn and self.is_healthy():
            return self.conn

        self._ensure_database_exists()

        connect_config = dict(self.config)
        connect_config.setdefault("connect_timeout", 5)
        try:
            self.conn = psycopg2.connect(**connect_config)
        except UnicodeDecodeError as first_error:
            # Some Windows/PostgreSQL setups return non-UTF8 auth errors.
            os.environ["PGCLIENTENCODING"] = "LATIN1"
            try:
                self.conn = psycopg2.connect(**connect_config)
            except UnicodeDecodeError as second_error:
                raise RuntimeError(
                    "Falha ao conectar no PostgreSQL por erro de encoding na mensagem do servidor. "
                    "Verifique usuario/senha no .env e configure o PostgreSQL para mensagens UTF-8 ou ingles "
                    "(lc_messages = 'C')."
                ) from second_error
            except Exception as fallback_error:
                raise RuntimeError(
                    "Falha ao conectar no PostgreSQL apos fallback de encoding. "
                    "Revise POSTGRES_HOST/PORT/DB/USER/PASSWORD no .env."
                ) from fallback_error
        except Exception as exc:
            raise RuntimeError(
                "Falha ao conectar no PostgreSQL. Revise POSTGRES_HOST/PORT/DB/USER/PASSWORD no .env."
            ) from exc
        self.conn.autocommit = True
        self.setup_tables()
        logger.info("postgres_connected", extra={"event": "postgres.connected", "database": self.config["database"]})
        return self.conn

    def _ensure_database_exists(self):
        if not self.config.get("database"):
            return
        try:
            self._create_database_if_missing()
        except RuntimeError:
            # If user has no CREATEDB permission but DB already exists,
            # the next regular connection still works.
            pass

    def _create_database_if_missing(self):
        admin_config = dict(self.config)
        admin_config["database"] = "postgres"
        admin_config.pop("cursor_factory", None)

        try:
            with psycopg2.connect(**admin_config) as admin_conn:
                admin_conn.autocommit = True
                with admin_conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (self.config["database"],))
                    exists = cur.fetchone()
                    if not exists:
                        cur.execute(
                            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self.config["database"]))
                        )
        except Exception as exc:
            raise RuntimeError(
                "Nao foi possivel criar o banco automaticamente. "
                "Verifique se o usuario do POSTGRES tem permissao CREATEDB."
            ) from exc

    def is_healthy(self):
        try:
            if not self.conn or self.conn.closed:
                return False
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return True
        except Exception:
            return False

    def setup_tables(self):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS players (
                    user_id BIGINT PRIMARY KEY,
                    name TEXT,
                    mmr INTEGER DEFAULT 1000,
                    tokens INTEGER DEFAULT 0,
                    steam_id TEXT,
                    medal TEXT,
                    registered_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS vips (
                    user_id BIGINT PRIMARY KEY REFERENCES players(user_id) ON DELETE CASCADE,
                    expiry_timestamp DOUBLE PRECISION
                );

                CREATE TABLE IF NOT EXISTS titles_registry (
                    title_name TEXT PRIMARY KEY,
                    emoji TEXT
                );

                CREATE TABLE IF NOT EXISTS user_inventory (
                    user_id BIGINT REFERENCES players(user_id) ON DELETE CASCADE,
                    title_name TEXT REFERENCES titles_registry(title_name),
                    is_equipped BOOLEAN DEFAULT FALSE,
                    PRIMARY KEY (user_id, title_name)
                );

                CREATE TABLE IF NOT EXISTS server_config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )

    # Legacy helpers kept for compatibility with migrate.py.
    def get_mmr(self, user_id):
        with self.conn.cursor() as cur:
            cur.execute("SELECT mmr FROM players WHERE user_id = %s", (user_id,))
            res = cur.fetchone()
            return res["mmr"] if res else 1000

    def update_mmr(self, user_id, amount, set_absolute=False):
        with self.conn.cursor() as cur:
            if set_absolute:
                cur.execute("UPDATE players SET mmr = %s WHERE user_id = %s", (amount, user_id))
            else:
                cur.execute("UPDATE players SET mmr = mmr + %s WHERE user_id = %s", (amount, user_id))

    def set_config(self, key, value):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO server_config (key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                (key, str(value)),
            )

    def get_config(self, key):
        with self.conn.cursor() as cur:
            cur.execute("SELECT value FROM server_config WHERE key = %s", (key,))
            res = cur.fetchone()
            return res["value"] if res else None


_db_manager = None


def get_db_manager():
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
