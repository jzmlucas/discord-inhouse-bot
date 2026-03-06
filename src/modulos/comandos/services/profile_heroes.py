import aiohttp


STEAM_ID_64_BASE = 76561197960265728
DEFAULT_HEROES_MSG = "⚠️ Sem partidas recentes (90 dias) ou perfil privado."


class OpenDotaHeroesService:
    def __init__(self, logger):
        self.logger = logger
        self.hero_mapping: dict[int, str] = {}
        self.heroes_loaded = False

    async def load_heroes(self):
        url = "https://api.opendota.com/api/heroes"
        timeout = aiohttp.ClientTimeout(total=10)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        self.logger.error("[Profile] Falha ao carregar heróis. Status: %s", resp.status)
                        return

                    data = await resp.json()
                    data.sort(key=lambda x: x["id"])
                    self.hero_mapping = {hero["id"]: hero["localized_name"] for hero in data}
                    self.heroes_loaded = True
                    self.logger.info("[Profile] %s heróis carregados com sucesso.", len(self.hero_mapping))
        except Exception as exc:
            self.logger.error("[Profile] Erro ao buscar heróis: %s", exc)

    async def get_top_heroes_text(self, steam_id) -> str:
        if not steam_id:
            return DEFAULT_HEROES_MSG

        clean_steam_id = str(steam_id).strip()
        if not clean_steam_id.isdigit():
            return DEFAULT_HEROES_MSG

        try:
            val_id = int(clean_steam_id)
            steam_id_32 = val_id - STEAM_ID_64_BASE if val_id >= STEAM_ID_64_BASE else val_id
            url = f"https://api.opendota.com/api/players/{steam_id_32}/heroes?date=90"

            timeout = aiohttp.ClientTimeout(total=7)
            headers = {"User-Agent": "LaligaBot/1.0"}
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return f"❌ Erro ao acessar dados (Status: {resp.status})"

                    heroes_data = await resp.json()
                    recent_heroes = [hero for hero in heroes_data if int(hero["games"]) > 0]
                    if not recent_heroes:
                        return "📭 Nenhuma partida nos últimos 90 dias."

                    top_3 = recent_heroes[:3]
                    lines = []
                    for hero in top_3:
                        hero_id = int(hero["hero_id"])
                        hero_name = self.hero_mapping.get(hero_id, f"Hero {hero_id}")
                        games = int(hero["games"])
                        winrate = int(hero["win"]) / games * 100 if games > 0 else 0
                        lines.append(f"• **{hero_name}**: `{games} partidas` ({winrate:.1f}% WR)")
                    return "\n".join(lines)
        except Exception as exc:
            self.logger.error("[Profile] Erro Heróis: %s", exc)
            return "❌ Falha na conexão com OpenDota."
