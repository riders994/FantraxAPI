"""Synthetic, recorded-shape fixture data and a mocked ``requests.Session`` for offline tests.

This module builds a small, internally-consistent fake league (4 teams, a handful of
weekly scoring periods + a playoff round, a handful of daily scoring dates, and a
couple of players) and a dispatcher that answers ``session.post(...)`` calls the same
way the real Fantrax ``/fxpa/req`` endpoint would, keyed off the requested method name
(and view, where needed), entirely offline.

Layout:
    - ``TEAMS`` / ``POSITIONS`` / ``STATUSES`` / ``SCORING_PERIODS`` / ``SCORING_DATES``:
      the raw building blocks every fixture below cross-references.
    - ``build_*`` functions: return the ``data`` payload for a single ``responses[i]``
      entry (i.e. exactly what ``api._request`` hands back), shaped to match how
      ``fantraxapi/objs/*`` indexes into it.
    - ``FakeResponse`` / ``MockSession``: a minimal stand-in for ``requests.Response``
      / ``requests.Session`` whose ``.post`` inspects the posted ``json`` payload and
      routes to the right ``build_*`` function (or to a forced error shape).
"""

from datetime import datetime

# ---------------------------------------------------------------------------
# Core fixture building blocks
# ---------------------------------------------------------------------------

LEAGUE_ID = "abc12345"
LEAGUE_NAME = "Mocked Mariners League"
LEAGUE_YEAR = "2024-25 NHL"

# Real NHL leagues report this as their scoring period tableType.
MATCHUP_TABLE_TYPE = "H2hPointsBased3"

# Season chosen safely in the past relative to "today" so date-derived
# booleans (complete/current/future) are deterministic.
SEASON_START = datetime(2024, 10, 8)
SEASON_END = datetime(2025, 4, 20)
SEASON_START_MS = int(SEASON_START.timestamp() * 1000)
SEASON_END_MS = int(SEASON_END.timestamp() * 1000)

POSITIONS = {
    "206": {"id": "206", "name": "Center", "shortName": "C"},
    "207": {"id": "207", "name": "Wing", "shortName": "W"},
    "204": {"id": "204", "name": "Defense", "shortName": "D"},
    "208": {"id": "208", "name": "Skater", "shortName": "Skt"},
    "1": {"id": "1", "name": "Team Goalie", "shortName": "TmG"},
}

STATUSES = {
    "1": {"id": "1", "code": "ROSTER", "name": "Roster", "shortName": "Rstr", "description": "On a Roster"},
    "3": {"id": "3", "code": "INJURED_RESERVE", "name": "Inj Res", "shortName": "IR", "description": "Injured Reserve"},
    "4": {"id": "4", "code": "FREE_AGENT", "name": "Free Agent", "shortName": "FA", "description": "Free Agent"},
    # Entries without "name" should be filtered out by League.reset_info()
    "5": {"id": "5", "code": "WAIVERS"},
}

TEAMS = [
    {"id": "team1id00000aaaa", "name": "Anchorage Avalanche", "shortName": "ANC", "logoUrl512": "https://example.com/anc.png", "commissioner": True},
    {"id": "team2id00000bbbb", "name": "Bayview Bandits", "shortName": "BAY", "logoUrl256": "https://example.com/bay.png", "commissioner": False},
    {"id": "team3id00000cccc", "name": "Cedar Crushers", "shortName": "CED", "logoUrl128": "https://example.com/ced.png", "commissioner": False},
    {"id": "team4id00000dddd", "name": "Dockside Dragons", "shortName": "DOX", "logoUrl512": "https://example.com/dox.png", "commissioner": False},
]
TEAM_IDS = [t["id"] for t in TEAMS]

# Owner account names surfaced per team via getTeamRosterInfo's teamHeadingInfo.
# Unlike team name/shortName these are stable across seasons.
TEAM_OWNERS = {
    "team1id00000aaaa": "anchor_andy",
    "team2id00000bbbb": "bay_bobby",
    "team3id00000cccc": "cedar_carl",
    "team4id00000dddd": "dock_dana",
}

# Weekly scoring periods (regular season periods 1-4, playoff period 5).
# "name" format mirrors Fantrax's "[Mon Day/YY - Mon Day/YY]" used by ScoringPeriod.
SCORING_PERIODS = [
    {"name": "[Oct 14/24 - Oct 20/24]", "value": 1},
    {"name": "[Oct 21/24 - Oct 27/24]", "value": 2},
    {"name": "[Oct 28/24 - Nov 03/24]", "value": 3},
    {"name": "[Nov 04/24 - Nov 10/24]", "value": 4},
    {"name": "[Nov 11/24 - Nov 17/24]", "value": 5},
]

# Daily scoring dates. Keys are the "daily period numbers" from getLiveScoringStats'
# periodList; values are actual calendar dates that fall within the weekly periods above.
# Includes a single-digit day (Nov 9) to exercise League.reset_info's unpadded-day key
# building (Fantrax renders "Nov 9", not "Nov 09").
SCORING_DATES = {
    14: "2024-10-14",
    15: "2024-10-15",
    21: "2024-10-21",
    22: "2024-10-22",
    28: "2024-10-28",
    9: "2024-11-09",
}


def _team_data_map() -> dict[str, dict]:
    return {t["id"]: dict(t) for t in TEAMS}


def _team_info_map() -> dict[str, dict]:
    # Standings responses carry a reduced team payload: just name/shortName/logoUrl512,
    # notably without the commissioner flag -- League._update_teams must merge rather
    # than downgrade the existing Team data.
    return {t["id"]: {"name": t["name"], "shortName": t["shortName"], "logoUrl512": f"https://example.com/{t['shortName'].lower()}_512.png"} for t in TEAMS}


# ---------------------------------------------------------------------------
# response[0]: getFantasyLeagueInfo
# ---------------------------------------------------------------------------


def build_fantasy_league_info() -> dict:
    return {
        "fantasySettings": {
            "leagueName": LEAGUE_NAME,
            "subtitle": LEAGUE_YEAR,
            "season": {"startDate": SEASON_START_MS, "endDate": SEASON_END_MS},
        },
        "positionMap": POSITIONS,
    }


