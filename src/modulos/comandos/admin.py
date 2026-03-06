import datetime
import logging
import re

import discord
from discord.ext import commands
from envs.mp.Lib.encodings.aliases import aliases

from src.database.storage.state import get_state_repository

logger = logging.getLogger("Admin")


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state_repo = get_state_repository()

    @commands.command(name="forceremake", aliases=["frmk"])
    @commands.has_permissions(administrator=True)
    async def force_remake(self, ctx, match_id: str):
        match_cog = self.bot.get_cog("Match")
        if not match_cog:
            return await ctx.send("Sistema de partidas não encontrado.")

        target_channel_id = None
        search_id = match_id.strip().upper()

        for channel_id, data in match_cog.active_matches.items():
            current_custom_id = data.get('custom_id', "").upper()
            if current_custom_id == search_id:
                target_channel_id = channel_id
                break

        if not target_channel_id:
            return await ctx.send(f"ID `{search_id}` não encontrado entre as partidas ativas.")

        await match_cog.process_remake_cancel(target_channel_id)
        await ctx.send(f"Partida `{search_id}` anulada com sucesso por um administrador.")
        logger.info(f"ADM {ctx.author} forçou remake da partida {search_id}")

    @commands.command(name="givedd", aliases=["givefichas"])
    @commands.has_permissions(administrator=True)
    async def give_fichas(self, ctx, member: discord.Member, quantidade: int):
        if quantidade <= 0:
            return await ctx.send("A quantidade deve ser maior que zero!")

        players = self.state_repo.get_players()
        user_id = str(member.id)

        if user_id not in players:
            players[user_id] = {"double_down_tokens": 0}

        atual = players[user_id].get("double_down_tokens", 0)
        players[user_id]["double_down_tokens"] = atual + quantidade

        self.state_repo.save_players(players)

        embed = discord.Embed(
            title="FICHAS ADICIONADAS",
            description=f"Foram adicionadas **{quantidade}** fichas de Double Down para {member.mention}.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Saldo Atual", value=f"💰 `{atual + quantidade}` fichas", inline=True)
        embed.set_footer(text=f"Admin: {ctx.author.display_name}")

        await ctx.send(embed=embed)
        logger.info(f"ADM {ctx.author} deu {quantidade} fichas para {member}")

    @commands.command(name="addmmr")
    @commands.has_permissions(administrator=True)
    async def add_mmr(self, ctx, member: discord.Member, amount: int):
        """Adiciona MMR manualmente a um jogador."""
        mmr_data = self.state_repo.get_mmr()
        current_mmr = mmr_data.get(str(member.id), 1000)
        new_mmr = current_mmr + amount
        mmr_data[str(member.id)] = new_mmr
        self.state_repo.save_mmr(mmr_data)
        await ctx.send(f"✅ **{amount} MMR** adicionados a {member.mention}. Novo total: `{new_mmr}`")

    @commands.command(name="setmmr")
    @commands.has_permissions(administrator=True)
    async def set_mmr(self, ctx, member: discord.Member, valor: int):
        """Define o MMR exato de um jogador."""
        mmr_data = self.state_repo.get_mmr()
        mmr_data[str(member.id)] = valor
        self.state_repo.save_mmr(mmr_data)
        await ctx.send(f"MMR de {member.mention} definido para `{valor}`.")

    @commands.command(name="resetmmr")
    @commands.has_permissions(administrator=True)
    async def reset_player(self, ctx, member: discord.Member):
        mmr_data = self.state_repo.get_mmr()
        if str(member.id) in mmr_data:
            mmr_data[str(member.id)] = 1000
            self.state_repo.save_mmr(mmr_data)
            await ctx.send(f"Perfil de {member.mention} foi resetado para 1000 MMR.")
        else:
            await ctx.send("Jogador não possui dados registrados.")

    @commands.command(name="resetlobby")
    @commands.has_permissions(administrator=True)
    async def clear_queue_admin(self, ctx):
        self.state_repo.save_queue([])
        queue_cog = self.bot.get_cog("Queue")
        if queue_cog:
            queue_cog.queue = []
        await ctx.send("A fila foi limpa manualmente por um administrador.")

    @commands.command(name="ban")
    @commands.has_permissions(administrator=True)
    async def ban_player(self, ctx, member: discord.Member, time_str: str, *, reason="Não informado"):
        """Bane um usuário por tempo: !ban @user 1d Motivo"""
        seconds_per_unit = {"m": 60, "h": 3600, "d": 86400}
        match = re.match(r"(\d+)([mhd])", time_str.lower())
        if not match:
            return await ctx.send("❌ Formato de tempo inválido! Use: 10m, 2h, 1d.")

        amount, unit = match.groups()
        ban_duration = int(amount) * seconds_per_unit[unit]
        unban_timestamp = datetime.datetime.now().timestamp() + ban_duration

        state = self.state_repo.load()
        bans = self.state_repo.get_bans()
        bans[str(member.id)] = unban_timestamp
        self.state_repo.save_bans(bans)

        await ctx.send(f"🔨 {member.mention} foi banido da liga por {time_str}.")

        general_id = state.get("general_id")
        if general_id:
            channel = self.bot.get_channel(general_id)
            if channel:
                embed = discord.Embed(
                    title="Usuário Banido",
                    description=f"O jogador **{member.display_name}** foi suspenso da liga.",
                    color=discord.Color.red()
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.add_field(name="⏱️ Duração", value=time_str, inline=True)
                embed.add_field(name="⚖️ Admin", value=ctx.author.mention, inline=True)
                embed.add_field(name="📝 Motivo", value=reason, inline=False)
                embed.set_footer(text=f"ID: {member.id}")
                embed.timestamp = discord.utils.utcnow()
                await channel.send(embed=embed)

    @commands.command(name="unban")
    @commands.has_permissions(administrator=True)
    async def unban_player(self, ctx, member: discord.Member):
        bans = self.state_repo.get_bans()
        if str(member.id) in bans:
            del bans[str(member.id)]
            self.state_repo.save_bans(bans)
            await ctx.send(f"✅ {member.mention} foi desbanido da liga.")
        else:
            await ctx.send("Esse usuário não está banido.")

    @commands.command(name="resetstrike")
    @commands.has_permissions(administrator=True)
    async def reset_strike(self, ctx, member: discord.Member):
        players = self.state_repo.get_players()
        if str(member.id) in players:
            players[str(member.id)]["strikes"] = 0
            self.state_repo.save_players(players)
            await ctx.send(f"Strikes de {member.mention} resetados.")


async def setup(bot):
    await bot.add_cog(Admin(bot))
