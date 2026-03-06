import os

from src.database.storage.state_repository import StateRepository

STATE_FILE = os.getenv("STATE_FILE", "state.json")
_repository = None


def _build_repository() -> StateRepository:
    return StateRepository(STATE_FILE)


def get_state_repository() -> StateRepository:
    global _repository
    if _repository is None:
        _repository = _build_repository()
    return _repository


def load_state():
    return get_state_repository().load()


def save_state(lobby_id=None, queue=None, **kwargs):
    return get_state_repository().update(lobby_id=lobby_id, queue=queue, **kwargs)
