import discord
from discord.ext import commands


class TitlesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _state(self):
        """Busca o estado atual do repositório."""
        return self.bot.state_repository.load()

    def _save(self, **kwargs):
        """Salva as alterações no repositório."""
        self.bot.state_repository.save(**kwargs)

    @commands.command(name="addtitle")
    @commands.has_permissions(administrator=True)
    async def add_title_registry(self, ctx, nome: str, emoji: str):
        """Admin: Cadastra um novo título e seu ícone no sistema global."""
        state = self._state()
        registry = state.get("titles_registry", {"Jogador": "👤"})

        registry[nome] = emoji
        self._save(titles_registry=registry)

        embed = discord.Embed(
            title="✅ Título Registrado",
            description=f"O título **{nome}** foi adicionado ao sistema com o ícone {emoji}.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command(name="titulos", aliases=["titles"])
    async def list_titles(self, ctx):
        """Lista os títulos que o jogador possui no inventário."""
        state = self._state()
        registry = state.get("titles_registry", {"Jogador": "👤"})
        user_titles_all = state.get("user_titles", {})
        user_data = user_titles_all.get(
            str(ctx.author.id), {"equipped": "Jogador", "inventory": ["Jogador"]})

        inventory = user_data.get("inventory", ["Jogador"])
        equipped = user_data.get("equipped", "Jogador")

        titles_list = ""
        for t in inventory:
            icon = registry.get(t, "❓")
            status = " ✅ *(Equipado)*" if t == equipped else ""
            titles_list += f"{icon} **{t}**{status}\n"

        embed = discord.Embed(
            title="🏷️ Seus Títulos Disponíveis",
            description=titles_list if titles_list else "Você só possui o título de Jogador.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Use !equipar <nome> para trocar seu título.")
        await ctx.send(embed=embed)

    @commands.command(name="equipar")
    async def equip_title(self, ctx, *, nome_titulo: str):
        """Equipa um título que o jogador já possui no inventário."""
        state = self._state()
        all_user_titles = state.get("user_titles", {})
        user_id_str = str(ctx.author.id)

        user_data = all_user_titles.get(
            user_id_str, {"equipped": "Jogador", "inventory": ["Jogador"]})

        inventory_lower = [t.lower() for t in user_data["inventory"]]
        if nome_titulo.lower() not in inventory_lower:
            return await ctx.send(f"❌ {ctx.author.mention}, você não possui o título `{nome_titulo}`!")

        titulo_real = user_data["inventory"][inventory_lower.index(
            nome_titulo.lower())]

        user_data["equipped"] = titulo_real
        all_user_titles[user_id_str] = user_data

        self._save(user_titles=all_user_titles)
        await ctx.send(f"✅ {ctx.author.mention}, seu título foi alterado para: **{titulo_real}**!")

    @commands.command(name="concedertitulo")
    @commands.has_permissions(administrator=True)
    async def give_title(self, ctx, member: discord.Member, *, nome_titulo: str):
        """Admin: Dá um título existente no registro para um jogador."""
        state = self._state()
        registry = state.get("titles_registry", {"Jogador": "👤"})

        if nome_titulo not in registry:
            return await ctx.send(
                f"❌ O título **{nome_titulo}** não existe no registro global. Use `!addtitle` primeiro.")

        all_user_titles = state.get("user_titles", {})
        user_id_str = str(member.id)

        user_data = all_user_titles.get(
            user_id_str, {"equipped": "Jogador", "inventory": ["Jogador"]})

        if nome_titulo not in user_data["inventory"]:
            user_data["inventory"].append(nome_titulo)
            all_user_titles[user_id_str] = user_data
            self._save(user_titles=all_user_titles)
            await ctx.send(f"✅ Título **{nome_titulo}** concedido a {member.mention}!")
        else:
            await ctx.send(f"⚠️ {member.mention} já possui o título **{nome_titulo}**.")


async def setup(bot):
    await bot.add_cog(TitlesCog(bot))
