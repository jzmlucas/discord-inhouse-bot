import math


def calculate_mmr_gain(team_winner_avg: float, team_loser_avg: float) -> int:
    k_factor = 40
    exponent = (team_loser_avg - team_winner_avg) / 400
    expected_win = 1 / (1 + math.pow(10, exponent))
    return max(15, min(round(k_factor * (1 - expected_win)), 35))


def apply_match_result(mmr_data, vips, match_data, winner_team_name: str, now_ts: float):
    active_doubles = match_data.get("active_doubles", [])
    winners = match_data["team1"] if winner_team_name == "Radiant" else match_data["team2"]
    losers = match_data["team2"] if winner_team_name == "Radiant" else match_data["team1"]

    def get_mmr(uid):
        return mmr_data.get(str(uid), 1000)

    winner_avg = sum(get_mmr(uid) for uid in winners) / len(winners)
    loser_avg = sum(get_mmr(uid) for uid in losers) / len(losers)
    base_pts = calculate_mmr_gain(winner_avg, loser_avg)

    details = []
    for uid in winners + losers:
        is_winner = uid in winners
        points = base_pts
        tags = []

        if is_winner and str(uid) in vips and now_ts < float(vips[str(uid)]):
            points = math.ceil(points * 1.10)
            tags.append("💎")

        if uid in active_doubles:
            points *= 2
            tags.append("🃏")

        tag_str = f" ({''.join(tags)})" if tags else ""
        if is_winner:
            mmr_data[str(uid)] = get_mmr(uid) + points
            details.append(f"• <@{uid}>: +{points} MMR{tag_str}")
        else:
            mmr_data[str(uid)] = max(0, get_mmr(uid) - points)
            details.append(f"• <@{uid}>: -{points} MMR{tag_str}")

    return details, winners, losers


def refund_double_down_tokens(players, active_doubles):
    for uid in active_doubles:
        uid_str = str(uid)
        if uid_str in players:
            players[uid_str]["double_down_tokens"] = players[uid_str].get("double_down_tokens", 0) + 1
