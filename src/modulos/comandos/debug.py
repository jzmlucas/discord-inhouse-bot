import discord
from discord.ext import commands
import random
import datetime
from src.database.storage.state import get_state_repository


class Debug(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state_repo = get_state_repository()

    @commands.command(name="simular")
    @commands.has_permissions(administrator=True)
    async def simulate_queue(self, ctx):
        """Preenche a fila com 9 bots fictícios + você."""
        # Tentamos buscar pelos nomes das classes que você definiu nos outros arquivos
        queue_cog = self.bot.get_cog("Queue")

        if not queue_cog:
            # Caso o nome no setup seja diferente, listamos os cogs ativos no console para debug
            print(f"Cogs ativos: {self.bot.cogs.keys()}")
            return await ctx.send("❌ Módulo de Fila não encontrado. Verifique se o arquivo queue.py carregou.")

        # 1. Configurar a fila com 10 IDs (9 fake + o seu)
        fake_ids = [random.randint(10000000, 99999999) for _ in range(9)]
        queue_cog.queue = [ctx.author.id] + fake_ids
        queue_cog.queue_start_time = datetime.datetime.now().timestamp()

        # 2. Registrar esses bots no banco para o Match.py não dar erro ao buscar MMR
        players = self.state_repo.get_players()
        mmr_data = self.state_repo.get_mmr()

        for fid in fake_ids:
            uid_str = str(fid)
            players[uid_str] = {
                "name": f"Bot_{fid}",
                "positions": ["MID", "HC"],
                "medal": "Lenda",
                "steam_id": "000000",
                "registered_at": "Simulação"
            }
            mmr_data[uid_str] = random.randint(900, 1100)

        # Salva o estado com os nomes de chaves que o seu save_state (corrigido) aceita
        self.state_repo.save_players_and_mmr(players, mmr_data)
        self.state_repo.save_queue(queue_cog.queue)

        # 3. Atualizar o Embed visual no canal de lobby
        if not queue_cog.lobby_channel_id:
            queue_cog.lobby_channel_id = ctx.channel.id

        await queue_cog.create_queue_message(ctx.channel)
        await ctx.send("🤖 **Simulação Ativa!** 10 jogadores inseridos. Use `!forcarpartida` para iniciar o Draft.")

    @commands.command(name="forcestart")
    @commands.has_permissions(administrator=True)
    async def force_match(self, ctx):
        """Pula a confirmação e cria a partida."""
        queue_cog = self.bot.get_cog("Queue")
        match_cog = self.bot.get_cog("Match")

        if not queue_cog or not match_cog:
            return await ctx.send(f"❌ Erro de Cogs: Queue={bool(queue_cog)}, Match={bool(match_cog)}")

        if len(queue_cog.queue) < 1:
            return await ctx.send("Fila vazia. Use !simular primeiro.")

        # Copia os jogadores, limpa a fila e inicia o processo do Match.py
        players_to_start = list(queue_cog.queue)
        queue_cog.queue.clear()
        self.state_repo.save_queue([])

        # O start_new_match é o método que você tem no match.py
        await match_cog.start_new_match(ctx.channel, players_to_start)
        await ctx.send("⚔️ **Sistema de Matchmaking iniciado forçadamente!**")


async def setup(bot):
    await bot.add_cog(Debug(bot))
