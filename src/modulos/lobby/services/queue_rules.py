import datetime
from dataclasses import dataclass

import discord

from src.database.storage.state import get_state_repository

STRIKE_EXPIRY_SECONDS = 604800
DEFAULT_BAN_BY_STRIKES = {1: 900, 2: 3600, 3: 21600}
REFUSAL_BAN_SECONDS = 900


@dataclass
class QueueJoinResult:
    allowed: bool
    message: str | None = None


class QueueRulesService:
    def __init__(self):
        self.state_repo = get_state_repository()

    def evaluate_join(self, interaction: discord.Interaction, queue, confirmation_active: bool) -> QueueJoinResult:
        user = interaction.user
        uid_str = str(user.id)
        now_ts = datetime.datetime.now().timestamp()

        players_data = self.state_repo.get_players()
        bans = self.state_repo.get_bans()

        if uid_str not in players_data:
            return QueueJoinResult(
                allowed=False,
                message=(
                    "**Você não está registrado nessa liga!**\n"
                    "Use o canal de registro para realizar seu cadastro antes de jogar."
                ),
            )

        user_info = players_data[uid_str]
        needs_save = False

        last_strike = user_info.get("last_strike_at", 0)
        if user_info.get("strikes", 0) > 0 and (now_ts - last_strike) > STRIKE_EXPIRY_SECONDS:
            user_info["strikes"] = 0
            players_data[uid_str] = user_info
            needs_save = True

        if uid_str in bans:
            unban_at = bans[uid_str]
            if now_ts < unban_at:
                return QueueJoinResult(
                    allowed=False,
                    message=f"**Você está banido!** Banimento expira em: `{self._format_remaining(unban_at - now_ts)}`.",
                )

            del bans[uid_str]
            needs_save = True

        if needs_save:
            self.state_repo.save_players_and_bans(players_data, bans)

        role_playing = discord.utils.get(interaction.guild.roles, name="Atualmente Jogando")
        if role_playing in user.roles:
            return QueueJoinResult(allowed=False, message="Você já está jogando!")

        if user.id in queue:
            return QueueJoinResult(allowed=False, message="Você já está na fila.")

        if confirmation_active:
            return QueueJoinResult(allowed=False, message="Partida sendo confirmada. Aguarde.")

        return QueueJoinResult(allowed=True)

    def apply_afk_punishments(self, current_match_players, confirmed):
        players_data = self.state_repo.get_players()
        bans = self.state_repo.get_bans()
        now_ts = datetime.datetime.now().timestamp()
        afks = [uid for uid in current_match_players if uid not in confirmed]

        details = []
        for uid in afks:
            uid_str = str(uid)
            if uid_str not in players_data:
                continue

            strikes = players_data[uid_str].get("strikes", 0) + 1
            players_data[uid_str]["strikes"] = strikes
            players_data[uid_str]["last_strike_at"] = now_ts
            duration = DEFAULT_BAN_BY_STRIKES.get(strikes, 86400)
            bans[uid_str] = now_ts + duration
            details.append(f"<@{uid}>: **{strikes}º Strike** (Ban: `{self._format_ban_label(duration)}`)")

        self.state_repo.save_queue_players_and_bans([], players_data, bans)
        return details

    def apply_refusal_punishment(self, refused_user_id: int, queue):
        players_data = self.state_repo.get_players()
        bans = self.state_repo.get_bans()
        uid_str = str(refused_user_id)
        now_ts = datetime.datetime.now().timestamp()

        if uid_str in players_data:
            strikes = players_data[uid_str].get("strikes", 0) + 1
            players_data[uid_str]["strikes"] = strikes
            players_data[uid_str]["last_strike_at"] = now_ts

        bans[uid_str] = now_ts + REFUSAL_BAN_SECONDS
        if refused_user_id in queue:
            queue.remove(refused_user_id)

        self.state_repo.save_queue_players_and_bans(queue, players_data, bans)

    @staticmethod
    def _format_ban_label(duration_seconds: int) -> str:
        if duration_seconds < 3600:
            return f"{duration_seconds // 60}m"
        return f"{duration_seconds // 3600}h"

    @staticmethod
    def _format_remaining(remaining_seconds: float) -> str:
        remaining_seconds = int(remaining_seconds)
        minutes = remaining_seconds // 60
        hours = minutes // 60

        if hours > 0:
            return f"{hours}h {minutes % 60}m"
        if minutes > 0:
            return f"{minutes}m"
        return f"{remaining_seconds}s"
