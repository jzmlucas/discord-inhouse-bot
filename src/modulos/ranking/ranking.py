import discord
from discord.ext import tasks, commands
from datetime import datetime
import asyncio
from src.database.storage.state import get_state_repository
from src.database.storage.ranking import get_medal
from src.ui.branding import BANNER_ATTACHMENT_URL, PRIMARY_COLOR, build_banner_file

# --- CONFIGURAÇÕES VISUAIS ---
THEME_COLOR = PRIMARY_COLOR
RED_COLOR = 0xff4b4b    # Vermelho LaLiga
state_repo = get_state_repository()

def build_ranking_embed():
    state = state_repo.load()
    mmr_data = state.get("mmr", {})
    vips = state.get("vips", {})
    agora = datetime.now().timestamp()

    # Ordenação por MMR
    sorted_mmr = sorted(mmr_data.items(), key=lambda item: item[1], reverse=True)
    
    embed = discord.Embed(
        title="🏆 RANKING DE COMPETIDORES",
        description="O ranking reflete o desempenho atual dos jogadores na liga.",
        color=THEME_COLOR
    )
    embed.set_image(url=BANNER_ATTACHMENT_URL)
    
    # Pódio (Top 3) - Estilo Minimalista
    podium_icons = {1: "🥇", 2: "🥈", 3: "🥉"}
    
    podium_text = ""
    for i in range(1, 4):
        if len(sorted_mmr) >= i:
            user_id, mmr = sorted_mmr[i-1]
            is_vip = str(user_id) in vips and agora < float(vips[str(user_id)])
            vip_tag = "💎 " if is_vip else ""
            medal = get_medal(mmr)
            podium_text += f"{podium_icons[i]} <@{user_id}> {vip_tag}\n└ `{mmr} PTS` • {medal}\n\n"
    
    if podium_text:
        embed.add_field(name="✨ LÍDERES", value=podium_text, inline=False)

    # Outros Jogadores (4-15) - Tabela Limpa
    leaderboard_text = ""
    restante = sorted_mmr[3:15]

    if restante:
        for i, (user_id, mmr) in enumerate(restante, 4):
            is_vip = str(user_id) in vips and agora < float(vips[str(user_id)])
            vip_tag = "💎" if is_vip else ""
            leaderboard_text += f"`#{i:02d}` <@{user_id}> {vip_tag} — `{mmr} PTS`\n"

        embed.add_field(
            name="📊 TOP 15 JOGADORES",
            value=leaderboard_text,
            inline=False
        )

    embed.set_footer(text=f"Última atualização: {datetime.now().strftime('%H:%M:%S')}")
    return embed


class RankingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state_repo = get_state_repository()
        self.auto_update_ranking.start()

    def cog_unload(self):
        self.auto_update_ranking.cancel()

    @tasks.loop(minutes=10)
    async def auto_update_ranking(self):
        """Atualização automática periódica."""
        await self.perform_update()

    @auto_update_ranking.before_loop
    async def before_ranking(self):
        await self.bot.wait_until_ready()

    async def perform_update(self):
        """Lógica central de atualização da mensagem de ranking."""
        state = self.state_repo.load()
        channel_id = state.get("leaderboard_channel_id")
        if not channel_id:
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        embed = build_ranking_embed()
        msg_id = state.get("leaderboard_msg_id")

        try:
            if msg_id:
                message = await channel.fetch_message(msg_id)
                await message.edit(embed=embed, attachments=[build_banner_file()])
            else:
                new_msg = await channel.send(embed=embed, file=build_banner_file())
                self.state_repo.set_leaderboard_message(new_msg.id)
        except Exception:
            # Se a mensagem foi deletada ou não encontrada, envia uma nova
            new_msg = await channel.send(embed=embed, file=build_banner_file())
            self.state_repo.set_leaderboard_message(new_msg.id)

    # --- COMANDOS ADMINISTRATIVOS ---

    @commands.command(name="settop")
    @commands.has_permissions(administrator=True)
    async def settop(self, ctx):
        """Define o canal onde o ranking será exibido e fixado."""
        self.state_repo.set_leaderboard_channel(ctx.channel.id)
        embed = build_ranking_embed()
        
        # Envia a mensagem principal
        msg = await ctx.send(embed=embed, file=build_banner_file())
        self.state_repo.set_leaderboard_message(msg.id)
        
        await ctx.send("✅ **Ranking configurado e fixado neste canal!**", delete_after=5)
        try: await ctx.message.delete()
        except: pass

    @commands.command(name="updatetop")
    @commands.has_permissions(administrator=True)
    async def updatetop(self, ctx):
        """Força a atualização manual imediata."""
        await self.perform_update()
        await ctx.send("🔄 **Ranking atualizado instantaneamente.**", delete_after=3)
        try: await ctx.message.delete()
        except: pass

async def setup(bot):
    await bot.add_cog(RankingCog(bot))
