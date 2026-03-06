import asyncio
import datetime
from collections import defaultdict

import discord
from discord.ext import commands

from src.database.storage.state import get_state_repository
from src.modulos.lobby.runtime_state import MatchRuntimeState
from src.modulos.lobby.services.match_cleanup import (
    add_role_to_players,
    delete_match_channels,
    ensure_playing_role,
    remove_role_from_players,
)
from src.modulos.lobby.services.match_draft import create_initial_match_data
from src.modulos.lobby.services.match_results import (
    apply_match_result,
    calculate_mmr_gain,
    refund_double_down_tokens,
)

from .double_down_view import DoubleDownView
from .draft_view import DraftView
from .win_voting_view import WinVotingView


class Match(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state_repo = get_state_repository()
        self.runtime = MatchRuntimeState()
        self.match_locks = defaultdict(asyncio.Lock)
        self.start_match_lock = asyncio.Lock()

    @property
    def active_matches(self):
        return self.runtime.active_matches

    @active_matches.setter
    def active_matches(self, value):
        self.runtime.active_matches = value

    @property
    def active_remakes(self):
        return self.runtime.active_remakes

    @active_remakes.setter
    def active_remakes(self, value):
        self.runtime.active_remakes = value

    def _telemetry(self):
        return getattr(self.bot, "telemetry", None)

    def _get_match_lock(self, channel_id: int):
        return self.match_locks[channel_id]

    async def _update_watch_panel(self, guild):
        if not guild:
            return
        watch_cog = self.bot.get_cog("WatchManager")
        if watch_cog:
            await watch_cog.update_panel(guild)

    def _remove_match_entry(self, channel_id: int):
        self.active_matches.pop(channel_id, None)
        self.active_remakes.pop(channel_id, None)

    async def process_remake_cancel(self, channel_id):
        lock = self._get_match_lock(channel_id)
        async with lock:
            match_data = self.active_matches.get(channel_id)
            if not match_data:
                return
            if match_data.get("closing") or match_data.get("remake_processed"):
                return
            match_data["closing"] = True
            match_data["remake_processed"] = True
            active_doubles = list(match_data.get("active_doubles", []))
            all_players = match_data["team1"] + match_data["team2"]
            channels = list(match_data.get("channels", []))
            guild_id = match_data["guild_id"]
            telemetry = self._telemetry()
            if telemetry:
                telemetry.inc("match.remake.processed")

        if active_doubles:
            players = self.state_repo.get_players()
            refund_double_down_tokens(players, active_doubles)
            self.state_repo.save_players(players)

        guild = self.bot.get_guild(guild_id)
        channel = self.bot.get_channel(channel_id)
        if channel:
            await channel.send("**Remake aprovado.** Fichas de Double Down foram devolvidas e o MMR foi inalterado.")

        await asyncio.sleep(5)
        role = discord.utils.get(guild.roles, name="Atualmente Jogando") if guild else None
        await delete_match_channels(self.bot, channels)
        if guild:
            await remove_role_from_players(guild, role, all_players)

        async with lock:
            self._remove_match_entry(channel_id)
        await self._update_watch_panel(guild)

    def create_match_embed(self, match_data):
        mmr_data = self.state_repo.get_mmr()
        players_data = self.state_repo.get_players()

        def get_mmr(uid):
            return mmr_data.get(str(uid), 1000)

        def get_player_name(uid):
            player = players_data.get(str(uid), {})
            if player.get("name"):
                return player["name"]
            user = self.bot.get_user(uid)
            if user:
                return user.display_name
            return f"ID: {uid}"

        match_label = match_data.get("custom_id", f"#{match_data['match_id']}")
        embed = discord.Embed(title=f"Seleção de Jogadores: {match_label}", color=discord.Color.dark_grey())

        team_1_list = [f"• **{get_player_name(uid)}** `({get_mmr(uid)})`" for uid in match_data["team1"]]
        team_2_list = [f"• **{get_player_name(uid)}** `({get_mmr(uid)})`" for uid in match_data["team2"]]
        sum_t1 = sum(get_mmr(uid) for uid in match_data["team1"])
        sum_t2 = sum(get_mmr(uid) for uid in match_data["team2"])

        embed.add_field(name=f"🔵 Radiant (Total: {sum_t1})", value="\n".join(team_1_list) if team_1_list else "Vazio", inline=True)
        embed.add_field(name=f"🔴 Dire (Total: {sum_t2})", value="\n".join(team_2_list) if team_2_list else "Vazio", inline=True)

        pool_list = [f"• **{get_player_name(uid)}** `({get_mmr(uid)})`" for uid in match_data["pool"]]
        embed.add_field(
            name="Jogadores Disponíveis",
            value="\n".join(pool_list) if pool_list else "Seleção Concluída!",
            inline=False,
        )

        if match_data["pool"]:
            current_turn_uid = match_data["sequence"][match_data["step"]]
            current_turn_name = get_player_name(current_turn_uid)
            end_time = int(datetime.datetime.now().timestamp() + 45)
            embed.description = f"Vez de escolha: **{current_turn_name}**\nTempo restante: <t:{end_time}:R>"
        else:
            embed.description = f"**Draft encerrado! Salas criadas para o lobby {match_label}...**"
        return embed

    async def start_new_match(self, channel, players_list):
        async with self.start_match_lock:
            mmr_data = self.state_repo.get_mmr()
            match_id_num = self.state_repo.get("last_match_id", 0) + 1
            match_data = create_initial_match_data(
                players_list=players_list,
                mmr_data=mmr_data,
                match_id_num=match_id_num,
                guild_id=channel.guild.id,
            )
            self.active_matches[channel.id] = match_data
            telemetry = self._telemetry()
            if telemetry:
                telemetry.inc("match.created")

        await channel.send(
            f"*Os capitães são os jogadores com maiores MMR:* "
            f"<@{match_data['cap1']}> e <@{match_data['cap2']}>"
        )

        if not match_data["pool"]:
            await channel.send(embed=self.create_match_embed(match_data))
            await asyncio.sleep(1)
            await self.finalize_match(channel.guild, match_data, channel.id)
        else:
            msg = await channel.send(embed=self.create_match_embed(match_data))
            view = DraftView(self, channel.id, message=msg)
            await msg.edit(view=view)

    async def finalize_match(self, guild, match_data, old_key):
        lock = self._get_match_lock(old_key)
        async with lock:
            if match_data.get("finalized"):
                return
            match_data["finalized"] = True
        started = asyncio.get_event_loop().time()

        self.state_repo.set_last_match_id(match_data["match_id"])
        role = await ensure_playing_role(guild)
        spectator_role = discord.utils.get(guild.roles, name="Espectador")
        all_players = list(set(match_data["team1"] + match_data["team2"]))
        await add_role_to_players(guild, role, all_players)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            role: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True, manage_permissions=True),
        }
        if spectator_role:
            overwrites[spectator_role] = discord.PermissionOverwrite(
                view_channel=True, connect=True, speak=False, stream=False, send_messages=False
            )

        custom_id = match_data["custom_id"]
        try:
            category = await guild.create_category(f"LOBBY: {custom_id}", overwrites=overwrites)
            text_channel = await guild.create_text_channel(f"chat-{custom_id.lower()}", category=category)
            voice_rad = await guild.create_voice_channel(f"Radiant-{custom_id.upper()}", category=category)
            voice_dire = await guild.create_voice_channel(f"Dire-{custom_id.upper()}", category=category)

            match_data["channels"] = [category.id, text_channel.id, voice_rad.id, voice_dire.id]
            match_data["start_time"] = datetime.datetime.now().timestamp()
            match_data["active_doubles"] = []

            async with lock:
                self.active_matches[text_channel.id] = match_data
                if old_key in self.active_matches:
                    del self.active_matches[old_key]

            view_dd = DoubleDownView(self, text_channel.id)
            embed_ready = self.create_match_embed(match_data)
            embed_ready.title = f"🎮 Partida {custom_id} Pronta"
            embed_ready.description = "Os canais de voz foram criados acima. Boa sorte!"

            await text_channel.send(
                content="**Bem-vindos à sala da partida!**\nUtilizem `!win` ao finalizar ou `!remake` se necessário.",
                embed=embed_ready,
                view=view_dd,
            )
        except Exception as exc:
            print(f"Erro crítico no finalize_match: {exc}")

        await self._update_watch_panel(guild)
        telemetry = self._telemetry()
        if telemetry:
            telemetry.inc("match.finalized")
            telemetry.observe("match.finalize.latency", asyncio.get_event_loop().time() - started)

    def calculate_mmr_gain(self, team_winner_avg, team_loser_avg):
        return calculate_mmr_gain(team_winner_avg, team_loser_avg)

    @commands.command()
    async def win(self, ctx):
        lock = self._get_match_lock(ctx.channel.id)
        async with lock:
            match_data = self.active_matches.get(ctx.channel.id)
            if not match_data:
                return await ctx.send("Use este comando no chat da partida.")
            if ctx.author.id not in [match_data["cap1"], match_data["cap2"]] and not ctx.author.guild_permissions.administrator:
                return await ctx.send("Apenas capitães ou ADMs.")
            if match_data.get("closing"):
                return await ctx.send("Esta partida já está sendo encerrada.")
            if match_data.get("win_vote_active"):
                return await ctx.send("Já existe uma votação de vencedor em andamento.")
            match_data["win_vote_active"] = True
            telemetry = self._telemetry()
            if telemetry:
                telemetry.inc("match.win_vote.started")

        view = WinVotingView(self, ctx.channel.id)
        await ctx.send("**Relatar Vencedor:** Ambos os capitães devem confirmar o time vencedor.", view=view)

    async def end_match(self, channel_id, winner_team_name):
        started = asyncio.get_event_loop().time()
        lock = self._get_match_lock(channel_id)
        async with lock:
            match_data = self.active_matches.get(channel_id)
            if not match_data:
                return
            if match_data.get("result_applied"):
                return
            match_data["result_applied"] = True
            match_data["closing"] = True
            match_data["win_vote_active"] = False

            mmr_data = self.state_repo.get_mmr()
            vips = self.state_repo.get_vips()
            now_ts = datetime.datetime.now().timestamp()
            details, winners, losers = apply_match_result(mmr_data, vips, match_data, winner_team_name, now_ts)
            self.state_repo.save_mmr(mmr_data)
            guild_id = match_data["guild_id"]
            channels = list(match_data.get("channels", []))
            custom_id = match_data.get("custom_id", f"#{match_data['match_id']}")
            telemetry = self._telemetry()
            if telemetry:
                telemetry.inc("match.ended", winner=winner_team_name)

        ranking_cog = self.bot.get_cog("RankingCog")
        if ranking_cog:
            await ranking_cog.perform_update()

        res_ch = self.bot.get_channel(self.state_repo.get("results_channel_id"))
        if res_ch:
            log_embed = discord.Embed(title=f"Partida {custom_id} Finalizada", color=discord.Color.green())
            log_embed.description = f"**Vencedor:** {winner_team_name}\n\n" + "\n".join(details)
            await res_ch.send(embed=log_embed)

        channel = self.bot.get_channel(channel_id)
        if channel:
            await channel.send("**Resultados:**\n" + "\n".join(details) + "\n\nCanais serão deletados em 30s.")

        await asyncio.sleep(30)
        guild = self.bot.get_guild(guild_id)
        role = discord.utils.get(guild.roles, name="Atualmente Jogando") if guild else None
        await delete_match_channels(self.bot, channels)
        if guild:
            await remove_role_from_players(guild, role, winners + losers)

        async with lock:
            self._remove_match_entry(channel_id)
        await self._update_watch_panel(guild)
        telemetry = self._telemetry()
        if telemetry:
            telemetry.observe("match.end.latency", asyncio.get_event_loop().time() - started)


async def setup(bot):
    await bot.add_cog(Match(bot))
