import discord
from discord.ext import commands

from src.database.storage.state import get_state_repository
from src.ui.branding import PRIMARY_COLOR


class WatchView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Assistir ao Jogo",
        style=discord.ButtonStyle.success,
        custom_id="btn_watch_toggle",
        emoji="👁️",
    )
    async def toggle_spectator(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = discord.utils.get(interaction.guild.roles, name="Espectador")

        if not role:
            try:
                role = await interaction.guild.create_role(
                    name="Espectador",
                    reason="Cargo para assistir partidas (Auto-criado pelo Bot)",
                    color=discord.Color.blue(),
                )
            except discord.Forbidden:
                return await interaction.response.send_message(
                    "Não tenho permissão para criar o cargo 'Espectador'.",
                    ephemeral=True,
                )

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(
                "❌ Você não é mais um espectador. Canais ocultados.",
                ephemeral=True,
            )
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(
                "✅ Você agora é um espectador! Você pode ver os canais de jogo, mas não pode falar.",
                ephemeral=True,
            )


class WatchManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state_repo = get_state_repository()

    async def update_panel(self, guild):
        state = self.state_repo.load()
        channel_id = state.get("watch_channel_id")
        message_id = state.get("watch_message_id")

        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            return

        match_cog = self.bot.get_cog("Match")
        active_matches = getattr(match_cog, "active_matches", {})

        embed = discord.Embed(
            title="🎮 Partidas em Andamento",
            description="Clique no botão abaixo para receber o cargo de espectador e liberar o acesso às salas.",
            color=PRIMARY_COLOR,
        )

        active_count = 0
        if active_matches:
            for ch_id, data in active_matches.items():
                if isinstance(data, dict) and "match_id" in data:
                    active_count += 1
                    t1 = data.get("team1", [])
                    t2 = data.get("team2", [])
                    custom_id = data.get("custom_id", f"#{data['match_id']}")
                    cap1 = f"<@{t1[0]}>" if t1 else "N/A"
                    cap2 = f"<@{t2[0]}>" if t2 else "N/A"

                    embed.add_field(
                        name=f"⚔️ Partida {custom_id}",
                        value=(
                            f"🔵 **Radiant:** {cap1}\n"
                            f"🔴 **Dire:** {cap2}\n"
                            f"📍 Canal: <#{ch_id}>"
                        ),
                        inline=False,
                    )

        if active_count == 0:
            embed.description = (
                "🚫 **Nenhuma partida ocorrendo no momento.**\n\n"
                "Mesmo assim, você pode pegar o cargo para estar pronto para a próxima!"
            )
            embed.color = discord.Color.red()
        else:
            embed.color = 0xD4AF37

        embed.set_footer(text="Acesso de Espectador: Ouve tudo, mas não fala.")

        try:
            if message_id:
                try:
                    msg = await channel.fetch_message(message_id)
                    await msg.edit(embed=embed, view=WatchView())
                    return
                except Exception:
                    pass

            new_msg = await channel.send(embed=embed, view=WatchView())
            self.state_repo.set_watch_message(new_msg.id)
        except Exception as exc:
            print(f"Erro ao atualizar painel de watch: {exc}")


async def setup(bot):
    await bot.add_cog(WatchManager(bot))
