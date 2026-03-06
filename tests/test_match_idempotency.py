import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.modulos.lobby.match import Match


class FakeStateRepo:
    def __init__(self):
        self._mmr = {"1": 1000, "2": 1000}
        self._vips = {"1": 9999999999}
        self.save_mmr_calls = 0

    def get_mmr(self):
        return self._mmr

    def get_vips(self):
        return self._vips

    def save_mmr(self, mmr):
        self.save_mmr_calls += 1
        self._mmr = mmr

    def get(self, key, default=None):
        return default

    def set_last_match_id(self, value):
        return value


class FakeBot:
    def __init__(self):
        self._channel = SimpleNamespace(send=AsyncMock())
        self._guild = SimpleNamespace(roles=[])

    def get_cog(self, name):
        return None

    def get_channel(self, channel_id):
        return self._channel if channel_id == 123 else None

    def get_guild(self, guild_id):
        return self._guild


async def _run_end_match_twice():
    bot = FakeBot()
    cog = Match(bot)
    cog.state_repo = FakeStateRepo()
    cog.active_matches[123] = {
        "team1": [1],
        "team2": [2],
        "guild_id": 777,
        "channels": [10, 11],
        "custom_id": "laliga-TEST",
        "match_id": 1,
        "active_doubles": [],
    }

    with patch("src.modulos.lobby.match.cog.asyncio.sleep", new=AsyncMock()), patch(
        "src.modulos.lobby.match.cog.delete_match_channels", new=AsyncMock()
    ) as delete_channels_mock, patch(
        "src.modulos.lobby.match.cog.remove_role_from_players", new=AsyncMock()
    ):
        await cog.end_match(123, "Radiant")
        await cog.end_match(123, "Radiant")

        assert cog.state_repo.save_mmr_calls == 1
        assert delete_channels_mock.await_count == 1


def test_end_match_is_idempotent():
    asyncio.run(_run_end_match_twice())


async def _run_win_duplicate_vote_guard():
    bot = FakeBot()
    cog = Match(bot)
    cog.active_matches[321] = {
        "cap1": 99,
        "cap2": 100,
        "team1": [99],
        "team2": [100],
    }

    ctx = SimpleNamespace(
        channel=SimpleNamespace(id=321),
        author=SimpleNamespace(id=99, guild_permissions=SimpleNamespace(administrator=False)),
        send=AsyncMock(),
    )

    await Match.win.callback(cog, ctx)
    await Match.win.callback(cog, ctx)

    assert ctx.send.await_count == 2
    second_call_msg = ctx.send.await_args_list[1].args[0]
    assert "votação de vencedor em andamento" in second_call_msg


def test_win_prevents_duplicate_sessions():
    asyncio.run(_run_win_duplicate_vote_guard())