# ---------------------------------------------------------------------------
# response[1]: getRefObject type=FantasyItemStatus
# ---------------------------------------------------------------------------


def build_ref_object_status() -> dict:
    return {"allObjs": STATUSES}


# ---------------------------------------------------------------------------
# response[2]: getLiveScoringStats newView=True (used for `dates` during init)
# ---------------------------------------------------------------------------


def build_live_scoring_stats_init() -> dict:
    return {"dates": [{"object1": d} for d in SCORING_DATES.values()]}


# ---------------------------------------------------------------------------
# response[3]: getTeamRosterInfo view=GAMES_PER_POS (periodList -> scoring_periods,
# fantasyTeams -> league teams)
# ---------------------------------------------------------------------------


def _scoring_period_list_entries() -> list[dict]:
    entries = [dict(p) for p in SCORING_PERIODS]
    entries.append({"name": "Full Season", "value": 0})
    return entries


def build_team_roster_info_games_per_pos() -> dict:
    return {
        "displayedLists": {"scoringPeriodList": _scoring_period_list_entries()},
        "fantasyTeams": _team_data_map(),
    }


# ---------------------------------------------------------------------------
# response[4]: getTeamRosterInfo view=STATS (periodList -> day -> period number map)
# ---------------------------------------------------------------------------


def _period_to_day_list_entries() -> list[str]:
    """Build entries shaped like "<dailyPeriodNumber> (<Weekday> <Mon> <Day>)".

    League.reset_info() splits each entry on the first space (giving the period number
    and "(<Weekday> <Mon> <Day>)"), then slices [5:-1] off the remainder to recover
    "<Mon> <Day>" (e.g. "(Wed Oct 21)"[5:-1] == "Oct 21"), which it uses as the lookup
    key against each scoring date's "<Mon> <unpadded day>" (e.g. "Nov 9").
    """
    entries = []
    for period_number, iso_date in SCORING_DATES.items():
        d = datetime.strptime(iso_date, "%Y-%m-%d").date()
        # Fantrax renders the day with no leading zero ("Oct 21", "Nov 9").
        key = f"{d.strftime('%b')} {d.day}"
        weekday = d.strftime("%a")
        entries.append(f"{period_number} ({weekday} {key})")
    return entries


def build_team_roster_info_stats() -> dict:
    return {"displayedLists": {"periodList": _period_to_day_list_entries()}}


def build_init_info_responses() -> list[dict]:
    return [
        build_fantasy_league_info(),
        build_ref_object_status(),
        build_live_scoring_stats_init(),
        build_team_roster_info_games_per_pos(),
        build_team_roster_info_stats(),
    ]


# ---------------------------------------------------------------------------
# Players (re-used across rosters/trades/transactions/live scoring)
# ---------------------------------------------------------------------------


def player_data(
    scorer_id: str,
    name: str,
    short_name: str,
    team_name: str,
    team_short_name: str,
    pos_ids: list[str],
    pos_ids_no_flex: list[str] | None = None,
    icons: list[dict] | None = None,
) -> dict:
    return {
        "scorerId": scorer_id,
        "name": name,
        "shortName": short_name,
        "teamName": team_name,
        "teamShortName": team_short_name,
        "posShortNames": "/".join(POSITIONS[p]["shortName"] for p in (pos_ids_no_flex or pos_ids)),
        "posIdsNoFlex": pos_ids_no_flex or pos_ids,
        "posIds": pos_ids,
        "icons": icons or [],
    }


PLAYER_CENTER = player_data("p001", "Connor Centerman", "C. Centerman", "Toronto Maple Leafs", "TOR", ["206", "208"], pos_ids_no_flex=["206"])
PLAYER_WINGER = player_data(
    "p002",
    "Wendell Wingfield",
    "W. Wingfield",
    "Boston Bruins",
    "BOS",
    ["207", "208"],
    pos_ids_no_flex=["207"],
    icons=[{"typeId": "1"}],
)
PLAYER_DEFENSEMAN = player_data("p003", "Derek Defenton", "D. Defenton", "Calgary Flames", "CGY", ["204", "208"], pos_ids_no_flex=["204"])
PLAYER_INJURED = player_data(
    "p004",
    "Ivan Ironside",
    "I. Ironside",
    "Edmonton Oilers",
    "EDM",
    ["207", "208"],
    pos_ids_no_flex=["207"],
    icons=[{"typeId": "2"}],
)
PLAYER_OUT = player_data(
    "p005",
    "Owen Outerbridge",
    "O. Outerbridge",
    "Vancouver Canucks",
    "VAN",
    ["204", "208"],
    pos_ids_no_flex=["204"],
    icons=[{"typeId": "30"}],
)
PLAYER_SUSPENDED = player_data(
    "p006",
    "Sam Suspendo",
    "S. Suspendo",
    "Montreal Canadiens",
    "MTL",
    ["206", "208"],
    pos_ids_no_flex=["206"],
    icons=[{"typeId": "6"}],
)
PLAYER_HEALTHY = player_data("p007", "Henry Healthy", "H. Healthy", "Ottawa Senators", "OTT", ["207", "208"], pos_ids_no_flex=["207"])


# ---------------------------------------------------------------------------
# getStandings view=SCHEDULE (League.scoring_period_results, season half)
# ---------------------------------------------------------------------------


def _matchup_cells(away_id: str, away_score: str, home_id: str, home_score: str) -> dict:
    return {"cells": [{"teamId": away_id, "content": TEAM_IDS_TO_NAMES[away_id]}, {"content": away_score}, {"teamId": home_id, "content": TEAM_IDS_TO_NAMES[home_id]}, {"content": home_score}]}


TEAM_IDS_TO_NAMES = {t["id"]: t["name"] for t in TEAMS}

