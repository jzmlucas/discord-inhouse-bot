import datetime
import re

import discord
from discord.ext import commands, tasks

from src.database.storage.state import get_state_repository


class VIPManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state_repo = get_state_repository()
        self.role_name = "💎 MEMBRO VIP"
        self.check_vip_expiry.start()

    def cog_unload(self):
        self.check_vip_expiry.cancel()

    @tasks.loop(minutes=5)
    async def check_vip_expiry(self):
        vips = self.state_repo.get_vips()
        if not vips:
            return

        now_ts = datetime.datetime.now().timestamp()
        expired = [user_id for user_id, expiry in vips.items() if now_ts >= float(expiry)]
        if not expired:
            return

        for user_id in expired:
            for guild in self.bot.guilds:
                member = guild.get_member(int(user_id))
                if not member:
                    continue
                try:
                    role = discord.utils.get(guild.roles, name=self.role_name)
                    if role and role in member.roles:
                        await member.remove_roles(role)
                    if member.display_name.startswith("[VIP]"):
                        await member.edit(nick=member.display_name.replace("[VIP]", "").strip())
                except Exception as exc:
                    print(f"Erro ao limpar VIP de {user_id}: {exc}")
            del vips[user_id]

        self.state_repo.save_vips(vips)
        print(f"✅ [VIP System] Limpeza concluída: {len(expired)} expirados.")

    @check_vip_expiry.before_loop
    async def before_check_vip(self):
        await self.bot.wait_until_ready()

    @commands.command(name="setvip")
    @commands.has_permissions(administrator=True)
    async def set_vip(self, ctx, member: discord.Member, time_str: str):
        seconds_per_unit = {"m": 60, "h": 3600, "d": 86400}
        match = re.match(r"(\d+)([mhd])", time_str.lower())
        if not match:
            return await ctx.send("❌ Formato inválido! Use: `30d`, `7d`, `1h`.")

        amount, unit = match.groups()
        duration = int(amount) * seconds_per_unit[unit]
        expiry_timestamp = datetime.datetime.now().timestamp() + duration

        role = discord.utils.get(ctx.guild.roles, name=self.role_name)
        if not role:
            try:
                role = await ctx.guild.create_role(
                    name=self.role_name,
                    color=discord.Color.from_rgb(255, 0, 255),
                    hoist=True,
                    reason="Sistema de Liga VIP",
                )
            except discord.Forbidden:
                await ctx.send("⚠️ Erro: Não tenho permissão para criar cargos.")

        if role:
            try:
                await member.add_roles(role)
            except discord.Forbidden:
                await ctx.send("⚠️ Hierarquia insuficiente para dar o cargo.")

        if not member.display_name.startswith("[VIP]"):
            try:
                await member.edit(nick=f"[VIP] {member.display_name}"[:32])
            except discord.Forbidden:
                print(f"Sem permissão para mudar nick de {member.name}")

        vips = self.state_repo.get_vips()
        vips[str(member.id)] = float(expiry_timestamp)
        self.state_repo.save_vips(vips)
        await ctx.send(f"💎 **{member.display_name}** agora é VIP por {time_str}!")


async def setup(bot):
    await bot.add_cog(VIPManager(bot))
