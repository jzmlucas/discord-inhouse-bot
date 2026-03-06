import discord
from discord.ext import commands
import datetime
from src.database.storage.state import get_state_repository

state_repo = get_state_repository()

class ShopButton(discord.ui.Button):
    def __init__(self, item_id, info):
        super().__init__(
            label=f"{info['name']} ({info['cost']} MMR)",
            style=discord.ButtonStyle.secondary,
            custom_id=f"shop:{item_id}",
        )
        self.item_id = item_id
        self.cost = info["cost"]

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        
        mmr_data = state_repo.get_mmr()
        players = state_repo.get_players()
        vips = state_repo.get_vips()
        
        hoje = datetime.date.today().isoformat()
        user_data = players.get(user_id, {
            "double_down_tokens": 0, 
            "inventory": [], 
            "daily_purchase": {"date": hoje, "count": 0}
        })

        if self.item_id == "ficha_dd":
            agora = datetime.datetime.now().timestamp()
            is_vip = False
            if user_id in vips:
                try:
                    if agora < float(vips[user_id]):
                        is_vip = True
                except: pass
            
            limite_max = 3 if is_vip else 1
            daily_data = user_data.get("daily_purchase", {"date": hoje, "count": 0})
            
            if daily_data.get("date") != hoje:
                daily_data = {"date": hoje, "count": 0}
            
            if daily_data["count"] >= limite_max:
                msg_vip = "\n*Membros VIP podem comprar até 3 fichas por dia.*" if not is_vip else ""
                return await interaction.response.send_message(
                    f"**Limite atingido!**\nVocê já comprou `{daily_data['count']}/{limite_max}` fichas hoje.{msg_vip}",
                    ephemeral=True
                )
            
            daily_data["count"] += 1
            user_data["daily_purchase"] = daily_data

        current_mmr = mmr_data.get(user_id, 1000)
        if current_mmr < (self.cost + 1000):
            return await interaction.response.send_message(
                f"**Saldo Insuficiente!**\nVocê precisa manter uma reserva de **1000 MMR**.\n"
                f"Saldo: `{int(current_mmr)}` | Custo + Reserva: `{self.cost + 1000}`",
                ephemeral=True
            )

        mmr_data[user_id] = current_mmr - self.cost
        
        if self.item_id == "ficha_dd":
            user_data["double_down_tokens"] = user_data.get("double_down_tokens", 0) + 1
        else:
            if "inventory" not in user_data: user_data["inventory"] = []
            user_data["inventory"].append(self.item_id)

        players[user_id] = user_data
        
        state_repo.save_players_and_mmr(players, mmr_data)

        await interaction.response.send_message(
            f"**Compra realizada com sucesso!**\nItem: `{self.label}`\nSaldo Atual: `{int(mmr_data[user_id])} MMR`",
            ephemeral=True
        )

class ShopView(discord.ui.View):
    def __init__(self, bot, catalog):
        super().__init__(timeout=None)
        self.bot = bot
        for item_id, info in catalog.items():
            self.add_item(ShopButton(item_id, info))

class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state_repo = get_state_repository()

    @commands.command(name="addproduto")
    @commands.has_permissions(administrator=True)
    async def add_product(self, ctx, item_id: str, custo: int, *, nome: str):
        catalog = self.state_repo.get_shop_catalog()
        catalog[item_id] = {"cost": custo, "name": nome}
        self.state_repo.save_shop_catalog(catalog)
        await ctx.send(f"Produto `{nome}` (`{item_id}`) cadastrado por `{custo} MMR`!")

    @commands.command(name="loja")
    async def show_shop(self, ctx):
        catalog = self.state_repo.get_shop_catalog()
        mmr_data = self.state_repo.get_mmr()
        user_mmr = int(round(float(mmr_data.get(str(ctx.author.id), 1000))))

        if not catalog or "ficha_dd" not in catalog:
            catalog["ficha_dd"] = {"cost": 10, "name": "Ficha de Double Down"}
            self.state_repo.save_shop_catalog(catalog)

        embed = discord.Embed(
            title="Loja",
            description=(
                f"**Usuário:** {ctx.author.mention}\n"
                f"**Saldo:** `{user_mmr} MMR`\n\n"
                "**Limite de fichas de Double Down:**\n"
                "Jogador Comum: `1 unidade`/dia\n"
                "Jogador VIP: `3 unidades`/dia\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=0x2F3136
        )
        
        shop_list = ""
        for item_id, info in catalog.items():
            shop_list += f"**{info['name']}**\n└ Custo: `{info['cost']} MMR` | ID: `{item_id}`\n\n"
        
        embed.add_field(name="Itens em Estoque", value=shop_list or "Nenhum item disponível.", inline=False)
        embed.set_thumbnail(url="https://cdnb.artstation.com/p/assets/images/images/040/467/281/original/tetiana-parkhomenko-tatyana-parkhomenko-coin-rotation-fast.gif?1628942162")
        embed.set_footer(text="É obrigatório manter 1000 MMR de reserva após a compra.")
        
        await ctx.send(embed=embed, view=ShopView(self.bot, catalog))

    @commands.command(name="inventario", aliases=["inv"])
    async def inventory(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        players = self.state_repo.get_players()
        user_data = players.get(str(member.id), {})
        
        fichas = user_data.get("double_down_tokens", 0)
        itens = user_data.get("inventory", [])

        embed = discord.Embed(
            title="🎒 INVENTÁRIO",
            description=f"Exibindo itens de {member.mention}",
            color=0x2ECC71
        )
        embed.add_field(name="🃏 Fichas Double Down", value=f"Você possui **{fichas}** fichas disponíveis.", inline=False)
        
        if itens:
            embed.add_field(name="📦 Outros Itens", value="`" + "`, `".join(itens) + "`", inline=False)
        
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Use suas fichas durante a fase de draft!")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Shop(bot))