# subCaption date ranges chosen to align 1:1 with SCORING_PERIODS (and to be safely
# in the past relative to "today" so `complete` is deterministically True).
_PERIOD_SUBCAPTIONS = {
    1: "(Mon Oct 14, 2024 - Sun Oct 20, 2024)",
    2: "(Mon Oct 21, 2024 - Sun Oct 27, 2024)",
    3: "(Mon Oct 28, 2024 - Sun Nov 03, 2024)",
    4: "(Mon Nov 04, 2024 - Sun Nov 10, 2024)",
}


def _season_table_entry(period_number: int, matchups: list[tuple[str, str, str, str]], table_type: str = MATCHUP_TABLE_TYPE) -> dict:
    return {
        "caption": f"Period {period_number}",
        "subCaption": _PERIOD_SUBCAPTIONS[period_number],
        "tableType": table_type,
        "rows": [_matchup_cells(*m) for m in matchups],
    }


def build_standings_schedule() -> dict:
    t1, t2, t3, t4 = TEAM_IDS
    return {
        "tableList": [
            _season_table_entry(1, [(t1, "100.0", t2, "90.0"), (t3, "80.0", t4, "85.0")]),
            _season_table_entry(2, [(t1, "110.5", t3, "95.5"), (t2, "70.0", t4, "70.0")]),
            _season_table_entry(3, [(t1, "120.0", t4, "60.0"), (t2, "88.8", t3, "77.7")]),
            _season_table_entry(4, [(t1, "75.0", t2, "150.0"), (t3, "99.9", t4, "33.3")]),
        ],
        "displayedLists": {
            "tabs": [
                {"id": "main", "name": "Main"},
                {"id": "PLAYOFFS", "name": "Playoffs"},
                {"id": ".consolation", "name": "Consolation"},
            ]
        },
    }


# ---------------------------------------------------------------------------
# getStandings view=PLAYOFFS / view=.consolation (playoff brackets, with other_brackets)
# ---------------------------------------------------------------------------


def build_standings_playoffs() -> dict:
    t1, t2, t3, t4 = TEAM_IDS
    return {
        "displayedSelections": {"view": "PLAYOFFS"},
        "displayedLists": {"tabs": _standings_tabs()},
        "tableList": [
            _playoff_standings_table(),
            {
                "caption": "Playoffs - Round 5",
                "subCaption": "(Mon Nov 11, 2024 - Sun Nov 17, 2024)",
                "tableType": MATCHUP_TABLE_TYPE,
                "rows": [_matchup_cells(t1, "200.5", t2, "175.25")],
            },
        ],
    }


def build_standings_consolation() -> dict:
    t3, t4 = TEAM_IDS[2], TEAM_IDS[3]
    return {
        "displayedSelections": {"view": ".consolation"},
        "displayedLists": {"tabs": [{"id": "PLAYOFFS", "name": "Playoffs"}, {"id": ".consolation", "name": "Consolation"}]},
        "tableList": [
            {"caption": "Standings", "subCaption": "(ignored)", "rows": []},
            {
                "caption": "Consolation - Round 5",
                "subCaption": "(Mon Nov 11, 2024 - Sun Nov 17, 2024)",
                "tableType": MATCHUP_TABLE_TYPE,
                "rows": [_matchup_cells(t3, "150.0", t4, "140.0")],
            },
        ],
    }


# ---------------------------------------------------------------------------
# getStandings view=SCHEDULE/PLAYOFFS/.consolation, H2hRotisserie2-shaped
# variant (rows are per-team category lines paired by matchupId, not
# pre-scored away/home pairs). Routed in only when MockSession(rotisserie=True)
# so the existing H2hPointsBased3 fixtures/tests above are untouched.
# ---------------------------------------------------------------------------

# Real rotisserie leagues report this as their scoring period tableType.
MATCHUP_TABLE_TYPE_ROTISSERIE = "H2hRotisserie2"

# A tableType FantraxAPI doesn't special-case in ScoringPeriodResult.matchup_types,
# used to exercise _matchup_factory's generic-Matchup fallback branch.
MATCHUP_TABLE_TYPE_UNKNOWN = "H2hSomeFutureType"

# shortName/name pairs mirror the "header.cells" shape H2HRotisserie2 reads
# (only the shortName ends up mattering -- see _header_translator/_scoreboard_builder).
ROTISSERIE_HEADER_CELLS = [
    {"shortName": "G", "name": "Goals"},
    {"shortName": "A", "name": "Assists"},
    {"shortName": "PIM", "name": "Penalty Minutes"},
    {"shortName": "Pts", "name": "Points"},
]

# Fantrax sends a teamId like this for an empty bracket slot -- not a real
# league member, so League.team() raises NotTeamInLeague and H2HRotisserie2
# falls back to a placeholder "Bye" Team.
BYE_TEAM_ID = "bye-placeholder-0000"


def _roto_cell(content: str, tool_tip: str | None = None, gain_color: int | None = None) -> dict:
    cell = {"content": content}
    if tool_tip is not None:
        cell["toolTip"] = tool_tip
    # Fantrax sets gainColor == 1 on the team that won a category (-1 on the loser).
    if gain_color is not None:
        cell["gainColor"] = gain_color
    return cell


def _roto_row(matchup_id: str, team_id: str, cells: list[dict], team_name: str | None = None) -> dict:
    name = team_name if team_name is not None else TEAM_IDS_TO_NAMES.get(team_id, team_id)
    return {"matchupId": matchup_id, "fixedCells": [{"teamId": team_id, "content": name}], "cells": cells}


def _roto_table_entry(caption: str, sub_caption: str, rows: list[dict]) -> dict:
    return {
        "caption": caption,
        "subCaption": sub_caption,
        "tableType": MATCHUP_TABLE_TYPE_ROTISSERIE,
        "header": {"cells": [dict(c) for c in ROTISSERIE_HEADER_CELLS]},
        "rows": rows,
    }


