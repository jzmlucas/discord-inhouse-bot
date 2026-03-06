import discord


class WinVotingView(discord.ui.View):
    def __init__(self, cog, channel_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.channel_id = channel_id
        self.votes = {}

    @discord.ui.button(label="Radiant venceu", style=discord.ButtonStyle.success)
    async def rad_win(self, interaction, button):
        await self.process_vote(interaction, "Radiant")

    @discord.ui.button(label="Dire venceu", style=discord.ButtonStyle.danger)
    async def dire_win(self, interaction, button):
        await self.process_vote(interaction, "Dire")

    async def process_vote(self, interaction, team):
        trigger_end = False
        lock = self.cog._get_match_lock(self.channel_id)
        async with lock:
            match_data = self.cog.active_matches.get(self.channel_id)
            if not match_data:
                return await interaction.response.send_message("Partida não encontrada.", ephemeral=True)
            if match_data.get("closing"):
                return await interaction.response.send_message("Esta partida já está encerrando.", ephemeral=True)
            if interaction.user.id not in [match_data["cap1"], match_data["cap2"]]:
                return await interaction.response.send_message("Apenas capitães.", ephemeral=True)
            if self.votes.get(interaction.user.id) == team:
                return await interaction.response.send_message("Você já votou nesse resultado.", ephemeral=True)

            self.votes[interaction.user.id] = team
            cap1, cap2 = match_data["cap1"], match_data["cap2"]
            if cap1 in self.votes and cap2 in self.votes:
                if self.votes[cap1] == self.votes[cap2]:
                    trigger_end = True
                else:
                    self.votes.clear()
                    telemetry = self.cog._telemetry()
                    if telemetry:
                        telemetry.inc("match.win_vote.divergence")

        await interaction.response.send_message(f"✅ Votou {team}", ephemeral=True)
        if trigger_end:
            await interaction.message.edit(content=f"Resultado: **{team}**", view=None)
            await self.cog.end_match(self.channel_id, team)
        elif not self.votes:
            await interaction.channel.send("Divergência! Votem novamente.")
