import argparse

from src.database.storage.state import get_state_repository
from src.modulos.registro.register import resolve_registration_medal_icon


def backfill_medal_icons(force: bool = False):
    repo = get_state_repository()
    state = repo.load()
    players = state.get("players", {})

    if not isinstance(players, dict):
        print("Formato invalido: state['players'] nao e um dicionario.")
        return

    updated = 0
    skipped = 0

    for user_id, info in players.items():
        if not isinstance(info, dict):
            skipped += 1
            continue

        has_icon = bool(info.get("medal_icon"))
        if has_icon and not force:
            skipped += 1
            continue

        medal_name = info.get("medal", "Herald")
        dota_mmr_estimate = info.get("dota_mmr_estimate")
        info["medal_icon"] = resolve_registration_medal_icon(medal_name, dota_mmr_estimate)
        players[user_id] = info
        updated += 1

    if updated:
        state["players"] = players
        repo.update(**state)

    print(f"Backfill concluido. Atualizados: {updated}. Ignorados: {skipped}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Preenche players[].medal_icon no estado.")
    parser.add_argument("--force", action="store_true", help="Regrava medal_icon mesmo para quem ja tem valor.")
    args = parser.parse_args()
    backfill_medal_icons(force=args.force)