def build_standings_schedule_rotisserie() -> dict:
    t1, t2, t3, t4 = TEAM_IDS

    # Period 1: two H2hRotisserie2 matchups paired by matchupId. The first row
    # seen for a matchupId becomes the away side, the second becomes the home
    # side (see ScoringPeriodResult._h2h_rot_2_factory). Cell values are picked
    # to exercise the plain-content path, the toolTip-takes-precedence path,
    # the ValueError -> 0.0 fallback for non-numeric content, and the special
    # "Pts" category that drives home_score/away_score.
    # Header order is [G, A, PIM, Pts]. The first row of a matchupId is the away side,
    # the second is the home side (see _h2h_rot_2_factory). gainColor == 1 marks the
    # category winner: away wins G + PIM, home wins A; Pts is a summary column (no winner).
    rotisserie_rows = [
        _roto_row("9001", t1, [_roto_cell("30", gain_color=1), _roto_cell("25", gain_color=-1), _roto_cell("40", tool_tip="40.2", gain_color=1), _roto_cell("2.5")]),
        _roto_row("9001", t2, [_roto_cell("N/A", gain_color=-1), _roto_cell("28", gain_color=1), _roto_cell("33", tool_tip="33.1", gain_color=-1), _roto_cell("1.5")]),
        # Second matchup carries no gainColor -> category_winners fall back to None.
        _roto_row("9002", t3, [_roto_cell("18"), _roto_cell("20"), _roto_cell("12"), _roto_cell("3.0")]),
        _roto_row("9002", t4, [_roto_cell("15"), _roto_cell("16"), _roto_cell("22"), _roto_cell("1.0")]),
    ]

    return {
        "tableList": [
            _roto_table_entry("Period 1", _PERIOD_SUBCAPTIONS[1], rotisserie_rows),
            # A second period reported under a tableType FantraxAPI doesn't
            # recognize, shaped like the plain pre-scored rows -- exercises
            # _matchup_factory's fallback to the generic Matchup class.
            _season_table_entry(2, [(t1, "110.5", t3, "95.5"), (t2, "70.0", t4, "70.0")], table_type=MATCHUP_TABLE_TYPE_UNKNOWN),
        ],
        "displayedLists": {
            "tabs": [
                {"id": "main", "name": "Main"},
                {"id": "PLAYOFFS", "name": "Playoffs"},
                {"id": ".consolation", "name": "Consolation"},
            ]
        },
    }


def build_standings_playoffs_rotisserie() -> dict:
    t1, t2 = TEAM_IDS[0], TEAM_IDS[1]
    rows = [
        _roto_row("9101", t1, [_roto_cell("32"), _roto_cell("27"), _roto_cell("38"), _roto_cell("3.0")]),
        _roto_row("9101", t2, [_roto_cell("29"), _roto_cell("24"), _roto_cell("44"), _roto_cell("1.0")]),
    ]
    return {
        "displayedSelections": {"view": "PLAYOFFS"},
        "displayedLists": {"tabs": _standings_tabs()},
        "tableList": [
            _playoff_standings_table(),
            # Real NBA leagues caption playoff tables "Scoring Period: Playoffs <round>"
            # rather than "Playoffs - Round <round>" (see build_standings_playoffs).
            # Round 1 deliberately collides with season Period 1: the round number must
            # never be mistaken for a season week number.
            _roto_table_entry("Scoring Period: Playoffs 1", "(Mon Nov 11, 2024 - Sun Nov 17, 2024)", rows),
        ],
    }


def build_standings_consolation_rotisserie() -> dict:
    t3 = TEAM_IDS[2]
    # Odd team count in this bracket -> Cedar Crushers draws a "Bye".
    rows = [
        _roto_row("9201", t3, [_roto_cell("20"), _roto_cell("19"), _roto_cell("16"), _roto_cell("2.0")]),
        _roto_row("9201", BYE_TEAM_ID, [_roto_cell("0"), _roto_cell("0"), _roto_cell("0"), _roto_cell("0.0")], team_name="Bye"),
    ]
    return {
        "displayedSelections": {"view": ".consolation"},
        "displayedLists": {"tabs": [{"id": "PLAYOFFS", "name": "Playoffs"}, {"id": ".consolation", "name": "Consolation"}]},
        "tableList": [
            {"caption": "Standings", "subCaption": "(ignored)", "rows": []},
            _roto_table_entry("Scoring Period: Playoffs 1", "(Mon Nov 11, 2024 - Sun Nov 17, 2024)", rows),
        ],
    }


# ---------------------------------------------------------------------------
# getStandings (default / by period / only_period) -> League.standings()
# ---------------------------------------------------------------------------


def _standings_header(alias_keys: bool = False) -> dict:
    # Column keys vary by league: some leagues report gamesback/pointsFor/pointsAgainst
    # (with points and wwOrder columns), others gb/cpf/cpa (without them).
    if alias_keys:
        stat_keys = ["win", "loss", "tie", "winpc", "gb", "cpf", "cpa", "streak"]
    else:
        stat_keys = ["win", "loss", "tie", "points", "winpc", "gamesback", "pointsFor", "pointsAgainst", "streak"]
    return {"cells": [{"key": "rank"}, {"key": "team"}] + [{"key": k} for k in stat_keys]}


def _standings_row(rank: int, team_id: str, win: int, loss: int, tie: int, points: int, winpc: str, gb: str, pf: str, pa: str, streak: str, alias_keys: bool = False) -> dict:
    stats = [str(win), str(loss), str(tie)]
    stats += [winpc, gb, pf, pa, streak] if alias_keys else [str(points), winpc, gb, pf, pa, streak]
    return {
        "fixedCells": [{"content": str(rank)}, {"teamId": team_id, "content": TEAM_IDS_TO_NAMES[team_id]}],
        "cells": [{"content": str(rank)}, {"content": TEAM_IDS_TO_NAMES[team_id]}] + [{"content": s} for s in stats],
    }


def _standings_table(rows: list[dict], alias_keys: bool = False) -> dict:
    return {"header": _standings_header(alias_keys=alias_keys), "rows": rows}


def _standings_tabs() -> list[dict]:
    return [
        {"id": "REGULAR_SEASON", "name": "Regular Season"},
        {"id": "PLAYOFFS", "name": "Playoffs"},
        {"id": ".consolation", "name": "Consolation"},
    ]


