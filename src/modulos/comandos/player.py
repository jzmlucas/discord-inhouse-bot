import datetime
import logging

import discord
from discord.ext import commands

from src.database.storage.state import get_state_repository
from src.modulos.comandos.services.profile_embed import build_profile_embed
from src.modulos.comandos.services.profile_heroes import OpenDotaHeroesService
from src.modulos.lobby.match import RemakeView
from src.ui.branding import BANNER_ATTACHMENT_URL, build_banner_file

logger = logging.getLogger("Profile.Cog")


class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state_repo = get_state_repository()
        self.heroes_service = OpenDotaHeroesService(logger)
        bot.loop.create_task(self.heroes_service.load_heroes())

    @commands.command(name="profile", aliases=["p", "rank", "perfil", "player"])
    async def profile(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        uid_str = str(member.id)

        state = self.state_repo.load()
        players_data = state.get("players", {})
        user_info = players_data.get(uid_str, {})
        heroes_display = await self.heroes_service.get_top_heroes_text(user_info.get("steam_id"))
        embed = build_profile_embed(member, uid_str, state, heroes_display)
        if embed.image and embed.image.url == BANNER_ATTACHMENT_URL:
            await ctx.send(embed=embed, file=build_banner_file())
        else:
            await ctx.send(embed=embed)

    @commands.command(name="remake", aliases=["rmk"])
    async def remake(self, ctx):
        match_cog = self.bot.get_cog("Match")
        if not match_cog:
            return await ctx.send("❌ Sistema de partidas não carregado.")

        channel_id = ctx.channel.id
        match_data = match_cog.active_matches.get(channel_id)
        if not match_data:
            return await ctx.send("❌ Este comando só funciona no canal de uma partida ativa.")
        if channel_id in match_cog.active_remakes:
            return await ctx.send("⚠️ Já existe uma votação de remake em andamento.")

        start_time = match_data.get("start_time", 0)
        now_ts = datetime.datetime.now().timestamp()
        if (now_ts - start_time) > 1800:
            return await ctx.send("O tempo de 30 minutos para remake expirou.")

        all_players = match_data["team1"] + match_data["team2"]
        view = RemakeView(match_cog, channel_id, all_players)
        match_cog.active_remakes[channel_id] = True
        await ctx.send(embed=view.create_embed(), view=view)

    @commands.command(name="setbanner")
    async def set_banner(self, ctx, url: str):
        uid_str = str(ctx.author.id)
        players_data = self.state_repo.get_players()
        vips = self.state_repo.get_vips()

        is_admin = ctx.author.guild_permissions.administrator
        is_vip = uid_str in vips
        if not is_admin and not is_vip:
            return await ctx.send("❌ Este comando é exclusivo para membros **VIP** ou **Staff**.")
        if not url.startswith("http"):
            return await ctx.send("❌ Envie uma URL de imagem válida (http/https).")
        if uid_str not in players_data:
            return await ctx.send("❌ Registre-se primeiro para usar este comando.")

        players_data[uid_str]["custom_banner"] = url
        self.state_repo.save_players(players_data)
        await ctx.send("**Seu banner personalizado foi atualizado!**")

    @commands.command(name="fichas", aliases=["dd"])
    async def consultar_fichas(self, ctx):
        players = self.state_repo.get_players()
        user_id = str(ctx.author.id)
        if user_id not in players:
            return await ctx.send("❌ Você ainda não está registrado na liga.")

        tokens = players[user_id].get("double_down_tokens", 0)
        embed = discord.Embed(
            title="🃏 SUAS FICHAS",
            description=f"Olá {ctx.author.mention}, aqui está o seu saldo.",
            color=0x9B59B6,
        )
        embed.add_field(name="Fichas de Double Down", value=f"💎 `{tokens}` unidades", inline=True)
        embed.set_footer(text="Use !doubledown no início da partida para apostar o dobro!")
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Profile(bot))
    print("Módulo Profile (Auto Hero Loader) carregado com sucesso!")
