import json
import logging
import os
from copy import deepcopy

from psycopg2.extras import Json

from src.database.db_manager import get_db_manager

logger = logging.getLogger("StateRepository")


class StateRepository:
    DEFAULT_STATE = {
        "lobby_channel_id": None,
        "ranking_channel_id": None,
        "general_channel_id": None,
        "results_channel_id": None,
        "watch_channel_id": None,
        "watch_message_id": None,
        "leaderboard_channel_id": None,
        "leaderboard_msg_id": None,
        "log_channel_id": None,
        "queue": [],
        "last_match_id": 0,
        "players": {},
        "mmr": {},
        "bans": {},
        "vips": {},
        "vip_colors": {},
        "shop_catalog": {},
        "titles_registry": {},
        "user_titles": {},
    }

    SAVE_MAPPING = {
        "last_match_id": "last_match_id",
        "mmr_dict": "mmr",
        "ranking_id": "ranking_channel_id",
        "general_id": "general_channel_id",
        "bans": "bans",
        "vips": "vips",
        "vip_colors": "vip_colors",
    }
    CONFIG_KEYS = (
        "lobby_channel_id",
        "ranking_channel_id",
        "ranking_message_id",
        "general_channel_id",
        "results_channel_id",
        "watch_channel_id",
        "watch_message_id",
        "leaderboard_channel_id",
        "leaderboard_msg_id",
        "log_channel_id",
        "register_channel_id",
        "channel_id",
        "last_match_id",
    )

    def __init__(self, state_file: str = "state.json"):
        self.state_file = state_file
        self.state_key = "global"
        self.db = get_db_manager()
        self._bootstrapped = False

    def _bootstrap(self):
        if self._bootstrapped:
            return
        self._bootstrapped = True
        self._ensure_row()
        self._migrate_legacy_file_once()

    def _ensure_row(self):
        self.db.connect()
        with self.db.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_state (key, value)
                VALUES (%s, %s)
                ON CONFLICT (key) DO NOTHING
                """,
                (self.state_key, Json(deepcopy(self.DEFAULT_STATE))),
            )

    def _migrate_legacy_file_once(self):
        if not os.path.exists(self.state_file):
            return

        current = self._load_from_db()
        if current and self._has_meaningful_data(current):
            return

        try:
            with open(self.state_file, "r", encoding="utf-8") as file:
                legacy = json.load(file)
        except (json.JSONDecodeError, OSError):
            return

        merged = deepcopy(self.DEFAULT_STATE)
        if isinstance(legacy, dict):
            merged.update(legacy)

        self._write_to_db(merged)

    @staticmethod
    def _has_meaningful_data(data: dict) -> bool:
        keys = ("players", "mmr", "queue", "vips", "bans", "shop_catalog", "last_match_id")
        for key in keys:
            value = data.get(key)
            if isinstance(value, dict) and value:
                return True
            if isinstance(value, list) and value:
                return True
            if key == "last_match_id" and isinstance(value, int) and value > 0:
                return True
        return False

    def _load_from_db(self) -> dict:
        self._bootstrap()
        self.db.connect()
        with self.db.conn.cursor() as cur:
            cur.execute("SELECT value FROM app_state WHERE key = %s", (self.state_key,))
            row = cur.fetchone()
            if not row:
                return deepcopy(self.DEFAULT_STATE)
            value = row["value"] if isinstance(row, dict) else row[0]
            if not isinstance(value, dict):
                return deepcopy(self.DEFAULT_STATE)
            return value

    def _write_to_db(self, data: dict) -> None:
        self._bootstrap()
        self.db.connect()
        with self.db.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_state (key, value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = NOW()
                """,
                (self.state_key, Json(data)),
            )

    @staticmethod
    def _to_int(value, default=None):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_float(value, default=None):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _sync_relational(self, state: dict) -> None:
        self.db.connect()
        with self.db.conn.cursor() as cur:
            self._sync_players(cur, state)
            self._sync_vips(cur, state)
            self._sync_titles(cur, state)
            self._sync_server_config(cur, state)

    def _sync_players(self, cur, state: dict) -> None:
        players = state.get("players", {})
        mmr_data = state.get("mmr", {})
        vips = state.get("vips", {})
        user_titles = state.get("user_titles", {})

        if not isinstance(players, dict):
            players = {}
        if not isinstance(mmr_data, dict):
            mmr_data = {}
        if not isinstance(vips, dict):
            vips = {}
        if not isinstance(user_titles, dict):
            user_titles = {}

        all_ids = set(players.keys()) | set(mmr_data.keys()) | set(vips.keys()) | set(user_titles.keys())
        rows = []
        user_ids = []

        for uid_str in all_ids:
            uid_int = self._to_int(uid_str)
            if uid_int is None:
                continue

            info = players.get(uid_str, {})
            if not isinstance(info, dict):
                info = {}

            tokens = self._to_int(info.get("double_down_tokens", 0), default=0)
            mmr = self._to_int(mmr_data.get(uid_str, 1000), default=1000)
            rows.append(
                (
                    uid_int,
                    info.get("name"),
                    mmr,
                    tokens,
                    str(info.get("steam_id")) if info.get("steam_id") is not None else None,
                    info.get("medal"),
                )
            )
            user_ids.append(uid_int)

        if rows:
            cur.executemany(
                """
                INSERT INTO players (user_id, name, mmr, tokens, steam_id, medal)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET
                    name = EXCLUDED.name,
                    mmr = EXCLUDED.mmr,
                    tokens = EXCLUDED.tokens,
                    steam_id = EXCLUDED.steam_id,
                    medal = EXCLUDED.medal
                """,
                rows,
            )
            cur.execute("DELETE FROM players WHERE NOT (user_id = ANY(%s))", (user_ids,))
        else:
            cur.execute("DELETE FROM players")

    def _sync_vips(self, cur, state: dict) -> None:
        vips = state.get("vips", {})
        if not isinstance(vips, dict):
            vips = {}

        rows = []
        user_ids = []
        for uid_str, expiry in vips.items():
            uid_int = self._to_int(uid_str)
            expiry_float = self._to_float(expiry)
            if uid_int is None or expiry_float is None:
                continue
            rows.append((uid_int, expiry_float))
            user_ids.append(uid_int)

        if rows:
            cur.executemany(
                """
                INSERT INTO vips (user_id, expiry_timestamp)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET expiry_timestamp = EXCLUDED.expiry_timestamp
                """,
                rows,
            )
            cur.execute("DELETE FROM vips WHERE NOT (user_id = ANY(%s))", (user_ids,))
        else:
            cur.execute("DELETE FROM vips")

    def _sync_titles(self, cur, state: dict) -> None:
        registry = state.get("titles_registry", {})
        user_titles = state.get("user_titles", {})

        if not isinstance(registry, dict):
            registry = {}
        if not isinstance(user_titles, dict):
            user_titles = {}

        title_rows = [("Jogador", "👤")]
        managed_titles = {"Jogador"}
        for title_name, emoji in registry.items():
            if not isinstance(title_name, str) or not title_name.strip():
                continue
            managed_titles.add(title_name)
            title_rows.append((title_name, str(emoji) if emoji is not None else None))

        inventory_rows = []
        managed_users = []
        for uid_str, data in user_titles.items():
            uid_int = self._to_int(uid_str)
            if uid_int is None or not isinstance(data, dict):
                continue

            inventory = data.get("inventory", ["Jogador"])
            if not isinstance(inventory, list):
                inventory = ["Jogador"]

            normalized_inventory = []
            for title in inventory:
                if isinstance(title, str) and title.strip() and title not in normalized_inventory:
                    normalized_inventory.append(title)
                    managed_titles.add(title)

            if "Jogador" not in normalized_inventory:
                normalized_inventory.append("Jogador")

            equipped = data.get("equipped", "Jogador")
            if equipped not in normalized_inventory:
                equipped = "Jogador"

            managed_users.append(uid_int)
            for title in normalized_inventory:
                inventory_rows.append((uid_int, title, title == equipped))

        for title_name in managed_titles:
            if title_name not in {row[0] for row in title_rows}:
                title_rows.append((title_name, registry.get(title_name)))

        cur.executemany(
            """
            INSERT INTO titles_registry (title_name, emoji)
            VALUES (%s, %s)
            ON CONFLICT (title_name) DO UPDATE
            SET emoji = EXCLUDED.emoji
            """,
            title_rows,
        )
        cur.execute("DELETE FROM titles_registry WHERE NOT (title_name = ANY(%s))", (list(managed_titles),))

        if inventory_rows:
            cur.executemany(
                """
                INSERT INTO user_inventory (user_id, title_name, is_equipped)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, title_name) DO UPDATE
                SET is_equipped = EXCLUDED.is_equipped
                """,
                inventory_rows,
            )
            cur.execute("DELETE FROM user_inventory WHERE NOT (user_id = ANY(%s))", (managed_users,))
        else:
            cur.execute("DELETE FROM user_inventory")

    def _sync_server_config(self, cur, state: dict) -> None:
        rows = []
        for key in self.CONFIG_KEYS:
            if key not in state or state[key] is None:
                continue
            rows.append((key, str(state[key])))

        if rows:
            cur.executemany(
                """
                INSERT INTO server_config (key, value)
                VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value
                """,
                rows,
            )
        cur.execute("DELETE FROM server_config WHERE key = ANY(%s) AND key <> ALL(%s)", (list(self.CONFIG_KEYS), [r[0] for r in rows]))

    def load(self) -> dict:
        data = self._load_from_db()
        merged = deepcopy(self.DEFAULT_STATE)
        merged.update(data)
        return merged

    def write(self, data: dict) -> None:
        merged = deepcopy(self.DEFAULT_STATE)
        merged.update(data or {})
        self._write_to_db(merged)
        try:
            self._sync_relational(merged)
        except Exception:
            logger.exception("relational_sync_failed")

    def update(self, lobby_id=None, queue=None, **kwargs) -> dict:
        data = self.load()

        if lobby_id is not None:
            data["lobby_channel_id"] = lobby_id
        if queue is not None:
            data["queue"] = queue

        for arg_name, value in kwargs.items():
            key = self.SAVE_MAPPING.get(arg_name, arg_name)
            data[key] = value

        self.write(data)
        return data

    def get(self, key, default=None):
        return self.load().get(key, default)

    # Generic section helpers
    def get_section(self, key: str, default):
        return self.load().get(key, default)

    def set_section(self, key: str, value):
        return self.update(**{key: value})

    # Domain getters
    def get_players(self):
        return self.get_section("players", {})

    def get_mmr(self):
        return self.get_section("mmr", {})

    def get_vips(self):
        return self.get_section("vips", {})

    def get_bans(self):
        return self.get_section("bans", {})

    def get_queue(self):
        return self.get_section("queue", [])

    def get_shop_catalog(self):
        return self.get_section("shop_catalog", {})

    # Domain setters
    def save_players(self, players: dict):
        return self.update(players=players)

    def save_mmr(self, mmr: dict):
        return self.update(mmr_dict=mmr)

    def save_vips(self, vips: dict):
        return self.update(vips=vips)

    def save_bans(self, bans: dict):
        return self.update(bans=bans)

    def save_queue(self, queue: list):
        return self.update(queue=queue)

    def save_shop_catalog(self, catalog: dict):
        return self.update(shop_catalog=catalog)

    def save_players_and_mmr(self, players: dict, mmr: dict):
        return self.update(players=players, mmr_dict=mmr)

    def save_players_and_bans(self, players: dict, bans: dict):
        return self.update(players=players, bans=bans)

    def save_queue_players_and_bans(self, queue: list, players: dict, bans: dict):
        return self.update(queue=queue, players=players, bans=bans)

    # Channel/config helpers
    def set_lobby(self, channel_id: int, queue: list | None = None):
        return self.update(lobby_id=channel_id, queue=queue)

    def set_general_channel(self, channel_id: int):
        return self.update(general_id=channel_id)

    def set_results_channel(self, channel_id: int):
        return self.update(results_channel_id=channel_id)

    def set_watch_channel(self, channel_id: int, reset_message: bool = False):
        data = {"watch_channel_id": channel_id}
        if reset_message:
            data["watch_message_id"] = None
        return self.update(**data)

    def set_watch_message(self, message_id: int):
        return self.update(watch_message_id=message_id)

    def set_leaderboard_channel(self, channel_id: int):
        return self.update(leaderboard_channel_id=channel_id)

    def set_leaderboard_message(self, message_id: int):
        return self.update(leaderboard_msg_id=message_id)

    def set_last_match_id(self, match_id: int):
        return self.update(last_match_id=match_id)
