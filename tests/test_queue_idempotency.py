import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from src.modulos.lobby.queue import Queue


class FakeBot:
    async def wait_until_ready(self):
        return None

    def get_cog(self, name):
        return None


async def _run_cancel_confirmation_idempotency():
    bot = FakeBot()
    cog = Queue(bot)
    cog.queue_reset_loop.cancel()

    cog.confirmation_active = True
    cog.confirmation_settled = False
    cog.confirmation_token = 1
    cog.confirm_task = SimpleNamespace(cancel=Mock())
    cog.confirm_message = SimpleNamespace(delete=AsyncMock())
    cog.rules.apply_refusal_punishment = Mock()
    cog.create_queue_message = AsyncMock()

    channel = SimpleNamespace(
        send=AsyncMock(return_value=SimpleNamespace(delete=AsyncMock())),
        id=55,
    )

    with patch("src.modulos.lobby.queue.cog.asyncio.sleep", new=AsyncMock()):
        await cog.cancel_confirmation(channel, 42)
        await cog.cancel_confirmation(channel, 42)

    assert cog.rules.apply_refusal_punishment.call_count == 1
    assert channel.send.await_count == 1
    assert cog.create_queue_message.await_count == 1


def test_cancel_confirmation_is_idempotent():
    asyncio.run(_run_cancel_confirmation_idempotency())
