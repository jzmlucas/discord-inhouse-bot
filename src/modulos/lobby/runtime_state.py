from dataclasses import dataclass, field
from typing import Optional

import asyncio
import discord


@dataclass
class QueueRuntimeState:
    queue: list[int] = field(default_factory=list)
    lobby_channel_id: Optional[int] = None
    queue_start_time: Optional[float] = None
    confirmed: set[int] = field(default_factory=set)
    confirm_message: Optional[discord.Message] = None
    queue_message: Optional[discord.Message] = None
    confirm_task: Optional[asyncio.Task] = None
    remaining_time: int = 0
    current_match_players: list[int] = field(default_factory=list)
    confirmation_active: bool = False


@dataclass
class MatchRuntimeState:
    active_matches: dict = field(default_factory=dict)
    active_remakes: dict = field(default_factory=dict)
