import asyncio
import datetime

import discord

from src.modulos.lobby.constants import MAX_PLAYERS
from src.ui.branding import build_banner_file


class LockedQueueView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Entrar na fila", style=discord.ButtonStyle.primary, disabled=True))
        self.add_item(discord.ui.Button(label="Sair da fila", style=discord.ButtonStyle.danger, disabled=True))


class QueueView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Entrar na Fila", style=discord.ButtonStyle.primary, custom_id="btn_join_queue")
    async def join_queue(self, interaction: discord.Interaction, button):
        start_confirmation = False
        reject_message = None

        async with self.cog.queue_lock:
            result = self.cog.rules.evaluate_join(interaction, self.cog.queue, self.cog.confirmation_active)
            if not result.allowed:
                reject_message = result.message
            else:
                if len(self.cog.queue) == 0:
                    self.cog.queue_start_time = datetime.datetime.now().timestamp()
                self.cog.queue.append(interaction.user.id)
                self.cog.persist_queue_state()
                if len(self.cog.queue) >= MAX_PLAYERS and not self.cog.confirmation_active:
                    start_confirmation = True

        if reject_message:
            telemetry = self.cog._telemetry()
            if telemetry:
                telemetry.inc("queue.join.rejected")
            return await interaction.response.send_message(reject_message, ephemeral=True)

        telemetry = self.cog._telemetry()
        if telemetry:
            telemetry.inc("queue.join.success")
        await interaction.response.edit_message(
            embed=self.cog.build_queue_embed(interaction.guild),
            attachments=[build_banner_file()],
        )
        if start_confirmation:
            asyncio.create_task(self.cog.start_confirmation(interaction.message))

    @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.danger, custom_id="btn_leave_queue")
    async def leave_queue(self, interaction: discord.Interaction, button):
        reject_message = None

        async with self.cog.queue_lock:
            if self.cog.confirmation_active:
                reject_message = "Você não pode sair durante a confirmação."
            elif interaction.user.id not in self.cog.queue:
                reject_message = "Você não está na fila."
            else:
                self.cog.queue.remove(interaction.user.id)
                if len(self.cog.queue) == 0:
                    self.cog.queue_start_time = None
                self.cog.state_repo.save_queue(self.cog.queue)

        if reject_message:
            telemetry = self.cog._telemetry()
            if telemetry:
                telemetry.inc("queue.leave.rejected")
            return await interaction.response.send_message(reject_message, ephemeral=True)

        telemetry = self.cog._telemetry()
        if telemetry:
            telemetry.inc("queue.leave.success")
        await interaction.response.edit_message(
            embed=self.cog.build_queue_embed(interaction.guild),
            attachments=[build_banner_file()],
        )


class ConfirmationView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Aceitar", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button):
        await interaction.response.defer(ephemeral=True)

        reject_message = None
        should_refresh = False
        async with self.cog.queue_lock:
            user_id = interaction.user.id
            if not self.cog.confirmation_active or user_id not in self.cog.current_match_players:
                reject_message = "Partida inválida ou já encerrada."
            elif user_id in self.cog.confirmed:
                reject_message = "Você já está confirmado."
            else:
                self.cog.confirmed.add(user_id)
                should_refresh = True

        if reject_message:
            return await interaction.followup.send(reject_message, ephemeral=True)
        if should_refresh:
            await interaction.message.edit(embed=self.cog.build_confirmation_embed())

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def refuse(self, interaction: discord.Interaction, button):
        if not self.cog.confirmation_active:
            return
        await interaction.response.send_message("Você recusou a partida.", ephemeral=True)
        await self.cog.cancel_confirmation(interaction.channel, interaction.user.id)
