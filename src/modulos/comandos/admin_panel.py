import discord
from discord.ext import commands
import datetime
from src.database.storage.state import get_state_repository


class AdminPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state_repo = get_state_repository()

    @commands.command(name="panel", aliases=["adminpanel", "stats"])
    @commands.has_permissions(administrator=True)
    async def show_admin_panel(self, ctx):
        """Exibe um resumo completo do estado técnico e social da liga."""
        state = self.state_repo.load()

        players = self.state_repo.get_players()
        mmr_data = self.state_repo.get_mmr()
        vips = self.state_repo.get_vips()
        bans = self.state_repo.get_bans()
        last_match = state.get("last_match_id", 0)

        total_players = len(players)
        total_mmr = sum(mmr_data.values()) if mmr_data else 0
        avg_mmr = (total_mmr / total_players) if total_players > 0 else 0

        agora = datetime.datetime.now().timestamp()
        active_vips = sum(1 for expiry in vips.values() if float(expiry) > agora)

        lobby_ch = f"<#{state.get('lobby_channel_id')}>" if state.get('lobby_channel_id') else "❌ Não definido"
        rank_ch = f"<#{state.get('ranking_channel_id')}>" if state.get('ranking_channel_id') else "❌ Não definido"
        log_ch = f"<#{state.get('log_channel_id')}>" if state.get('log_channel_id') else "❌ Não definido"

        embed = discord.Embed(
            title="PAINEL DE CONTROLE",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )

        embed.add_field(
            name="Comunidade",
            value=f"**Jogadores:** `{total_players}`\n**VIPs Ativos:** `{active_vips}`\n**Banidos:** `{len(bans)}`",
            inline=True
        )

        embed.add_field(
            name="Partidas",
            value=f"**Total Realizadas:** `{last_match}`\n**Média MMR:** `{avg_mmr:.0f}`",
            inline=True
        )

        embed.add_field(
            name="Configuração de Canais",
            value=f"**Lobby:** {lobby_ch}\n**Ranking:** {rank_ch}\n**Logs:** {log_ch}",
            inline=False
        )

        # Listar os 3 maiores MMRs para ver se a economia está estável
        top_3 = sorted(mmr_data.items(), key=lambda x: x[1], reverse=True)[:3]
        top_list = "\n".join(
            [f"**{i + 1}º** <@{uid}>: `{int(pts)}`" for i, (uid, pts) in enumerate(top_3)]) if top_3 else "Nenhum dado."

        embed.add_field(name="Top Economia (MMR)", value=top_list, inline=True)

        embed.set_footer(text=f"Solicitado por {ctx.author.display_name}")

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AdminPanel(bot))
