import datetime

import discord

from src.database.storage.state import get_state_repository
from src.modulos.lobby.constants import (
    DEFAULT_MEDAL_ICON,
    DEFAULT_TITLE_REGISTRY,
    MAX_PLAYERS,
    MEDAL_ICONS,
    VIP_TAG_ID,
)
from src.ui.branding import BANNER_ATTACHMENT_URL, PRIMARY_COLOR


state_repo = get_state_repository()

MEDAL_FALLBACK_BY_NAME = {
    "Aralto": "Herald",
    "Guardião": "Guardian",
    "Cruzado": "Crusader",
    "Arconte": "Archon",
    "Lenda": "Lenda",
    "Ancient": "Ancient",
    "Divine": "Divine",
    "Imortal": "Imortal",
    "Herald": "Herald",
    "Guardian": "Guardian",
    "Crusader": "Crusader",
    "Archon": "Archon",
}


def _resolve_medal_icon(player_info: dict) -> str:
    medal_icon = player_info.get("medal_icon")
    if medal_icon:
        return str(medal_icon)

    medal_name = player_info.get("medal", "Herald")
    medal_key = MEDAL_FALLBACK_BY_NAME.get(str(medal_name), "Herald")
    return MEDAL_ICONS.get(medal_key, DEFAULT_MEDAL_ICON)


def build_queue_embed(
    bot,
    queue,
    confirmation_active,
    queue_start_time,
    next_reset,
    guild=None,
):
    mmr_data = state_repo.get_mmr()
    vips_data = state_repo.get_vips()
    players_data = state_repo.get_players()
    registry = state_repo.get("titles_registry", DEFAULT_TITLE_REGISTRY)
    user_titles = state_repo.get("user_titles", {})

    current_count = len(queue)
    is_full = current_count >= MAX_PLAYERS
    embed_color = 0x880808 if is_full else PRIMARY_COLOR
    reset_timestamp = int(next_reset.timestamp())

    if queue and queue_start_time:
        time_status = f"**Tempo de fila:** <t:{int(queue_start_time)}:R>"
    else:
        time_status = "**Aguardando jogadores entrarem na fila...**"

    server_name = guild.name if guild else "InHouse Queue"
    embed = discord.Embed(
        title=server_name.upper(),
        description=(
            f"**STATUS:** `{'Aguardando Confirmação' if confirmation_active else 'Fila Aberta'}`\n"
            f"**Jogadores na fila:** `{current_count}/{MAX_PLAYERS}`\n"
            f"{time_status}\n"
            f"**Fila resetando em:** <t:{reset_timestamp}:R>\n"
        ),
        color=embed_color,
    )

    radiant, dire = [], []

    for i in range(MAX_PLAYERS):
        if i < len(queue):
            uid = queue[i]
            uid_str = str(uid)
            user = bot.get_user(uid)
            nome = user.display_name if user else "Jogador"
            vip_tag = VIP_TAG_ID if uid_str in vips_data else "🔹"  
            equipped = user_titles.get(uid_str, {}).get("equipped", "Jogador")
            icone_titulo = registry.get(equipped, "")
            p_info = players_data.get(uid_str, {})
            icon_medalha = _resolve_medal_icon(p_info)
            mmr_int = int(round(float(mmr_data.get(uid_str, 1000))))
            warning_emoji = " ⚠️" if p_info.get("strikes", 0) > 0 else ""
            line = f"{vip_tag}{icone_titulo}{icon_medalha} **{nome}** ({mmr_int} 🏆){warning_emoji}"
        else:
            line = ""

        if i < 5:
            radiant.append(line)
        else:
            dire.append(line)

    embed.add_field(name="Time 1", value="\n".join(radiant), inline=True)
    embed.add_field(name="Time 2", value="\n".join(dire), inline=True)
    embed.set_image(url=BANNER_ATTACHMENT_URL)
    embed.set_footer(text="🌐 LaLiga • Matchmaking valendo pontos")
    return embed


def build_confirmation_embed(current_match_players, confirmed, remaining_time):
    end_time = int(datetime.datetime.now().timestamp() + remaining_time)
    embed = discord.Embed(title="Partida Encontrada", color=PRIMARY_COLOR)
    embed.description = f"Clique em aceitar para jogar!\n**Expira em:** <t:{end_time}:R>"

    total = len(current_match_players)
    conf = len(confirmed)
    bar = "🟥" * conf + "⬛" * (total - conf) if total > 0 else "⬛" * 10

    embed.add_field(name="", value=f"{bar} `{conf}/{total}`", inline=False)
    half = (total + 1) // 2
    p1, p2 = current_match_players[:half], current_match_players[half:]

    def get_status_list(players):
        if not players:
            return "---"
        return "\n".join([f"{'🟢' if uid in confirmed else '⚪'} <@{uid}>" for uid in players])

    embed.add_field(name="Jogadores", value=get_status_list(p1), inline=True)
    embed.add_field(name="‎", value=get_status_list(p2), inline=True)
    embed.set_footer(text="A partida será cancelada se algum jogador recusar ou não aceitar a partida.")
    return embed
