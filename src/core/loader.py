EXTENSIONS = [
    "src.modulos.comandos.config",
    "src.modulos.comandos.admin",
    "src.modulos.comandos.player",
    "src.modulos.comandos.debug",
    "src.modulos.comandos.admin_panel",
    "src.modulos.lobby.queue",
    "src.modulos.lobby.match",
    "src.modulos.lobby.watch",
    "src.modulos.loja.loja",
    "src.modulos.ranking.ranking",
    "src.modulos.registro.register",
    "src.modulos.vip.vip",
]

async def load_extensions(bot, logger):
    for ext in EXTENSIONS:
        try:
            await bot.load_extension(ext)
            logger.info(f"✅ {ext}")
        except Exception as e:
            logger.error(f"❌ {ext}: {e}")