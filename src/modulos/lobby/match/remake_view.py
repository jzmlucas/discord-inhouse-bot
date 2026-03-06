import discord
from src.ui.branding import PRIMARY_COLOR


class RemakeView(discord.ui.View):
    def __init__(self, cog, channel_id, players_list):
        super().__init__(timeout=120)
        self.cog = cog
        self.channel_id = channel_id
        self.players_list = players_list
        self.votes = []
        self.required = 6

    def create_embed(self):
        filled = len(self.votes)
        bar = "🟢" * filled + "⚪" * (self.required - filled)
        embed = discord.Embed(
            title="Votação de remake",
            description=(
                "A partida será cancelada se 6+ jogadores votarem pelo remake.\n"
                f"**Status:** `{filled}/{self.required}`\n{bar}\n\n"
                "**Jogadores que votaram pelo remake:**\n"
                + (", ".join([f"<@{uid}>" for uid in self.votes]) if self.votes else "_Nenhum voto ainda_")
            ),
            color=PRIMARY_COLOR,
        )
        embed.set_footer(text="Apenas jogadores que estão nessa partida podem votar.")
        return embed

    @discord.ui.button(label="Confirmar Remake", style=discord.ButtonStyle.gray, custom_id="remake_btn")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.players_list:
            return await interaction.response.send_message("Você não está nessa partida.", ephemeral=True)
        if interaction.user.id in self.votes:
            return await interaction.response.send_message("Seu voto já foi contabilizado.", ephemeral=True)

        self.votes.append(interaction.user.id)
        if len(self.votes) < self.required:
            return await interaction.response.edit_message(embed=self.create_embed(), view=self)

        embed = discord.Embed(
            description="**Remake aprovado.** A partida está sendo encerrada e nenhum dado será salvo.",
            color=0x00FF7F,
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()
        self.cog.active_remakes.pop(self.channel_id, None)
        await self.cog.process_remake_cancel(self.channel_id)

    async def on_timeout(self):
        self.cog.active_remakes.pop(self.channel_id, None)
