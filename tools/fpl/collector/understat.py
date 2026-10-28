"""Understat EPL player + team match xG via soccerdata (it keeps its own cache under SOCCERDATA_DIR)."""
from . import store


def pull(start_year):
    import soccerdata as sd  # heavy import, only for this job
    u = sd.Understat(leagues="ENG-Premier League", seasons=start_year)
    players = u.read_player_match_stats().reset_index()
    teams = u.read_team_match_stats().reset_index()
    if players.empty and teams.empty:
        raise RuntimeError("understat returned no data")
    season = store.season_str(start_year)
    now = store.utcnow()
    store.save_table("understat_player_match", players, season, now)
    store.save_table("understat_team_match", teams, season, now)
    return f"understat: {len(players)} player rows, {len(teams)} team rows"
