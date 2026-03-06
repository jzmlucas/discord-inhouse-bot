import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from src.modulos.lobby.match import Match
from src.modulos.lobby.queue import MAX_PLAYERS, Queue


class DummyTask:
    def cancel(self):
        return None


def _drop_task(coro):
    coro.close()
    return DummyTask()


class FakeQueueStateRepo:
    def __init__(self):
        self.queue_saved = None
        self.lobby_id = None

    def get_queue(self):
        return []

    def get(self, key, default=None):
        return default

    def save_queue(self, queue):
        self.queue_saved = list(queue)

    def set_lobby(self, lobby_id, queue):
        self.lobby_id = lobby_id
        self.queue_saved = list(queue)


class FakeMatchStateRepo:
    def __init__(self):
        self._mmr = {"1": 1000, "2": 1000}
        self._vips = {"1": 9999999999}
        self._players = {"1": {"double_down_tokens": 0}}

    def get_mmr(self):
        return self._mmr

    def get_vips(self):
        return self._vips

    def get_players(self):
        return self._players

    def save_mmr(self, mmr):
        self._mmr = mmr

    def save_players(self, players):
        self._players = players

    def get(self, key, default=None):
        return default

    def set_last_match_id(self, _):
        return None


async def _queue_to_match_flow():
    match_cog = SimpleNamespace(start_new_match=AsyncMock())
    fake_bot = SimpleNamespace(
        wait_until_ready=AsyncMock(),
        get_cog=Mock(return_value=match_cog),
    )

    queue_cog = Queue(fake_bot)
    queue_cog.queue_reset_loop.cancel()
    queue_cog.state_repo = FakeQueueStateRepo()
    queue_cog.create_queue_message = AsyncMock()

    queue_cog.queue = list(range(1, MAX_PLAYERS + 1))
    queue_message = SimpleNamespace(
        edit=AsyncMock(),
        delete=AsyncMock(),
        channel=SimpleNamespace(
            send=AsyncMock(
                return_value=SimpleNamespace(
                    edit=AsyncMock(),
                    delete=AsyncMock(),
                    channel=SimpleNamespace(),
                )
            )
        ),
    )
    queue_message.channel.send.return_value.channel = queue_message.channel

    with patch("src.modulos.lobby.queue.views.asyncio.create_task", side_effect=_drop_task), patch(
        "src.modulos.lobby.queue.cog.asyncio.sleep", new=AsyncMock()
    ):
        await queue_cog.start_confirmation(queue_message)
        queue_cog.confirmed = set(queue_cog.current_match_players)
        await queue_cog.confirm_timer(queue_message, queue_cog.confirmation_token)

    assert match_cog.start_new_match.await_count == 1
    assert queue_cog.state_repo.queue_saved == []
    assert queue_cog.confirmation_active is False


def test_flow_queue_confirmation_starts_match():
    asyncio.run(_queue_to_match_flow())


async def _match_win_flow_cleanup():
    fake_result_channel = SimpleNamespace(send=AsyncMock())
    fake_match_channel = SimpleNamespace(send=AsyncMock())
    fake_guild = SimpleNamespace(roles=[])

    bot = SimpleNamespace(
        get_cog=Mock(return_value=None),
        get_channel=Mock(side_effect=lambda cid: fake_result_channel if cid == 900 else fake_match_channel if cid == 123 else None),
        get_guild=Mock(return_value=fake_guild),
    )
    cog = Match(bot)
    cog.state_repo = FakeMatchStateRepo()
    cog.state_repo.get = Mock(side_effect=lambda key, default=None: 900 if key == "results_channel_id" else default)

    cog.active_matches[123] = {
        "team1": [1],
        "team2": [2],
        "guild_id": 777,
        "channels": [10, 11],
        "custom_id": "laliga-ABCD",
        "match_id": 1,
        "active_doubles": [],
    }

    with patch("src.modulos.lobby.match.cog.asyncio.sleep", new=AsyncMock()), patch(
        "src.modulos.lobby.match.cog.delete_match_channels", new=AsyncMock()
    ) as delete_channels_mock, patch(
        "src.modulos.lobby.match.cog.remove_role_from_players", new=AsyncMock()
    ):
        await cog.end_match(123, "Radiant")

    assert 123 not in cog.active_matches
    assert fake_result_channel.send.await_count == 1
    assert fake_match_channel.send.await_count == 1
    assert delete_channels_mock.await_count == 1


def test_flow_end_match_logs_and_cleans():
    asyncio.run(_match_win_flow_cleanup())


async def _match_remake_flow_refund():
    fake_match_channel = SimpleNamespace(send=AsyncMock())
    fake_guild = SimpleNamespace(roles=[])

    bot = SimpleNamespace(
        get_cog=Mock(return_value=None),
        get_channel=Mock(return_value=fake_match_channel),
        get_guild=Mock(return_value=fake_guild),
    )
    cog = Match(bot)
    cog.state_repo = FakeMatchStateRepo()
    cog.state_repo._players["1"]["double_down_tokens"] = 0

    cog.active_matches[555] = {
        "team1": [1],
        "team2": [2],
        "guild_id": 888,
        "channels": [21, 22],
        "active_doubles": [1],
    }

    with patch("src.modulos.lobby.match.cog.asyncio.sleep", new=AsyncMock()), patch(
        "src.modulos.lobby.match.cog.delete_match_channels", new=AsyncMock()
    ) as delete_channels_mock, patch(
        "src.modulos.lobby.match.cog.remove_role_from_players", new=AsyncMock()
    ):
        await cog.process_remake_cancel(555)

    assert cog.state_repo.get_players()["1"]["double_down_tokens"] == 1
    assert 555 not in cog.active_matches
    assert fake_match_channel.send.await_count == 1
    assert delete_channels_mock.await_count == 1


def test_flow_remake_refunds_and_cleans():
    asyncio.run(_match_remake_flow_refund())
