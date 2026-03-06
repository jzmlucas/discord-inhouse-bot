import asyncio

from src.core.bot import LigaBot
from src.core.config import Config
from src.core.logger import setup_logger


async def main():
    logger = setup_logger()
    bot = LigaBot(Config, logger)

    try:
        async with bot:
            await bot.start(Config.TOKEN)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot desligado manualmente.")