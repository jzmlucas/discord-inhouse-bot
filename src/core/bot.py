import asyncio

import discord
from discord.ext import commands

from src.core.telemetry import Telemetry
from src.database.storage.state import get_state_repository
from src.modulos.lobby.queue import QueueView
from src.modulos.lobby.watch import WatchView
from src.modulos.loja.loja import ShopView
from src.modulos.registro.register import RegisterView


class LigaBot(commands.Bot):
    def __init__(self, config, logger):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(command_prefix=config.PREFIX, intents=intents)

        self.config = config
        self.logger = logger
        self.telemetry = Telemetry()
        self.state_repo = get_state_repository()
        self.state = self.state_repo.load()
        self._metrics_task = None

    async def setup_hook(self):
        from src.core.loader import load_extensions

        await load_extensions(self, self.logger)
        self.before_invoke(self._before_command_invoke)
        self.after_invoke(self._after_command_invoke)
        self._metrics_task = asyncio.create_task(self._metrics_loop())

    async def close(self):
        if self._metrics_task:
            self._metrics_task.cancel()
        await super().close()

    async def _before_command_invoke(self, ctx):
        ctx._cmd_started_at = self.telemetry.now()

    async def _after_command_invoke(self, ctx):
        cmd_name = ctx.command.qualified_name if ctx.command else "unknown"
        self.telemetry.inc("command.success", command=cmd_name)
        started = getattr(ctx, "_cmd_started_at", None)
        if started is not None:
            self.telemetry.observe_since("command.latency", started, command=cmd_name)

    async def _metrics_loop(self):
        while True:
            await asyncio.sleep(60)
            self.logger.info("telemetry_snapshot", extra={"event": "telemetry.snapshot", "metrics": self.telemetry.snapshot()})

    async def on_command_error(self, ctx, exception):
        cmd_name = ctx.command.qualified_name if ctx.command else "unknown"
        self.telemetry.inc("command.error", command=cmd_name, error=exception.__class__.__name__)
        self.logger.error(
            "command_error",
            extra={
                "event": "command.error",
                "command": cmd_name,
                "error_type": exception.__class__.__name__,
            },
        )

    async def on_ready(self):
        self.logger.info("bot_ready", extra={"event": "bot.ready", "user": str(self.user)})

        self.add_view(RegisterView())
        self.add_view(WatchView())
        self.add_view(ShopView(self, self.state.get("shop_catalog", {})))

        queue = self.get_cog("Queue")
        watch = self.get_cog("WatchManager")

        if queue:
            self.add_view(QueueView(queue))
            queue.lobby_channel_id = self.state.get("lobby_channel_id")

            if queue.lobby_channel_id and watch:
                channel = self.get_channel(queue.lobby_channel_id)
                if channel:
                    await watch.update_panel(channel.guild)

        self.logger.info("system_initialized", extra={"event": "system.initialized"})
