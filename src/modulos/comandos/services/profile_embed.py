import datetime

import discord

from src.database.storage.ranking import get_medal, get_next_rank_info
from src.ui.branding import BANNER_ATTACHMENT_URL, PRIMARY_COLOR

DEFAULT_BANNER = BANNER_ATTACHMENT_URL


def build_profile_embed(member, uid_str, state, heroes_display: str):
    mmr_data = state.get("mmr", {})
    vips = state.get("vips", {})
    players_data = state.get("players", {})
    user_titles = state.get("user_titles", {})
    registry = state.get("titles_registry", {"Jogador": "👤"})

    user_mmr = mmr_data.get(uid_str, 1000)
    user_info = players_data.get(uid_str, {})
    now_ts = datetime.datetime.now().timestamp()

    is_vip = False
    exp_date = None
    if uid_str in vips:
        try:
            expiry_ts = float(vips[uid_str])
            if now_ts < expiry_ts:
                is_vip = True
                exp_date = datetime.datetime.fromtimestamp(expiry_ts).strftime("%d/%m/%Y")
        except Exception:
            pass

    color = discord.Color.from_rgb(0, 255, 255) if is_vip else discord.Color(PRIMARY_COLOR)

    equipped_name = user_titles.get(uid_str, {}).get("equipped", "Jogador")
    title_icon = registry.get(equipped_name, "👤")
    medal = get_medal(user_mmr)

    strikes = user_info.get("strikes", 0)
    last_strike = user_info.get("last_strike_at", 0)
    exp_strike_ts = int(last_strike + 604800)
    strike_status = (
        f"⚠{strikes} Strike(s) — <t:{exp_strike_ts}:R>"
        if strikes > 0 and now_ts < exp_strike_ts
        else "✅ Limpo"
    )

    embed = discord.Embed(title=f"Perfil de {member.display_name}", color=color)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Medalha", value=f"**{medal}**", inline=True)
    embed.add_field(name="MMR", value=f"`{int(user_mmr)}`", inline=True)
    embed.add_field(name="Título", value=f"{title_icon} {equipped_name}", inline=True)
    embed.add_field(name="Heróis mais jogados nos últimos 90 dias", value=heroes_display, inline=False)
    embed.add_field(name="Strikes na liga", value=strike_status, inline=True)

    next_rank, missing = get_next_rank_info(user_mmr)
    progresso = f"Faltam `{missing}` para **{next_rank}**" if next_rank != "Máximo" else "🔥 Nível Máximo"

    if is_vip:
        embed.add_field(name="💎 Premium", value=f"Expira em: `{exp_date}`\n{progresso}", inline=False)
    else:
        embed.add_field(name="Progresso de Medalha", value=progresso, inline=False)

    banner = user_info.get("custom_banner", DEFAULT_BANNER)
    embed.set_image(url=banner)
    embed.set_footer(text="Perfil LaLiga • ")
    embed.timestamp = discord.utils.utcnow()
    return embed
