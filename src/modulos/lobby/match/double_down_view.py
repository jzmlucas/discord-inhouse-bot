import datetime

import discord


class DoubleDownView(discord.ui.View):
    def __init__(self, cog, match_id):
        super().__init__(timeout=180)
        self.cog = cog
        self.match_id = match_id

    @discord.ui.button(label="Usar Double Down", style=discord.ButtonStyle.secondary)
    async def use_dd(self, interaction: discord.Interaction, button: discord.ui.Button):
        lock = self.cog._get_match_lock(self.match_id)
        async with lock:
            match_data = self.cog.active_matches.get(self.match_id)
            if not match_data:
                return
            if match_data.get("closing"):
                return await interaction.response.send_message("Partida encerrando. Ação indisponível.", ephemeral=True)
            if (datetime.datetime.now().timestamp() - match_data["start_time"]) > 180:
                return await interaction.response.send_message("Tempo expirado!", ephemeral=True)

            players = self.cog.state_repo.get_players()
            user_id_str = str(interaction.user.id)
            user_tokens = players.get(user_id_str, {}).get("double_down_tokens", 0)
            if user_tokens <= 0:
                return await interaction.response.send_message(
                    "Você está sem fichas de Double Down, compre mais utilizando !loja",
                    ephemeral=True,
                )
            if interaction.user.id in match_data["active_doubles"]:
                return await interaction.response.send_message("Você já ativou a ficha de Double Down!", ephemeral=True)

            match_data["active_doubles"].append(interaction.user.id)
            players[user_id_str]["double_down_tokens"] -= 1
            self.cog.state_repo.save_players(players)
            telemetry = self.cog._telemetry()
            if telemetry:
                telemetry.inc("match.double_down.activated")

        await interaction.response.send_message("**Double Down Ativado!**", ephemeral=True)
        await interaction.channel.send(f"**{interaction.user.display_name}** usou Double Down!")
