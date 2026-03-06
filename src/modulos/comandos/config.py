import discord
from discord.ext import commands
import logging
from src.database.storage.state import get_state_repository
from src.modulos.lobby.queue import QueueView

logger = logging.getLogger("Config")

class Config(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state_repo = get_state_repository()

    @commands.command(name="setlobby", aliases=["settestlobby"])
    @commands.has_permissions(administrator=True)
    async def set_lobby_command(self, ctx):
        try:
            self.state_repo.set_lobby(ctx.channel.id, [])
            
            queue_cog = self.bot.get_cog("Queue")
            if queue_cog:
                queue_cog.lobby_channel_id = ctx.channel.id
                queue_cog.queue = []
                logger.info(f"Lobby alterado por {ctx.author}: #{ctx.channel.name} ({ctx.channel.id})")
            
            await ctx.send(f"Canal <#{ctx.channel.id}> configurado como canal para os jogos!")
            
            embed = queue_cog.build_queue_embed()
            await ctx.send(embed=embed, view=QueueView(queue_cog))
            
        except Exception as e:
            logger.error(f"Erro ao executar setlobby: {e}")
            await ctx.send("Erro ao configurar o lobby.")

    @commands.command(name="lobby")
    async def lobby_info(self, ctx):
        queue_cog = self.bot.get_cog("Queue")
        lobby_id = getattr(queue_cog, "lobby_channel_id", None)

        if lobby_id is None:
            await ctx.send("O canal de lobby ainda não foi definido por um administrador.")
            return

        channel = self.bot.get_channel(lobby_id)
        if not channel:
            await ctx.send(f"O ID do Lobby é `{lobby_id}`, mas não consegui encontrar o canal no cache.")
        else:
            await ctx.send(f"O lobby atual é o canal: {channel.mention}")

    @commands.command(name="setchat")
    @commands.has_permissions(administrator=True)
    async def set_general(self, ctx):
        self.state_repo.set_general_channel(ctx.channel.id)
        await ctx.send(f"Canal <#{ctx.channel.id}> definido como o chat de avisos gerais!")

    @commands.command(name="setresults")
    @commands.has_permissions(administrator=True)
    async def setresultados(self, ctx):
        self.state_repo.set_results_channel(ctx.channel.id)
        await ctx.send(f"Canal {ctx.channel.mention} definido para o histórico de partidas!")

    @commands.command(name="setwatch")
    @commands.has_permissions(administrator=True)
    async def set_watch_channel(self, ctx):
        """Define o canal atual para exibir as partidas ao vivo."""
        self.state_repo.set_watch_channel(ctx.channel.id, reset_message=True)
        await ctx.send(f"Canal <#{ctx.channel.id}> definido como painel de transmissão!")
        await self.update_panel(ctx.guild)

async def setup(bot):
    await bot.add_cog(Config(bot))
