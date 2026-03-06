from src.modulos.lobby.services.match_results import apply_match_result


def test_vip_bonus_applies_only_on_win():
    mmr_data = {"1": 1000, "2": 1000}
    vips = {"1": 9999999999, "2": 9999999999}
    match_data = {
        "team1": [1],
        "team2": [2],
        "active_doubles": [],
    }

    details, winners, losers = apply_match_result(
        mmr_data=mmr_data,
        vips=vips,
        match_data=match_data,
        winner_team_name="Radiant",
        now_ts=1_000_000,
    )

    assert winners == [1]
    assert losers == [2]
    assert mmr_data["1"] > 1000
    assert mmr_data["2"] < 1000

    winner_gain = mmr_data["1"] - 1000
    loser_loss = 1000 - mmr_data["2"]
    assert winner_gain > loser_loss
    assert any("💎" in line for line in details if "<@1>" in line)
    assert all("💎" not in line for line in details if "<@2>" in line)