def _playoff_standings_table() -> dict:
    # The playoff view's standings table uses a reduced header (no season columns).
    # ScoringPeriodResult parsing skips it by its "Standings" caption;
    # League.playoff_standings() parses it.
    t1, t2 = TEAM_IDS[0], TEAM_IDS[1]
    return {
        "caption": "Standings",
        "header": {"cells": [{"key": "rank"}, {"key": "team"}, {"key": "win"}, {"key": "loss"}, {"key": "tie"}, {"key": "cp"}]},
        "rows": [
            {
                "fixedCells": [{"content": "1"}, {"teamId": t1, "content": TEAM_IDS_TO_NAMES[t1]}],
                "cells": [{"content": "1"}, {"content": TEAM_IDS_TO_NAMES[t1]}, {"content": "1"}, {"content": "0"}, {"content": "0"}, {"content": "2"}],
            },
            {
                "fixedCells": [{"content": "2"}, {"teamId": t2, "content": TEAM_IDS_TO_NAMES[t2]}],
                "cells": [{"content": "2"}, {"content": TEAM_IDS_TO_NAMES[t2]}, {"content": "0"}, {"content": "1"}, {"content": "0"}, {"content": "0"}],
            },
        ],
    }


def build_standings_default() -> dict:
    # Once playoffs exist, a viewless getStandings answers with the PLAYOFFS view --
    # League.standings() must spot this and re-request the season view.
    return build_standings_playoffs()


def build_standings_regular_season() -> dict:
    t1, t2, t3, t4 = TEAM_IDS
    return {
        "displayedSelections": {"view": "REGULAR_SEASON"},
        "displayedLists": {"tabs": _standings_tabs()},
        "fantasyTeamInfo": _team_info_map(),
        "tableList": [
            _standings_table(
                [
                    # gb "-" mirrors how Fantrax marks the leader; "3.5" covers fractional games back
                    _standings_row(1, t1, 4, 0, 0, 8, "1.000", "-", "405.5", "300.0", "W4", alias_keys=True),
                    _standings_row(2, t2, 2, 2, 0, 4, "0.500", "2", "350.0", "350.0", "L1", alias_keys=True),
                    _standings_row(3, t3, 1, 3, 0, 2, "0.250", "3.5", "330.0", "365.0", "L2", alias_keys=True),
                    _standings_row(4, t4, 1, 3, 0, 2, "0.250", "3.5", "248.3", "318.3", "W1", alias_keys=True),
                ],
                alias_keys=True,
            )
        ],
    }


def build_standings_by_period(period_number: int) -> dict:
    t1, t2, t3, t4 = TEAM_IDS
    base = {
        2: [
            _standings_row(1, t1, 2, 0, 0, 4, "1.000", "0", "210.5", "185.5", "W2"),
            _standings_row(2, t3, 1, 1, 0, 2, "0.500", "1", "173.2", "165.0", "L1"),
            _standings_row(3, t2, 1, 1, 0, 2, "0.500", "1", "160.0", "180.5", "W1"),
            _standings_row(4, t4, 0, 2, 0, 0, "0.000", "2", "145.5", "201.0", "L2"),
        ],
        3: [
            _standings_row(1, t1, 3, 0, 0, 6, "1.000", "0", "295.0", "230.0", "W3"),
            _standings_row(2, t3, 1, 2, 0, 2, "0.333", "2", "250.5", "260.0", "L1"),
            _standings_row(3, t2, 1, 2, 0, 2, "0.333", "2", "228.8", "240.0", "L2"),
            _standings_row(4, t4, 1, 2, 0, 2, "0.333", "2", "175.0", "215.0", "W1"),
        ],
    }
    return {"fantasyTeamInfo": _team_info_map(), "tableList": [_standings_table(base[period_number])]}


def build_standings_only_period(period_number: int) -> dict:
    t1, t2, t3, t4 = TEAM_IDS
    rows = {
        2: [
            _standings_row(1, t1, 1, 0, 0, 2, "1.000", "0", "110.5", "95.5", "W1"),
            _standings_row(2, t2, 1, 0, 0, 2, "1.000", "0", "70.0", "70.0", "W1"),
            _standings_row(3, t3, 0, 1, 0, 0, "0.000", "1", "95.5", "110.5", "L1"),
            _standings_row(4, t4, 0, 1, 0, 0, "0.000", "1", "70.0", "70.0", "L1"),
        ]
    }
    return {"fantasyTeamInfo": _team_info_map(), "tableList": [_standings_table(rows[period_number])]}


# ---------------------------------------------------------------------------
# getPendingTransactions / getTradeBlocks
# ---------------------------------------------------------------------------


def trade_data(trade_id: str, creator_team_id: str, proposed: str, accepted: str, executed: str, moves: list[dict]) -> dict:
    return {
        "txSetId": trade_id,
        "creatorTeamId": creator_team_id,
        "usefulInfo": [
            {"name": "Proposed", "value": proposed},
            {"name": "Accepted", "value": accepted},
            {"name": "To be executed", "value": executed},
        ],
        "moves": moves,
    }


def draft_pick_move(from_team_id: str, to_team_id: str, year: int, round_number: int, owner_team_id: str) -> dict:
    return {
        "draftPick": {"year": year, "round": round_number, "origOwnerTeam": {"id": owner_team_id}},
        "from": {"teamId": from_team_id},
        "to": {"teamId": to_team_id},
    }


def player_move(from_team_id: str, to_team_id: str, scorer: dict, score_per_game: float, score: float) -> dict:
    return {"scorer": scorer, "scorePerGame": score_per_game, "score": score, "from": {"teamId": from_team_id}, "to": {"teamId": to_team_id}}


def build_pending_transactions() -> dict:
    t1, t2 = TEAM_IDS[0], TEAM_IDS[1]
    return {
        "tradeInfoList": [
            trade_data(
                "tradeset001",
                t1,
                "Nov 2, 3:00 AM EDT",
                "Nov 2, 3:00 AM EDT",
                "Nov 2, 3:00 AM EDT",
                [
                    draft_pick_move(t1, t2, 2025, 2, t1),
                    player_move(t2, t1, PLAYER_CENTER, 5.5, 100.5),
                ],
            )
        ]
    }


