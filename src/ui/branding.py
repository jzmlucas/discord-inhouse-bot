from pathlib import Path

import discord

PRIMARY_COLOR = 0x3B1DE0
BANNER_FILENAME = "ligainhouse.png"
BANNER_ATTACHMENT_URL = f"attachment://{BANNER_FILENAME}"
BANNER_IMAGE_PATH = Path(__file__).resolve().parent / "images" / BANNER_FILENAME


def build_banner_file() -> discord.File:
    return discord.File(str(BANNER_IMAGE_PATH), filename=BANNER_FILENAME)
