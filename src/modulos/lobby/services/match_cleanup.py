import discord


async def ensure_playing_role(guild):
    role = discord.utils.get(guild.roles, name="Atualmente Jogando")
    if not role:
        role = await guild.create_role(name="Atualmente Jogando", color=discord.Color.orange())
    return role


async def add_role_to_players(guild, role, player_ids):
    for user_id in player_ids:
        try:
            member = guild.get_member(user_id) or await guild.fetch_member(user_id)
            if member:
                await member.add_roles(role)
        except Exception as exc:
            print(f"[ERRO] add_roles: {exc}")


async def remove_role_from_players(guild, role, player_ids):
    if not role:
        return
    for uid in player_ids:
        try:
            member = guild.get_member(uid) or await guild.fetch_member(uid)
            if member:
                await member.remove_roles(role)
        except Exception as exc:
            print(f"[ERRO] remove_roles: {exc}")


async def delete_match_channels(bot, channel_ids):
    for ch_id in channel_ids:
        channel = bot.get_channel(ch_id)
        if channel:
            await channel.delete()
