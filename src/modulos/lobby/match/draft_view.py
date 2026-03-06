import asyncio

import discord

from src.modulos.lobby.services.match_draft import (
    apply_draft_pick,
    choose_best_autopick,
)

DRAFT_TIME = 60


class DraftView(discord.ui.View):
    def __init__(self, cog, channel_id, message=None):
        super().__init__(timeout=None)
        self.cog = cog
        self.channel_id = channel_id
        self.message = message
        self.timer_task = None
        self.turn_time = DRAFT_TIME
        self.create_select_menu()
        self.start_timer()

    def create_select_menu(self):
        self.clear_items()
        match_data = self.cog.active_matches.get(self.channel_id)
        if not match_data or not match_data["pool"]:
            return

        players_info = self.cog.state_repo.get_players()
        options = []
        for uid in match_data["pool"]:
            info = players_info.get(str(uid), {})
            name = info.get("name", f"ID: {uid}")
            options.append(discord.SelectOption(label=name, value=str(uid), emoji="👤"))

        select = discord.ui.Select(placeholder="Escolha um jogador...", options=options)
        select.callback = self.select_callback
        self.add_item(select)

    def start_timer(self):
        if self.timer_task:
            self.timer_task.cancel()
        self.timer_task = asyncio.create_task(self.timeout_handler())

    async def timeout_handler(self):
        await asyncio.sleep(self.turn_time)
        await self.auto_pick()

    async def auto_pick(self):
        lock = self.cog._get_match_lock(self.channel_id)
        async with lock:
            match_data = self.cog.active_matches.get(self.channel_id)
            if not match_data or not match_data["pool"] or match_data.get("closing"):
                return
            mmr_data = self.cog.state_repo.get_mmr()
            chosen_id = choose_best_autopick(match_data, mmr_data)
            expected_cap = match_data["sequence"][match_data["step"]]
            apply_draft_pick(match_data, expected_cap, chosen_id)
            should_finalize = not match_data["pool"]
            telemetry = self.cog._telemetry()
            if telemetry:
                telemetry.inc("draft.autopick")

        if not self.message:
            return

        embed = self.cog.create_match_embed(match_data)
        if should_finalize:
            if self.timer_task:
                self.timer_task.cancel()
            await self.message.edit(content=f"<@{expected_cap}> demorou! Auto-pick: <@{chosen_id}>", embed=embed, view=None)
            await self.cog.finalize_match(self.message.guild, match_data, self.channel_id)
        else:
            self.create_select_menu()
            await self.message.edit(content=f"<@{expected_cap}> demorou! Auto-pick: <@{chosen_id}>", embed=embed, view=self)
            self.start_timer()

    async def select_callback(self, interaction: discord.Interaction):
        lock = self.cog._get_match_lock(self.channel_id)
        async with lock:
            match_data = self.cog.active_matches.get(self.channel_id)
            if not match_data or match_data.get("closing"):
                return await interaction.response.send_message("Partida já encerrada.", ephemeral=True)
            expected_cap = match_data["sequence"][match_data["step"]]
            if interaction.user.id != expected_cap:
                return await interaction.response.send_message("Não é sua vez!", ephemeral=True)

            chosen_id = int(interaction.data["values"][0])
            apply_draft_pick(match_data, interaction.user.id, chosen_id)
            should_finalize = not match_data["pool"]
            telemetry = self.cog._telemetry()
            if telemetry:
                telemetry.inc("draft.pick.manual")

        if self.timer_task:
            self.timer_task.cancel()

        if should_finalize:
            await interaction.response.edit_message(embed=self.cog.create_match_embed(match_data), view=None)
            await self.cog.finalize_match(interaction.guild, match_data, self.channel_id)
        else:
            self.create_select_menu()
            await interaction.response.edit_message(embed=self.cog.create_match_embed(match_data), view=self)
            self.start_timer()