def build_trade_blocks() -> list[dict]:
    t1, t2, t3 = TEAM_IDS[0], TEAM_IDS[1], TEAM_IDS[2]
    return [
        # Entries with len(block) <= 2 are filtered out by League.trade_block()
        {"teamId": "ignored1", "x": 1},
        {"teamId": "ignored2", "y": 2},
        {
            "teamId": t1,
            "lastUpdated": {"date": int(datetime(2024, 11, 1, 12, 0).timestamp() * 1000)},
            "comment": {"body": "Looking to add scoring depth, will listen on anyone"},
            "scorersOffered": {"scorers": {"206": [PLAYER_CENTER], "207": [PLAYER_WINGER, PLAYER_HEALTHY]}},
            "scorersWanted": {"scorers": {"204": [PLAYER_DEFENSEMAN]}},
            "positionsOffered": {"positions": ["206", "207"]},
            "positionsWanted": {"positions": ["204"]},
            "statsOffered": {"stats": [{"shortName": "G"}, {"shortName": "A"}]},
            "statsWanted": {"stats": [{"shortName": "PIM"}]},
        },
        {
            "teamId": t2,
            "lastUpdated": {"date": int(datetime(2024, 11, 2, 9, 30).timestamp() * 1000)},
            "comment": {"body": "Rebuilding, send picks"},
            "positionsOffered": {"positions": ["204"]},
            "positionsWanted": {"positions": ["206", "207"]},
        },
        {
            "teamId": t3,
            "lastUpdated": {"date": int(datetime(2024, 11, 3, 18, 15).timestamp() * 1000)},
            # No "comment" key -> note should default to ""
            "scorersOffered": {"scorers": {"208": [PLAYER_HEALTHY]}},
        },
    ]


# ---------------------------------------------------------------------------
# getTeamRosterInfo teamId=... view=GAMES_PER_POS -> League.position_counts()
# ---------------------------------------------------------------------------


def build_position_counts(scoring_period_number: int | None, team_id: str | None = None) -> dict:
    if scoring_period_number == 2:
        table = [
            {"pos": "Center", "posShort": "C", "min": "-", "max": 3, "gp": "5"},
            {"pos": "Wing", "posShort": "W", "min": 1, "max": "-", "gp": "9"},
            {"pos": "Defense", "posShort": "D", "min": "-", "max": "-", "gp": "7"},
            {"pos": "Team Goalie", "posShort": "TmG", "min": 1, "max": 2, "gp": "2"},
        ]
    else:
        table = [
            {"pos": "Center", "posShort": "C", "min": "-", "max": 3, "gp": "17"},
            {"pos": "Wing", "posShort": "W", "min": 1, "max": "-", "gp": "21"},
            {"pos": "Defense", "posShort": "D", "min": "-", "max": "-", "gp": "19"},
            {"pos": "Team Goalie", "posShort": "TmG", "min": 1, "max": 7, "gp": "8"},
        ]
    return {
        "gamePlayedPerPosData": {"tableData": table},
        "fantasyTeams": _team_data_map(),
        "teamHeadingInfo": {"owners": {"owners": "Owner(s)", "shortName": "Own", "value": TEAM_OWNERS.get(team_id, "")}},
    }


# ---------------------------------------------------------------------------
# getTransactionDetailsHistory -> League.transactions()
# ---------------------------------------------------------------------------


def _transaction_row(
    tx_set_id: str,
    team_id: str,
    when: str,
    transaction_code: str,
    scorer: dict,
    claim_type: str | None = None,
    period: int = 1,
    executed: bool = True,
    result: str = "Executed",
) -> dict:
    # The third cell is the scoring period the transaction processed in (Fantrax labels
    # the column "Period"); result/executed report whether the move actually went through.
    row = {
        "txSetId": tx_set_id,
        "transactionCode": transaction_code,
        "transactionType": transaction_code.title(),
        "executed": executed,
        "result": {"content": result},
        "scorer": scorer,
        "cells": [{"teamId": team_id, "content": TEAM_IDS_TO_NAMES[team_id]}, {"content": when}, {"content": str(period)}],
    }
    if claim_type is not None:
        row["claimType"] = claim_type
    return row


def _all_transaction_rows() -> list[dict]:
    t1, t2 = TEAM_IDS[0], TEAM_IDS[1]
    return [
        _transaction_row("txset_a", t1, "Mon Oct 14, 2024, 09:30AM", "CLAIM", PLAYER_HEALTHY, claim_type="WW", period=1),
        _transaction_row("txset_a", t1, "Mon Oct 14, 2024, 09:30AM", "DROP", PLAYER_OUT, period=1),
        # A waiver claim that did not go through -> executed False / result "Cancelled".
        _transaction_row("txset_b", t2, "Tue Oct 15, 2024, 11:00AM", "CLAIM", PLAYER_SUSPENDED, claim_type="WW", period=2, executed=False, result="Cancelled"),
        _transaction_row("txset_c", t1, "Wed Oct 16, 2024, 08:15AM", "CLAIM", PLAYER_CENTER, claim_type="FA", period=2),
        _transaction_row("txset_c", t1, "Wed Oct 16, 2024, 08:15AM", "DROP", PLAYER_INJURED, period=2),
    ]


