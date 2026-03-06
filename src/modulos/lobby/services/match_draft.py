import random
import string


def generate_match_code(prefix: str = "laliga") -> str:
    chars = string.ascii_uppercase + string.digits
    random_code = "".join(random.choice(chars) for _ in range(4))
    return f"{prefix}-{random_code}"


def create_initial_match_data(players_list, mmr_data, match_id_num: int, guild_id: int):
    players_with_mmr = []
    for uid in players_list:
        mmr = mmr_data.get(str(uid), 1000)
        players_with_mmr.append((uid, mmr))
    players_with_mmr.sort(key=lambda x: x[1], reverse=True)

    if len(players_list) >= 2:
        cap1, cap2 = players_with_mmr[0][0], players_with_mmr[1][0]
        pool = [player for player in players_list if player not in [cap1, cap2]]
    else:
        cap1 = cap2 = players_list[0]
        pool = []

    sequence = [cap1, cap2, cap2, cap1, cap1, cap2, cap2, cap1]

    return {
        "match_id": match_id_num,
        "custom_id": generate_match_code(),
        "cap1": cap1,
        "cap2": cap2,
        "team1": [cap1],
        "team2": [cap2],
        "pool": pool,
        "sequence": sequence,
        "step": 0,
        "guild_id": guild_id,
        "channels": [],
    }


def choose_best_autopick(match_data, mmr_data):
    sorted_pool = sorted(
        match_data["pool"],
        key=lambda uid: mmr_data.get(str(uid), 1000),
        reverse=True,
    )
    return sorted_pool[0]


def apply_draft_pick(match_data, captain_uid: int, chosen_id: int):
    if captain_uid == match_data["cap1"]:
        match_data["team1"].append(chosen_id)
    else:
        match_data["team2"].append(chosen_id)

    match_data["pool"].remove(chosen_id)
    match_data["step"] += 1
