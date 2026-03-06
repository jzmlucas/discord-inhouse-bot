import json
import os
from copy import deepcopy

from src.database.storage.state_repository import StateRepository


def _deep_merge(base: dict, incoming: dict) -> dict:
    result = deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            merged = dict(result[key])
            merged.update(value)
            result[key] = merged
        else:
            result[key] = value
    return result


def migrate_state_file_to_postgres(state_file: str = "stats.json", overwrite: bool = False):
    repo = StateRepository(state_file=state_file)

    if not os.path.exists(state_file):
        print(f"Arquivo nao encontrado: {state_file}")
        return

    try:
        with open(state_file, "r", encoding="utf-8") as f:
            legacy = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Falha ao ler JSON legado: {exc}")
        return

    if not isinstance(legacy, dict):
        print("Arquivo invalido: JSON raiz precisa ser um objeto.")
        return

    if overwrite:
        merged = deepcopy(repo.DEFAULT_STATE)
        merged = _deep_merge(merged, legacy)
    else:
        current = repo.load()
        merged = _deep_merge(current, legacy)

    repo.write(merged)
    print(f"Migracao concluida usando '{state_file}' -> PostgreSQL (app_state.key='global').")


if __name__ == "__main__":
    source = os.getenv("MIGRATE_SOURCE_FILE")
    if source:
        chosen = source
    elif os.path.exists("stats.json"):
        chosen = "stats.json"
    else:
        chosen = os.getenv("STATE_FILE", "state.json")

    overwrite = os.getenv("MIGRATE_OVERWRITE", "0").strip() in {"1", "true", "True", "yes", "YES"}
    migrate_state_file_to_postgres(chosen, overwrite=overwrite)