def build_transaction_history(max_results_per_page: int = 100, page_number: int = 1) -> dict:
    """Page the full row set the way Fantrax's getTransactionDetailsHistory does.

    Honours ``maxResultsPerPage``/``pageNumber`` and reports ``paginatedResultSet``
    metadata, so the pagination loop in League.transactions() is exercised (and a txSet
    split across a page boundary is exercised when the page size is small).
    """
    rows = _all_transaction_rows()
    total = len(rows)
    total_pages = max(1, -(-total // max_results_per_page))  # ceil division
    start = (page_number - 1) * max_results_per_page
    return {
        "table": {"rows": rows[start : start + max_results_per_page]},
        "paginatedResultSet": {
            "totalNumPages": total_pages,
            "pageNumber": page_number,
            "maxResultsPerPage": max_results_per_page,
            "totalNumResults": total,
        },
    }


# ---------------------------------------------------------------------------
# getLiveScoringStats date=... -> League.live_scores()
# ---------------------------------------------------------------------------


# Per-category scoring definitions, keyed by category group id, mirroring the real
# getLiveScoringStats "scoringCategoriesPerGroup". The "id" (scipId) ties each category
# to the per-category entries in a scorer's statsMap "object2".
LIVE_SCORING_CATEGORIES = {
    "2010": [
        {"id": "2010#2130#-1", "name": "Goals", "shortName": "G"},
        {"id": "2010#2090#-1", "name": "Assists", "shortName": "A"},
        {"id": "2010#2170#-1", "name": "Penalty Minutes", "shortName": "PIM"},
    ]
}


def build_live_scoring_stats(scoring_date_iso: str) -> dict:
    t1, t2 = TEAM_IDS[0], TEAM_IDS[1]
    matchup_key = f"{t1}_{t2}"
    return {
        "matchups": [matchup_key],
        "scoringCategoriesPerGroup": LIVE_SCORING_CATEGORIES,
        "scorerMap": {
            "g1": {
                "g2": {
                    "g3": [
                        {"scorer": PLAYER_CENTER},
                        {"scorer": PLAYER_WINGER},
                    ]
                }
            }
        },
        "statsPerTeam": {
            "allTeamsStats": {
                # p001 carries a per-category breakdown (object2) that sums to object1
                # (12.0 + 4.0 - 3.5 = 12.5); PIM contributes negative fantasy points.
                t1: {
                    "ACTIVE": {
                        "statsMap": {
                            "p001": {
                                "object1": 12.5,
                                "object2": [
                                    {"scipId": "2010#2130#-1", "sv": "2", "av": 2.0, "fpts": 12.0},
                                    {"scipId": "2010#2090#-1", "sv": "1", "av": 1.0, "fpts": 4.0},
                                    {"scipId": "2010#2170#-1", "sv": "7", "av": 7.0, "fpts": -3.5},
                                ],
                            },
                            "_meta": {"object1": 0},
                        }
                    }
                },
                # p002 has no object2 -> categories stay empty (older/summary responses).
                t2: {"ACTIVE": {"statsMap": {"p002": {"object1": 7.0}}}},
                # team3/4 not part of an active matchup on this date -> excluded
                TEAM_IDS[2]: {"ACTIVE": {"statsMap": {"p003": {"object1": 99.9}}}},
            }
        },
    }


# ---------------------------------------------------------------------------
# getTeamRosterInfo teamId=... view=STATS / view=SCHEDULE_FULL -> League.team_roster()
# ---------------------------------------------------------------------------


# `game_today` is read off the *stats* table (a column whose header has a truthy
# "eventStr" and a non-empty cell), while `future_games` are read off the *schedule*
# table (columns keyed by header "shortName" with truthy "eventStr").
ROSTER_PERIOD_DATE = "2024-10-22"  # period 22 -> Tue, so game_today's "today" = Tue 10/22
_FUTURE_GAME_LABEL = "Thu 10/24"


def _stats_header_cells() -> list[dict]:
    return [
        {"shortName": "Pos"},
        {"shortName": "Player"},
        {"shortName": "FPts", "sortKey": "SCORE"},
        {"shortName": "FP/G", "sortKey": "FPTS_PER_GAME"},
        {"shortName": "Today", "eventStr": True},
    ]


def _schedule_header_cells() -> list[dict]:
    return [
        {"shortName": "Pos"},
        {"shortName": "Player"},
        {"shortName": _FUTURE_GAME_LABEL, "eventStr": True},
    ]


def _roster_stats_row(pos_id: str, scorer: dict | None, status_id: str, fpts: str | None = None, fp_per_game: str | None = None, today_content: str = "") -> dict:
    row = {"posId": pos_id, "statusId": status_id}
    if scorer is not None:
        row["scorer"] = scorer
        row["cells"] = [
            {"content": POSITIONS[pos_id]["shortName"]},
            {"content": scorer["name"]},
            {"content": fpts if fpts is not None else "0.0"},
            {"content": fp_per_game if fp_per_game is not None else "0.0"},
            {"content": today_content, "eventId": f"today_{scorer['scorerId']}"} if today_content else {"content": ""},
        ]
    return row


def _roster_schedule_row(pos_id: str, scorer: dict | None, future_content: str = "") -> dict:
    row = {"posId": pos_id}
    if scorer is not None:
        row["cells"] = [
            {"content": POSITIONS[pos_id]["shortName"]},
            {"content": scorer["name"]},
            {"content": future_content, "eventId": f"future_{scorer['scorerId']}"} if future_content else {"content": ""},
        ]
    return row


def build_team_roster_stats() -> dict:
    return {
        "displayedSelections": {"displayedPeriod": "22"},
        "miscData": {
            "statusTotals": [
                {"name": "Active", "total": "11", "max": "12"},
                {"name": "Reserve", "total": "7", "max": "18"},
                {"name": "Inj Res", "total": "1", "max": "3"},
            ]
        },
        "tables": [
            {
                "header": {"cells": _stats_header_cells()},
                "rows": [
                    _roster_stats_row("206", PLAYER_CENTER, "1", fpts="21.8", fp_per_game="3.1"),
                    _roster_stats_row("207", PLAYER_WINGER, "1", fpts="14.7", fp_per_game="2.4", today_content="CAR<br/>Tue 7:00PM"),
                    _roster_stats_row("204", PLAYER_DEFENSEMAN, "1", fpts="10.0", fp_per_game="1.7"),
                    _roster_stats_row("204", None, "0"),
                ],
            }
        ],
        "fantasyTeams": _team_data_map(),
    }


def build_team_roster_schedule_full() -> dict:
    return {
        "tables": [
            {
                "header": {"cells": _schedule_header_cells()},
                "rows": [
                    _roster_schedule_row("206", PLAYER_CENTER, future_content="@TOR<br/>Thu 7:00PM"),
                    _roster_schedule_row("207", PLAYER_WINGER, future_content=""),
                    # Doubleheader: opponent + weekday in the first part, then both start times.
                    _roster_schedule_row("204", PLAYER_DEFENSEMAN, future_content="@BOS Thu<br/>1:35PM<br/>7:10PM"),
                    _roster_schedule_row("204", None),
                ],
            }
        ]
    }


# ---------------------------------------------------------------------------
# Mocked transport
# ---------------------------------------------------------------------------


class FakeResponse:
    """Minimal stand-in for ``requests.Response`` good enough for ``api._request``."""

    def __init__(self, json_data: dict | None, status_code: int = 200, reason: str = "OK", json_error: bool = False) -> None:
        self._json_data = json_data
        self.status_code = status_code
        self.reason = reason
        self._json_error = json_error

    def json(self) -> dict:
        if self._json_error:
            from json import loads

            # Raises a real json.decoder.JSONDecodeError
            return loads("not-json")
        return self._json_data


class MockSession:
    """Drop-in (partial) replacement for ``requests.Session`` that answers
    ``POST https://www.fantrax.com/fxpa/req`` calls entirely offline by inspecting
    the posted ``msgs`` and routing to the appropriate fixture builder.

    Pass ``force_error`` to make every call return a particular error/garbage shape
    instead of dispatching normally - used to test the exception paths in ``_request``.

    Pass ``rotisserie=True`` to answer ``getStandings`` calls with H2hRotisserie2-shaped
    schedule/playoff/consolation data instead of the default H2hPointsBased3-shaped data,
    so the rotisserie matchup-parsing path can be exercised offline too.

    Pass ``no_playoffs=True`` to mimic a league without playoffs: every standings view,
    including an explicit ``PLAYOFFS`` request, answers with the regular season view.
    """

    def __init__(self, force_error: str | None = None, rotisserie: bool = False, no_playoffs: bool = False, tx_page_cap: int | None = None) -> None:
        self.force_error = force_error
        self.rotisserie = rotisserie
        self.no_playoffs = no_playoffs
        self.tx_page_cap = tx_page_cap
        self.post_calls: list[dict] = []

    def post(self, url: str, params: dict | None = None, json: dict | None = None, **kwargs: object) -> FakeResponse:
        self.post_calls.append({"url": url, "params": params, "json": json})

        if self.force_error == "bad_json":
            return FakeResponse(None, json_error=True)
        if self.force_error == "http_error":
            return FakeResponse({"error": "boom"}, status_code=500, reason="Internal Server Error")
        if self.force_error == "not_logged_in":
            return FakeResponse({"pageError": {"code": "WARNING_NOT_LOGGED_IN", "title": "Not Logged In"}})
        if self.force_error == "not_member":
            return FakeResponse({"pageError": {"code": "NOT_MEMBER_OF_LEAGUE", "title": "Not a Member"}})
        if self.force_error == "unexpected_error":
            return FakeResponse({"pageError": {"code": "UNEXPECTED_ERROR", "title": "Something Broke"}})
        if self.force_error == "unknown_error":
            return FakeResponse({"pageError": {"code": "SOME_OTHER_CODE", "title": "Mystery"}})

        msgs = (json or {}).get("msgs", [])
        responses = [{"data": self._dispatch(m)} for m in msgs]
        return FakeResponse({"responses": responses})

    def _dispatch(self, msg: dict) -> dict | list:
        method = msg["method"]
        data = msg.get("data", {})
        view = data.get("view")

        if method == "getFantasyLeagueInfo":
            return build_fantasy_league_info()
        if method == "getRefObject":
            return build_ref_object_status()
        if method == "getLiveScoringStats":
            if "date" in data:
                return build_live_scoring_stats(data["date"])
            return build_live_scoring_stats_init()
        if method == "getTeamRosterInfo":
            if view == "GAMES_PER_POS":
                if "teamId" in data:
                    period = int(data["scoringPeriod"]) if "scoringPeriod" in data else None
                    return build_position_counts(period, team_id=data["teamId"])
                return build_team_roster_info_games_per_pos()
            if view == "STATS":
                if "teamId" in data:
                    return build_team_roster_stats()
                return build_team_roster_info_stats()
            if view == "SCHEDULE_FULL":
                return build_team_roster_schedule_full()
            raise AssertionError(f"Unhandled getTeamRosterInfo view: {view}")
        if method == "getPendingTransactions":
            return build_pending_transactions()
        if method == "getStandings":
            return self._dispatch_standings(data)
        if method == "getTradeBlocks":
            return {"tradeBlocks": build_trade_blocks()}
        if method == "getTransactionDetailsHistory":
            per_page = int(data.get("maxResultsPerPage", 100))
            # Simulate a server that caps the page size below what the client asked for,
            # so League.transactions() must page through and stitch txSets across pages.
            if self.tx_page_cap is not None:
                per_page = min(per_page, self.tx_page_cap)
            return build_transaction_history(per_page, int(data.get("pageNumber", 1)))
        raise AssertionError(f"Unhandled method in mock dispatcher: {method} ({data})")

    def _dispatch_standings(self, data: dict) -> dict:
        view = data.get("view")
        if view == "SCHEDULE":
            return build_standings_schedule_rotisserie() if self.rotisserie else build_standings_schedule()
        if view == "PLAYOFFS" and not self.no_playoffs:
            return build_standings_playoffs_rotisserie() if self.rotisserie else build_standings_playoffs()
        if view == ".consolation":
            return build_standings_consolation_rotisserie() if self.rotisserie else build_standings_consolation()
        if view in ("REGULAR_SEASON", "COMBINED"):
            return build_standings_regular_season()
        if "period" in data:
            period_number = int(data["period"])
            if data.get("timeStartType") == "PERIOD_ONLY":
                return build_standings_only_period(period_number)
            return build_standings_by_period(period_number)
        if self.no_playoffs:
            # Without playoffs there's no playoff view for Fantrax to default to
            return build_standings_regular_season()
        return build_standings_default()


def new_mock_session(force_error: str | None = None, rotisserie: bool = False, no_playoffs: bool = False, tx_page_cap: int | None = None) -> MockSession:
    return MockSession(force_error=force_error, rotisserie=rotisserie, no_playoffs=no_playoffs, tx_page_cap=tx_page_cap)
