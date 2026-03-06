import datetime
import re
import asyncio
import time
import aiohttp
import discord
from pathlib import Path
from discord import ui
from discord.ext import commands

from src.database.storage.state import get_state_repository
from src.modulos.lobby.constants import DEFAULT_MEDAL_ICON, MEDAL_ICONS
from src.ui.branding import BANNER_ATTACHMENT_URL, PRIMARY_COLOR, build_banner_file

MEDAL_IMAGES = {
    "Aralto": "herald.webp",
    "Guardião": "guardian.webp",
    "Cruzado": "crusader.webp",
    "Arconte": "archon.webp",
    "Lenda": "legends.webp",
    "Ancient": "ancient.webp",
    "Divine": "divine.webp",
    "Imortal": "immortal.webp",
}

MEDAL_ICONS_PATH = Path(__file__).resolve(
).parent.parent.parent / "ui" / "icons"


def get_medal_image_file(medal_name: str) -> discord.File | None:
    """Retorna um discord.File para a medalha especificada."""
    filename = MEDAL_IMAGES.get(medal_name, "herald.webp")
    image_path = MEDAL_ICONS_PATH / filename
    if image_path.exists():
        return discord.File(str(image_path), filename=filename)
    return None


ROLE_IMAGES = {
    "HC": "hc.png",
    "MID": "mid.png",
    "OFFLANE": "off.png",
    "SUP 4": "sup4.png",
    "SUP 5": "sup5.png"
}

ROLE_ICONS_PATH = Path(__file__).resolve(
).parent.parent.parent / "ui" / "icons" / "roles"


def get_role_image_file(role_name: str) -> discord.File | None:
    """Retorna um discord.File para a role especificada."""
    filename = ROLE_IMAGES.get(role_name, "hc.png")
    image_path = ROLE_ICONS_PATH / filename
    if image_path.exists():
        return discord.File(str(image_path), filename=filename)
    return None


ROLE_EMOJIS = {
    "HC": "⚔️", "MID": "☀️", "OFFLANE": "🛡️", "SUP 4": "💉", "SUP 5": "📜"
}

THEME_COLOR = PRIMARY_COLOR
SUCCESS_COLOR = 0x00ff7f
ERROR_COLOR = 0xff4b4b
state_repo = get_state_repository()
OPENDOTA_MIN_INTERVAL = 0.35
OPENDOTA_MAX_CONCURRENT = 2
DEFAULT_RETRY_AFTER = 5
OPENDOTA_CACHE_TTL_SECONDS = 300
REGISTRATION_MEDAL_KEYS = {
    "Aralto": "Herald",
    "Guardião": "Guardian",
    "Cruzado": "Crusader",
    "Arconte": "Archon",
    "Lenda": "Lenda",
    "Ancient": "Ancient",
    "Divine": "Divine",
    "Imortal": "Imortal",
}


class OpenDotaRateLimitError(Exception):
    def __init__(self, retry_after: int):
        super().__init__("OpenDota rate limited")
        self.retry_after = retry_after


