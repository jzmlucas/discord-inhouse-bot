import asyncio
import datetime
import logging

import discord
from discord.ext import commands, tasks

from src.database.storage.state import get_state_repository
from src.modulos.lobby.constants import CONFIRM_TIME, MAX_PLAYERS, RESET_INTERVAL
from src.modulos.lobby.runtime_state import QueueRuntimeState
from src.modulos.lobby.services.queue_embed_builder import (
    build_confirmation_embed,
    build_queue_embed,
)
from src.modulos.lobby.services.queue_rules import QueueRulesService
from src.ui.branding import build_banner_file

from .views import ConfirmationView, LockedQueueView, QueueView

logger = logging.getLogger("Queue.View")


class Queue(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state_repo = get_state_repository()
        self.rules = QueueRulesService()

        self.queue_lock = asyncio.Lock()
        self.confirmation_token = 0
        self.confirmation_settled = False
        self.refused_users: set[int] = set()

        initial_queue = self.state_repo.get_queue()
        self.runtime = QueueRuntimeState(
            queue=initial_queue,
            lobby_channel_id=self.state_repo.get("lobby_channel_id"),
            queue_start_time=(None if not initial_queue else datetime.datetime.now().timestamp()),
        )
        self.next_reset = datetime.datetime.now() + datetime.timedelta(hours=1)
        self.queue_reset_loop.start()

    @property
    def queue(self):
        return self.runtime.queue

    @queue.setter
    def queue(self, value):
        self.runtime.queue = value

    @property
    def lobby_channel_id(self):
        return self.runtime.lobby_channel_id

    @lobby_channel_id.setter
    def lobby_channel_id(self, value):
        self.runtime.lobby_channel_id = value

    @property
    def queue_start_time(self):
        return self.runtime.queue_start_time

    @queue_start_time.setter
    def queue_start_time(self, value):
        self.runtime.queue_start_time = value

    @property
    def confirmed(self):
        return self.runtime.confirmed

    @confirmed.setter
    def confirmed(self, value):
        self.runtime.confirmed = value

    @property
    def confirm_message(self):
        return self.runtime.confirm_message

    @confirm_message.setter
    def confirm_message(self, value):
        self.runtime.confirm_message = value

    @property
    def queue_message(self):
        return self.runtime.queue_message

    @queue_message.setter
    def queue_message(self, value):
        self.runtime.queue_message = value

    @property
    def confirm_task(self):
        return self.runtime.confirm_task

    @confirm_task.setter
    def confirm_task(self, value):
        self.runtime.confirm_task = value

    @property
    def remaining_time(self):
        return self.runtime.remaining_time

    @remaining_time.setter
    def remaining_time(self, value):
        self.runtime.remaining_time = value

    @property
    def current_match_players(self):
        return self.runtime.current_match_players

    @current_match_players.setter
    def current_match_players(self, value):
        self.runtime.current_match_players = value

    @property
    def confirmation_active(self):
        return self.runtime.confirmation_active

    @confirmation_active.setter
    def confirmation_active(self, value):
        self.runtime.confirmation_active = value

    def _telemetry(self):
        return getattr(self.bot, "telemetry", None)

    def cog_unload(self):
        self.queue_reset_loop.cancel()

    @tasks.loop(seconds=RESET_INTERVAL)
    async def queue_reset_loop(self):
        should_edit = False
        async with self.queue_lock:
            if self.confirmation_active:
                self.next_reset = datetime.datetime.now() + datetime.timedelta(seconds=120)
                return
            self.queue.clear()
            self.queue_start_time = None
            self.next_reset = datetime.datetime.now() + datetime.timedelta(seconds=RESET_INTERVAL)
            self.state_repo.save_queue(self.queue)
            should_edit = self.queue_message is not None

        if should_edit:
            try:
                await self.queue_message.edit(
                    embed=self.build_queue_embed(self.queue_message.guild),
                    attachments=[build_banner_file()],
                )
            except Exception:
                pass

    @queue_reset_loop.before_loop
    async def before_queue_reset(self):
        await self.bot.wait_until_ready()

    def build_queue_embed(self, guild=None):
        return build_queue_embed(
            bot=self.bot,
            queue=self.queue,
            confirmation_active=self.confirmation_active,
            queue_start_time=self.queue_start_time,
            next_reset=self.next_reset,
            guild=guild,
        )

    def build_confirmation_embed(self):
        return build_confirmation_embed(self.current_match_players, self.confirmed, self.remaining_time)

    def persist_queue_state(self):
        self.state_repo.set_lobby(self.lobby_channel_id, self.queue)

    async def start_confirmation(self, queue_message: discord.Message):
        async with self.queue_lock:
            if self.confirmation_active or len(self.queue) < MAX_PLAYERS:
                return

            self.confirmation_active = True
            self.confirmation_settled = False
            self.refused_users.clear()
            self.confirmation_token += 1
            token = self.confirmation_token

            self.confirmed.clear()
            self.remaining_time = CONFIRM_TIME
            self.current_match_players = list(self.queue)
            mentions = " ".join([f"<@{uid}>" for uid in self.current_match_players])
            telemetry = self._telemetry()
            if telemetry:
                telemetry.inc("queue.confirmation.started")

        try:
            await queue_message.edit(view=LockedQueueView())
            confirm_message = await queue_message.channel.send(
                content=f"**Lobby fechado!** {mentions}",
                embed=self.build_confirmation_embed(),
                view=ConfirmationView(self),
            )
            async with self.queue_lock:
                self.confirm_message = confirm_message
                if self.confirm_task:
                    self.confirm_task.cancel()
                self.confirm_task = asyncio.create_task(self.confirm_timer(queue_message, token))
        except Exception as exc:
            logger.error("Erro start_conf: %s", exc)
            async with self.queue_lock:
                if token == self.confirmation_token:
                    self.confirmation_active = False
                    self.confirmation_settled = False

    async def confirm_timer(self, queue_msg: discord.Message, token: int):
        try:
            while True:
                await asyncio.sleep(5)
                async with self.queue_lock:
                    if token != self.confirmation_token or not self.confirmation_active or self.confirmation_settled:
                        return
                    self.remaining_time -= 5
                    total = len(self.current_match_players)
                    confirmed = len(self.confirmed)
                    time_over = self.remaining_time <= 0
                    everyone_confirmed = confirmed >= total

                if everyone_confirmed or time_over:
                    break

                try:
                    await self.confirm_message.edit(embed=self.build_confirmation_embed())
                except Exception:
                    break

            async with self.queue_lock:
                if token != self.confirmation_token or self.confirmation_settled:
                    return
                self.confirmation_settled = True
                success = len(self.confirmed) >= len(self.current_match_players)
                channel = self.confirm_message.channel if self.confirm_message else queue_msg.channel
                confirmed_players = list(self.confirmed)
                current_players = list(self.current_match_players)

                if success:
                    self.queue.clear()
                    self.state_repo.save_queue([])

            if success:
                telemetry = self._telemetry()
                if telemetry:
                    telemetry.inc("queue.confirmation.success")
                embed_res = discord.Embed(description="**Partida confirmada!** Criando salas...", color=0x00FF7F)
                if self.confirm_message:
                    await self.confirm_message.edit(content=None, embed=embed_res, view=None)
                match_cog = self.bot.get_cog("Match")
                if match_cog:
                    await match_cog.start_new_match(channel, confirmed_players)
            else:
                telemetry = self._telemetry()
                if telemetry:
                    telemetry.inc("queue.confirmation.failed")
                await self.process_punishments(channel, current_players, set(confirmed_players))

            await asyncio.sleep(5)
            try:
                if self.confirm_message:
                    await self.confirm_message.delete()
                await queue_msg.delete()
            except Exception:
                pass

            async with self.queue_lock:
                if token == self.confirmation_token:
                    self.confirmation_active = False
                    self.confirmation_settled = False
                    self.confirm_task = None
            await self.create_queue_message(channel)
        except Exception as exc:
            logger.error("Erro timer: %s", exc)
            async with self.queue_lock:
                if token == self.confirmation_token:
                    self.confirmation_active = False
                    self.confirmation_settled = False
                    self.confirm_task = None

    async def process_punishments(self, channel, players_snapshot=None, confirmed_snapshot=None):
        players_snapshot = players_snapshot if players_snapshot is not None else self.current_match_players
        confirmed_snapshot = confirmed_snapshot if confirmed_snapshot is not None else self.confirmed
        details = self.rules.apply_afk_punishments(players_snapshot, confirmed_snapshot)
        telemetry = self._telemetry()
        if telemetry:
            telemetry.inc("queue.punishment.afk", value=max(1, len(details)))
        if not details:
            details = ["Nenhuma punição aplicada."]
        embed_pun = discord.Embed(
            title="Lobby cancelado por ausência",
            description="\n".join(details),
            color=0xFF4B4B,
        )
        msg_pun = await channel.send(embed=embed_pun)
        await asyncio.sleep(5)
        try:
            await msg_pun.delete()
        except Exception:
            pass

    async def cancel_confirmation(self, channel: discord.TextChannel, refused_user_id: int):
        async with self.queue_lock:
            if not self.confirmation_active or self.confirmation_settled:
                return
            if refused_user_id in self.refused_users:
                return

            self.refused_users.add(refused_user_id)
            self.confirmation_settled = True
            token = self.confirmation_token
            if self.confirm_task:
                self.confirm_task.cancel()
                self.confirm_task = None

            self.rules.apply_refusal_punishment(refused_user_id, self.queue)
            telemetry = self._telemetry()
            if telemetry:
                telemetry.inc("queue.confirmation.refused")
            self.confirmation_active = False
            confirm_message = self.confirm_message

        msg = await channel.send(f"<@{refused_user_id}> recusou a partida. Recebeu 1 strike e uma punição.")
        try:
            if confirm_message:
                await confirm_message.delete()
        except Exception:
            pass
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except Exception:
            pass

        async with self.queue_lock:
            if token == self.confirmation_token:
                self.confirmation_settled = False
                self.confirm_task = None
        await self.create_queue_message(channel)

    async def create_queue_message(self, channel: discord.TextChannel):
        async with self.queue_lock:
            self.lobby_channel_id = channel.id
            self.state_repo.set_lobby(self.lobby_channel_id, self.queue)
        self.queue_message = await channel.send(
            content="",
            embed=self.build_queue_embed(channel.guild),
            view=QueueView(self),
            file=build_banner_file(),
        )


async def setup(bot):
    await bot.add_cog(Queue(bot))