class OpenDotaRateLimiter:
    def __init__(self, min_interval_seconds: float):
        self.min_interval_seconds = min_interval_seconds
        self._last_request_at = 0.0
        self._lock = asyncio.Lock()

    async def wait_turn(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_at
            if elapsed < self.min_interval_seconds:
                await asyncio.sleep(self.min_interval_seconds - elapsed)
            self._last_request_at = time.monotonic()


_OPENDOTA_LIMITER = OpenDotaRateLimiter(OPENDOTA_MIN_INTERVAL)
_OPENDOTA_SEMAPHORE = asyncio.Semaphore(OPENDOTA_MAX_CONCURRENT)
_OPENDOTA_CACHE = {}
_OPENDOTA_CACHE_LOCK = asyncio.Lock()


def _parse_retry_after(value):
    if not value:
        return DEFAULT_RETRY_AFTER
    try:
        parsed = int(float(value))
    except (ValueError, TypeError):
        return DEFAULT_RETRY_AFTER
    return max(1, min(parsed, 60))


async def _request_opendota_json(session: aiohttp.ClientSession, url: str, retries: int = 2):
    for attempt in range(retries + 1):
        await _OPENDOTA_LIMITER.wait_turn()
        async with _OPENDOTA_SEMAPHORE:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                if response.status == 429:
                    retry_after = _parse_retry_after(
                        response.headers.get("Retry-After"))
                    if attempt == retries:
                        raise OpenDotaRateLimitError(retry_after)
                    await asyncio.sleep(retry_after)
                    continue
                return None
    raise OpenDotaRateLimitError(DEFAULT_RETRY_AFTER)


def resolve_registration_medal_icon(medal_name: str, dota_mmr_estimate) -> str:
    """Resolve medal icon during registration. Prefers Dota MMR estimate if available."""
    mmr_value = None
    try:
        if dota_mmr_estimate is not None:
            mmr_value = int(round(float(dota_mmr_estimate)))
    except (TypeError, ValueError):
        mmr_value = None

    if mmr_value is not None and mmr_value > 0:
        if mmr_value >= 9000:
            key = "Imortal 9k"
        elif mmr_value >= 8000:
            key = "Imortal 8k"
        elif mmr_value >= 6000:
            key = "Imortal"
        elif mmr_value >= 5000:
            key = "Divine"
        elif mmr_value >= 4000:
            key = "Ancient"
        elif mmr_value >= 3000:
            key = "Lenda"
        elif mmr_value >= 2300:
            key = "Archon"
        elif mmr_value >= 1540:
            key = "Crusader"
        elif mmr_value >= 770:
            key = "Guardian"
        else:
            key = "Herald"
    else:
        key = REGISTRATION_MEDAL_KEYS.get(medal_name, "Herald")

    return MEDAL_ICONS.get(key, DEFAULT_MEDAL_ICON)


def validate_input(input_text):
    text = input_text.strip()
    if "/matches/" in text or "/heroes/" in text:
        return None, "Use o link do seu **Perfil**, não de uma partida ou herói."

    match = re.search(r'(?:players/|profiles/)?(\d{5,17})', text)
    if match:
        extracted_id = int(match.group(1))
        # Se o ID for menor que 76561197960265728, é um SteamID32, então convertemos para 64
        if extracted_id < 76561197960265728:
            extracted_id += 76561197960265728
        return str(extracted_id), None

    return None, "Formato inválido! Insira o ID numérico ou link do Dotabuff/OpenDota."


async def get_dota_data(steam_id_64):
    async with _OPENDOTA_CACHE_LOCK:
        cached = _OPENDOTA_CACHE.get(steam_id_64)
        if cached and (time.monotonic() - cached["ts"]) < OPENDOTA_CACHE_TTL_SECONDS:
            return dict(cached["data"])

    # Converte para 32 para a API
    steam_id_32 = int(steam_id_64) - 76561197960265728

    urls = [
        f"https://api.opendota.com/api/players/{steam_id_32}",
        f"https://api.opendota.com/api/players/{steam_id_32}/wl"
    ]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        try:
            data = await _request_opendota_json(session, urls[0], retries=2)
            if not data or not data.get("profile"):
                return None

            wl = await _request_opendota_json(session, urls[1], retries=1)
            if not wl:
                wl = {"win": 0, "lose": 0}

            result = {
                "tier": data.get("rank_tier"),
                "mmr": data.get("mmr_estimate", {}).get("estimate", 0),
                "name": data["profile"].get("personaname", "Player"),
                "avatar": data["profile"].get("avatarfull"),
                "games": wl.get("win", 0) + wl.get("lose", 0),
                "steam_id": steam_id_64  # Salvando o ID de 17 dígitos
            }
            async with _OPENDOTA_CACHE_LOCK:
                _OPENDOTA_CACHE[steam_id_64] = {
                    "ts": time.monotonic(), "data": result}
            return dict(result)
        except OpenDotaRateLimitError as exc:
            return {"error": "rate_limited", "retry_after": exc.retry_after}
        except:
            return None


class RoleSelectView(ui.View):
    def __init__(self, data, medal_name):
        super().__init__(timeout=120)
        self.data = data
        self.medal_name = medal_name
        self.selected_roles = []

    async def process_registration(self, interaction: discord.Interaction):
        """Processa o cadastro com as roles selecionadas."""
        await interaction.response.defer(ephemeral=True)

        players = state_repo.get_players()
        mmr_data = state_repo.get_mmr()

        uid_str = str(interaction.user.id)
        players[uid_str] = {
            "name": self.data['name'],
            "positions": self.selected_roles,
            "medal": self.medal_name,
            "medal_icon": resolve_registration_medal_icon(self.medal_name, self.data.get("mmr")),
            "dota_mmr_estimate": int(round(float(self.data.get("mmr") or 0))),
            "steam_id": str(self.data['steam_id']),
            "registered_at": datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        }
        mmr_data[uid_str] = 1000
        state_repo.save_players_and_mmr(players, mmr_data)

        guild = interaction.guild
        roles_to_add = []
        for r_name in ["Jogador", self.medal_name] + self.selected_roles:
            role = discord.utils.get(guild.roles, name=r_name)
            if role:
                roles_to_add.append(role)

        try:
            all_possible_roles = list(
                MEDAL_IMAGES.keys()) + list(ROLE_EMOJIS.keys()) + ["Jogador"]
            to_remove = [
                r for r in interaction.user.roles if r.name in all_possible_roles]
            await interaction.user.remove_roles(*to_remove)
            await interaction.user.add_roles(*roles_to_add)
            await interaction.user.edit(nick=f"{self.data['name'][:25]}")
        except:
            pass

        cog = interaction.client.get_cog("RegisterCog")
        if cog:
            await cog.send_registration_log(interaction.user, self.data, self.selected_roles, self.medal_name)

        embed = discord.Embed(
            title="Cadastro realizado",
            description=f"Bem-vindo à liga, **{self.data['name']}**!\nSeu perfil foi vinculado e os cargos aplicados.",
            color=SUCCESS_COLOR
        )
        embed.set_thumbnail(url=self.data['avatar'])
        await interaction.edit_original_response(content=None, embed=embed, view=None)

    async def update_buttons(self, interaction: discord.Interaction):
        """Atualiza o estado visual dos botões."""
        for item in self.children:
            if isinstance(item, ui.Button) and item.custom_id and item.custom_id.startswith("role_"):
                role_name = item.custom_id.replace("role_", "")
                if role_name in self.selected_roles:
                    item.style = discord.ButtonStyle.success
                    item.label = f"✓ {role_name}"
                else:
                    item.style = discord.ButtonStyle.primary
                    item.label = role_name
                item.disabled = len(
                    self.selected_roles) == 2 and role_name not in self.selected_roles

    @ui.button(label="HC", style=discord.ButtonStyle.primary, custom_id="role_HC", emoji=ROLE_EMOJIS["HC"])
    async def hc_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.toggle_role("HC", interaction)

    @ui.button(label="MID", style=discord.ButtonStyle.primary, custom_id="role_MID", emoji=ROLE_EMOJIS["MID"])
    async def mid_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.toggle_role("MID", interaction)

    @ui.button(label="OFFLANE", style=discord.ButtonStyle.primary, custom_id="role_OFFLANE", emoji=ROLE_EMOJIS["OFFLANE"])
    async def offlane_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.toggle_role("OFFLANE", interaction)

    @ui.button(label="SUP 4", style=discord.ButtonStyle.primary, custom_id="role_SUP 4", emoji=ROLE_EMOJIS["SUP 4"])
    async def sup4_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.toggle_role("SUP 4", interaction)

    @ui.button(label="SUP 5", style=discord.ButtonStyle.primary, custom_id="role_SUP 5", emoji=ROLE_EMOJIS["SUP 5"])
    async def sup5_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.toggle_role("SUP 5", interaction)

    async def toggle_role(self, role_name: str, interaction: discord.Interaction):
        """Alterna a seleção de uma role."""
        if role_name in self.selected_roles:
            self.selected_roles.remove(role_name)
        else:
            if len(self.selected_roles) < 2:
                self.selected_roles.append(role_name)

        await self.update_buttons(interaction)
        await interaction.response.edit_message(view=self)

        if len(self.selected_roles) == 2:
            self.clear_items()
            confirmar = ui.Button(
                label="Confirmar Roles", style=discord.ButtonStyle.green, custom_id="confirm_roles")
            confirmar.callback = self.confirm_callback
            self.add_item(confirmar)
            await interaction.edit_original_response(view=self)

    async def confirm_callback(self, interaction: discord.Interaction):
        """Callback para confirmar as roles selecionadas."""
        await self.process_registration(interaction)


class SteamIDModal(ui.Modal, title="Cadastro de ID"):
    steam_input = ui.TextInput(
        label="ID Steam ou Link Dotabuff",
        placeholder="Ex: 12345678 ou link do perfil...",
        min_length=5, required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        steam_id, error = validate_input(self.steam_input.value)
        if error:
            return await interaction.followup.send(error, ephemeral=True)

        data = await get_dota_data(steam_id)
        if data and data.get("error") == "rate_limited":
            return await interaction.followup.send(
                f"OpenDota está com muitas requisições (HTTP 429). Aguarde ~{data['retry_after']}s e tente novamente.",
                ephemeral=True,
            )
        if not data:
            return await interaction.followup.send(
                "Perfil privado ou não encontrado. Ative 'Expor Dados Públicos' no jogo.", ephemeral=True)

        if data['games'] < 200:
            return await interaction.followup.send(
                f"Sua conta possui apenas `{data['games']}` partidas. Você deve ter pelo menos 200.", ephemeral=True)

        tier_map = {1: "Aralto", 2: "Guardião", 3: "Cruzado", 4: "Arconte", 5: "Lenda", 6: "Ancient", 7: "Divine",
                    8: "Imortal"}
        medal_name = tier_map.get((data['tier'] or 10) // 10, "Aralto")

        embed = discord.Embed(title="Perfil encontrado", color=THEME_COLOR)
        embed.set_author(name=data['name'], icon_url=data['avatar'])
        embed.add_field(name="Rank Estimado",
                        value=f"**{medal_name}**", inline=True)
        embed.add_field(name="Partidas",
                        value=f"`{data['games']}`", inline=True)

        view = RoleSelectView(data, medal_name)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class ConfirmDeleteView(ui.View):
    def __init__(self):
        super().__init__(timeout=30)

    @ui.button(label="Sim, apagar meus dados", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        if any(r.name == "Banido" for r in interaction.user.roles):
            return await interaction.response.edit_message(content="Usuários banidos não podem apagar seus dados.",
                                                           embed=None, view=None)

        uid_str = str(interaction.user.id)
        state = state_repo.load()

        data_keys = ["players", "mmr", "vips",
                     "bans", "strikes", "stats", "history"]
        removed_anything = False

        for key in data_keys:
            current_dict = state.get(key, {})
            if uid_str in current_dict:
                del current_dict[uid_str]
                removed_anything = True

        if removed_anything:
            state_repo.update(**state)

            try:
                guild = interaction.guild
                all_roles_names = list(MEDAL_IMAGES.keys()) + list(ROLE_EMOJIS.keys()) + ["Jogador", "VIP", "Banido",
                                                                                          "Strike"]
                to_remove = [
                    r for r in interaction.user.roles if r.name in all_roles_names]
                await interaction.user.remove_roles(*to_remove)
                if interaction.user.display_name != interaction.user.name:
                    await interaction.user.edit(nick=None)
            except:
                pass

            cog = interaction.client.get_cog("RegisterCog")
            if cog:
                await cog.send_deletion_log(interaction.user)

            await interaction.response.edit_message(
                content="**Perfil Encerrado.** Seus dados, VIP e cargos foram limpos.",
                embed=None, view=None
            )
        else:
            await interaction.response.edit_message(content="Nenhum dado encontrado para sua conta.", embed=None,
                                                    view=None)


class RegisterView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Iniciar Cadastro", style=discord.ButtonStyle.success, custom_id="reg_start")
    async def register_button(self, interaction: discord.Interaction, button: ui.Button):
        if any(r.name == "Banido" for r in interaction.user.roles):
            return await interaction.response.send_message("Você está banido e não pode realizar um novo cadastro.",
                                                           ephemeral=True)

        state = state_repo.load()
        if str(interaction.user.id) in state.get("players", {}):
            return await interaction.response.send_message("Você já está cadastrado!", ephemeral=True)
        await interaction.response.send_modal(SteamIDModal())

    @ui.button(label="Remover Cadastro", style=discord.ButtonStyle.secondary, custom_id="reg_remove")
    async def remove_button(self, interaction: discord.Interaction, button: ui.Button):
        if any(r.name == "Banido" for r in interaction.user.roles):
            return await interaction.response.send_message(
                "Usuários banidos não podem remover dados do sistema. Entre em contato com algum moderador.",
                ephemeral=True)

        embed = discord.Embed(
            title="Limpeza de perfil",
            description=(
                "Esta ação é **irreversível** e apagará:\n\n"
                "⚠️ **Progresso:** MMR, Rank e Medalhas.\n"
                "⚠️ **Vantagens:** Status VIP e benefícios.\n"
                "⚠️ **Histórico:** Banimentos e Strikes acumulados.\n"
                "⚠️ **Cargos:** Todas as tags da liga no Discord.\n\n"
                "**Tem certeza de que deseja resetar sua identidade na liga?**"
            ),
            color=THEME_COLOR
        )
        await interaction.response.send_message(embed=embed, view=ConfirmDeleteView(), ephemeral=True)


class RegisterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="setregistro", aliases=["settestregistro"])
    @commands.has_permissions(administrator=True)
    async def setregistro(self, ctx):
        embed = discord.Embed(
            title="Cadastro",
            description=(
                "Realize o cadastro para jogar.\n\n"
                "**Requisitos**\n"
                "🔹 `200+` Partidas jogadas no total\n"
                "🔹 Perfil de Dados `Público` no Dota\n\n"
                "**Como realizar o cadastro**\n"
                "Clique no botão abaixo e insira seu ID do Dota ou link do Dotabuff\n"
                "*O sistema buscará seus dados automaticamente.*"
            ),
            color=THEME_COLOR
        )
        embed.set_image(url=BANNER_ATTACHMENT_URL)
        await ctx.send(embed=embed, view=RegisterView(), file=build_banner_file())
        await ctx.message.delete()

    @commands.command(name="setlog")
    @commands.has_permissions(administrator=True)
    async def setlog(self, ctx):
        state_repo.set_section("log_channel_id", ctx.channel.id)
        await ctx.send(f"**Canal de logs da Staff definido:** {ctx.channel.mention}")

    async def send_registration_log(self, user, data, roles, medal):
        channel = self.bot.get_channel(state_repo.get("log_channel_id"))
        if not channel:
            return

        embed = discord.Embed(title="Jogador cadastrado",
                              color=SUCCESS_COLOR, timestamp=discord.utils.utcnow())
        embed.set_thumbnail(url=data['avatar'])
        embed.add_field(
            name="Usuário", value=f"{user.mention} (`{user.id}`)", inline=False)
        embed.add_field(name="Steam", value=f"[{data['name']}](https://www.dotabuff.com/players/{data['steam_id']})",
                        inline=True)
        embed.add_field(name="Medalha", value=f"**{medal}**", inline=True)
        embed.add_field(name="Roles", value=" | ".join(
            [f"`{r}`" for r in roles]), inline=False)

        await channel.send(embed=embed)

    async def send_deletion_log(self, user):
        channel = self.bot.get_channel(state_repo.get("log_channel_id"))
        if not channel:
            return

        embed = discord.Embed(
            title="Jogador removeu perfil",
            description=f"O usuário {user.mention} deletou todos os seus dados da liga.",
            color=discord.Color.dark_grey(),
            timestamp=discord.utils.utcnow()
        )
        await channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(RegisterCog(bot))
