"""Fully-offline, mocked-session test suite for FantraxAPI.

Unlike test_live_api.py, these tests never touch the network, require no
credentials/env vars, and don't use Selenium. Instead they patch `requests.Session.post`
(via a small `MockSession` defined in `fixtures_mocked.py`) with a dispatcher that
inspects the posted JSON payload (`msgs[i]["method"]`/`view`/etc.) and returns
synthetic, recorded-shaped fixture data routed through the real parsing code in
`fantraxapi/objs/*`.

Run with: pytest tests/test_mocked_api.py -v
"""

import unittest
from datetime import date, datetime

from fixtures_mocked import (
    _FUTURE_GAME_LABEL,
    BYE_TEAM_ID,
    LEAGUE_ID,
    LEAGUE_NAME,
    LEAGUE_YEAR,
    MATCHUP_TABLE_TYPE_UNKNOWN,
    PLAYER_CENTER,
    PLAYER_INJURED,
    PLAYER_OUT,
    PLAYER_SUSPENDED,
    PLAYER_WINGER,
    SEASON_END,
    SEASON_START,
    TEAM_IDS,
    _matchup_cells,
    draft_pick_move,
    new_mock_session,
    player_move,
    trade_data,
)

from fantraxapi import League, NotLoggedIn, NotTeamInLeague
from fantraxapi.api import _request
from fantraxapi.exceptions import DateNotInSeason, FantraxException, NotMemberOfLeague, PeriodNotInSeason
from fantraxapi.objs import Player, Trade
from fantraxapi.objs.game import Game
from fantraxapi.objs.scoring_period import H2hPointsBased3, H2HRotisserie2, Matchup


def make_league(force_error: str | None = None) -> League:
    return League(LEAGUE_ID, session=new_mock_session(force_error=force_error))


class LeagueInfoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.league = make_league()

    def test_basic_info(self) -> None:
        self.assertEqual(self.league.name, LEAGUE_NAME)
        self.assertEqual(self.league.year, LEAGUE_YEAR)
        self.assertEqual(self.league.start_date, SEASON_START)
        self.assertEqual(self.league.end_date, SEASON_END)

    def test_positions(self) -> None:
        self.assertIn("206", self.league.positions)
        self.assertEqual(self.league.positions["206"].name, "Center")
        self.assertEqual(self.league.positions["206"].short_name, "C")
        self.assertEqual(str(self.league.positions["206"]), "[206:Center:C]")
        self.assertEqual(self.league.positions["206"], self.league.positions["206"])
        self.assertNotEqual(self.league.positions["206"], self.league.positions["207"])

    def test_status(self) -> None:
        self.assertEqual(self.league.status["3"].name, "Inj Res")
        self.assertEqual(self.league.status["4"].code, "FREE_AGENT")
        self.assertEqual(str(self.league.status["3"]), "[3:Inj Res]")
        self.assertEqual(self.league.status["3"], self.league.status["3"])
        self.assertNotEqual(self.league.status["3"], self.league.status["4"])
        # Entries without "name" are filtered out during reset_info
        self.assertNotIn("5", self.league.status)

    def test_scoring_dates(self) -> None:
        self.assertEqual(len(self.league.scoring_dates), 6)
        self.assertEqual(self.league.scoring_dates[21], date(2024, 10, 21))
        self.assertEqual(self.league.scoring_dates[28], date(2024, 10, 28))
        # Single-digit day: Fantrax renders the periodList key as "Nov 9" (unpadded).
        self.assertEqual(self.league.scoring_dates[9], date(2024, 11, 9))
        self.assertIn(date(2024, 10, 14), self.league.scoring_dates.values())
        self.assertNotIn(date(2024, 10, 20), self.league.scoring_dates.values())

    def test_scoring_periods(self) -> None:
        self.assertEqual(len(self.league.scoring_periods), 5)
        self.assertEqual(str(self.league.scoring_periods[2]), "[2:2024-10-21 - 2024-10-27]")
        self.assertEqual(self.league.scoring_periods[2].start, date(2024, 10, 21))
        self.assertEqual(self.league.scoring_periods[2].end, date(2024, 10, 27))
        self.assertNotEqual(self.league.scoring_periods[1], self.league.scoring_periods[2])
        self.assertEqual(self.league.scoring_periods[3], "3")
        self.assertEqual(self.league.scoring_periods[3], 3)
        self.assertIn("2024-10-21 - 2024-10-27", self.league.scoring_periods_lookup)
        self.assertEqual(self.league.scoring_periods_lookup["2024-10-21 - 2024-10-27"], self.league.scoring_periods[2])

    def test_teams_and_lookup(self) -> None:
        self.assertEqual(len(self.league.teams), 4)
        for team in self.league.teams:
            self.assertIn(team.id, TEAM_IDS)
        self.assertEqual(self.league.team(TEAM_IDS[0]).name, "Anchorage Avalanche")
        self.assertIs(self.league.team_lookup[TEAM_IDS[0]], self.league.team(TEAM_IDS[0]))
        self.assertEqual(self.league.team("bandits").name, "Bayview Bandits")
        self.assertRaises(NotTeamInLeague, self.league.team, "NotARealTeamIdentifier")

    def test_team_metadata(self) -> None:
        league = make_league()
        team = league.team(TEAM_IDS[0])
        self.assertTrue(team.commissioner)
        self.assertFalse(league.team(TEAM_IDS[1]).commissioner)
        calls = len(league.session.post_calls)
        self.assertEqual(team.owners, "anchor_andy")
        self.assertEqual(len(league.session.post_calls), calls + 1)
        # second access is served from the cache
        self.assertEqual(team.owners, "anchor_andy")
        self.assertEqual(len(league.session.post_calls), calls + 1)
        self.assertEqual(league.team(TEAM_IDS[3]).owners, "dock_dana")

    def test_team_metadata_survives_team_updates(self) -> None:
        # Standings responses carry a reduced team payload (no commissioner flag),
        # and any team-bearing response rebuilds league.teams -- richer fields and
        # the owners cache must survive the rebuild.
        league = make_league()
        team = league.team(TEAM_IDS[0])
        self.assertEqual(team.owners, "anchor_andy")
        league.standings()
        refreshed = league.team(TEAM_IDS[0])
        self.assertIsNot(refreshed, team)
        self.assertTrue(refreshed.commissioner)
        calls = len(league.session.post_calls)
        self.assertEqual(refreshed.owners, "anchor_andy")
        self.assertEqual(len(league.session.post_calls), calls)

    def test_construction_failure_propagates(self) -> None:
        # If get_init_info itself errors out (e.g. bad league), construction should
        # raise rather than yielding a half-built League.
        self.assertRaises(FantraxException, make_league, "bad_json")


class ScoringPeriodResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.league = make_league()

    def test_season_results(self) -> None:
        results = self.league.scoring_period_results(playoffs=False)
        self.assertEqual(len(results), 4)
        self.assertEqual(results[1].days, 7)
        self.assertFalse(results[1].playoffs)
        self.assertEqual(results[1].title, "Period 1")
        self.assertEqual(results[1].range, "2024-10-14 - 2024-10-20")
        # Dates are all safely in the past relative to "today"
        self.assertTrue(results[1].complete)
        self.assertFalse(results[1].current)
        self.assertFalse(results[1].future)

    def test_matchup_fields(self) -> None:
        results = self.league.scoring_period_results(playoffs=False)
        matchup = results[1].matchups["1"]
        self.assertEqual(matchup.away.name, "Anchorage Avalanche")
        self.assertEqual(matchup.home.name, "Bayview Bandits")
        self.assertEqual(matchup.away_score, 100.0)
        self.assertEqual(matchup.home_score, 90.0)
        winner, winner_score, loser, loser_score = matchup.winner()
        self.assertEqual(winner.name, "Anchorage Avalanche")
        self.assertEqual(winner_score, 100.0)
        self.assertEqual(loser.name, "Bayview Bandits")
        self.assertEqual(loser_score, 90.0)
        self.assertEqual(matchup.difference(), 10.0)
        self.assertEqual(str(matchup), "Period 1 Anchorage Avalanche (100.0) vs Bayview Bandits (90.0)")
        self.assertEqual(matchup.composite_key, f"{matchup.home.id}_{matchup.away.id}")

    def test_matchup_tie(self) -> None:
        results = self.league.scoring_period_results(playoffs=False)
        tied = results[2].matchups["2"]
        self.assertEqual(tied.away_score, 70.0)
        self.assertEqual(tied.home_score, 70.0)
        self.assertEqual(tied.winner(), (None, None, None, None))
        self.assertEqual(tied.difference(), 0.0)
        # Matchup.__str__ takes the "winner" branch whenever either score is truthy,
        # even on a tie - so a non-zero tie renders with empty winner/loser fields.
        self.assertEqual(str(tied), "Period 2 None (None) vs None (None)")

    def test_composite_key_falls_back_to_raw_content_for_unresolved_teams(self) -> None:
        # When a row's teamId doesn't match a league member, away/home fall back to the
        # raw "content" string rather than a Team instance (the pre-paired-cell parsing
        # lives on H2hPointsBased3) -- composite_key, on the base, must handle that side too.
        results = self.league.scoring_period_results(playoffs=False)
        matchup = H2hPointsBased3(
            results[1],
            "ghost",
            [
                {"teamId": "ghost-team-a", "content": "Ghost A"},
                {"content": "10.0"},
                {"teamId": "ghost-team-b", "content": "Ghost B"},
                {"content": "5.0"},
            ],
        )
        self.assertEqual(matchup.away, "Ghost A")
        self.assertEqual(matchup.home, "Ghost B")
        self.assertEqual(matchup.composite_key, "Ghost B_Ghost A")
        # difference() works even when both sides are raw strings (no Team).
        self.assertEqual(matchup.difference(), 5.0)

    def test_playoffs_with_other_brackets(self) -> None:
        results = self.league.scoring_period_results(season=False, playoffs=True)
        self.assertEqual(len(results), 1)
        playoff_result = results[5]
        self.assertTrue(playoff_result.playoffs)
        self.assertEqual(playoff_result.title, "Playoff Period 5")
        self.assertEqual(playoff_result.days, 7)
        self.assertIn("Consolation", playoff_result.other_brackets)
        self.assertEqual(len(playoff_result.other_brackets["Consolation"]), 1)
        consolation_matchup = playoff_result.other_brackets["Consolation"]["1"]
        self.assertEqual(consolation_matchup.away.name, "Cedar Crushers")
        self.assertEqual(consolation_matchup.home.name, "Dockside Dragons")
        self.assertEqual(str(consolation_matchup), "Playoff Period 5 Cedar Crushers (150.0) vs Dockside Dragons (140.0)")
        self.assertIn("Playoff Period 5 Anchorage Avalanche (200.5) vs Bayview Bandits (175.25)", str(playoff_result))
        self.assertIn("Consolation", str(playoff_result))

    def test_season_and_playoffs_combined(self) -> None:
        results = self.league.scoring_period_results()
        self.assertEqual(len(results), 5)
        self.assertFalse(results[4].playoffs)
        self.assertTrue(results[5].playoffs)


class RotisserieScoringPeriodResultsTests(unittest.TestCase):
    """Mocked coverage for the H2hRotisserie2 parsing path.

    ScoringPeriodResultsTests above only ever sees H2hPointsBased3-shaped data
    (the only tableType the shared fixture league reports), so H2HRotisserie2,
    _h2h_rot_2_factory, scoring_grid/categories, the bye-team fallback, and
    other_brackets routed through rotisserie-shaped data were previously only
    reachable via the live, network-dependent tests in test_live_matchup_types.py.
    This uses a separate MockSession(rotisserie=True) so the fixtures above stay
    untouched.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.league = League(LEAGUE_ID, session=new_mock_session(rotisserie=True))

    def test_h2h_rotisserie_matchup_fields(self) -> None:
        t1, t2, t3, t4 = TEAM_IDS
        results = self.league.scoring_period_results(playoffs=False)
        self.assertEqual(results[1].matchup_type, "H2hRotisserie2")
        # Unlike H2hPointsBased3 (keyed by 1-based row position), _h2h_rot_2_factory
        # keys matchups by their matchupId ("<away_id>_<home_id>") straight from the data.
        self.assertEqual(set(results[1].matchups), {f"{t1}_{t2}", f"{t3}_{t4}"})
        matchup = results[1].matchups[f"{t1}_{t2}"]
        self.assertIsInstance(matchup, H2HRotisserie2)
        self.assertFalse(matchup.no_contest)
        self.assertEqual(matchup.away.name, "Anchorage Avalanche")
        self.assertEqual(matchup.home.name, "Bayview Bandits")
        self.assertEqual(matchup.away_score, 2.5)
        self.assertEqual(matchup.home_score, 1.5)
        self.assertEqual(matchup.home_categories["opponent"], matchup.away.id)
        self.assertEqual(matchup.away_categories["opponent"], matchup.home.id)
        # toolTip wins over plain "content" when both are present
        self.assertEqual(matchup.scoring_grid["PIM"], {matchup.home.id: 33.1, matchup.away.id: 40.2})
        # non-numeric content falls back to 0.0 (home side) rather than raising
        self.assertEqual(matchup.scoring_grid["G"], {matchup.home.id: 0.0, matchup.away.id: 30.0})
        self.assertEqual(matchup.home_categories["G"], 0.0)
        self.assertEqual(matchup.away_categories["G"], 30.0)
        # The "Pts" (Category points) column drives home_score/away_score but is a summary,
        # not a scoring category -- so it (and W/L/T) is excluded from the grid/categories.
        self.assertEqual(matchup.away_score, 2.5)
        self.assertEqual(matchup.home_score, 1.5)
        self.assertEqual(set(matchup.scoring_grid), {"G", "A", "PIM", "BLK"})
        for summary in ("W", "L", "T", "Pts"):
            self.assertNotIn(summary, matchup.scoring_grid)
            self.assertNotIn(summary, matchup.category_winners)
            self.assertNotIn(summary, matchup.home_categories)
        self.assertEqual(matchup.composite_key, f"{matchup.home.id}_{matchup.away.id}")
        # Per-category win/loss (gainColor) is captured, not discarded.
        self.assertEqual(matchup.category_winners["G"], matchup.away.id)
        self.assertEqual(matchup.category_winners["A"], matchup.home.id)
        self.assertEqual(matchup.category_winners["PIM"], matchup.away.id)
        # A tied category (gainColor 0 on both sides) is recorded as None -- now unambiguous
        # since summary columns no longer share that sentinel.
        self.assertIsNone(matchup.category_winners["BLK"])
        # winner()/difference() (shared on the base) work off the public scores, so
        # they apply to rotisserie too -- difference() no longer needs Decimal internals.
        self.assertEqual(matchup.winner()[0].name, "Anchorage Avalanche")
        self.assertEqual(matchup.difference(), 1.0)

    def test_h2h_rotisserie_second_matchup(self) -> None:
        t1, t2, t3, t4 = TEAM_IDS
        results = self.league.scoring_period_results(playoffs=False)
        matchup = results[1].matchups[f"{t3}_{t4}"]
        self.assertIsInstance(matchup, H2HRotisserie2)
        # This matchup's rows are supplied in reverse matchupId order (home row first),
        # so passing here proves away/home follow the matchupId, not arrival order.
        self.assertEqual(matchup.away.name, "Cedar Crushers")
        self.assertEqual(matchup.home.name, "Dockside Dragons")
        self.assertEqual(matchup.away_score, 3.0)
        self.assertEqual(matchup.home_score, 1.0)
        self.assertEqual(matchup.scoring_grid["PIM"], {matchup.home.id: 22.0, matchup.away.id: 12.0})
        # No gainColor on this matchup -> every category winner is None.
        self.assertTrue(all(v is None for v in matchup.category_winners.values()))

    def test_unrecognized_table_type_falls_back_to_points_based_matchup(self) -> None:
        results = self.league.scoring_period_results(playoffs=False)
        self.assertEqual(results[2].matchup_type, MATCHUP_TABLE_TYPE_UNKNOWN)
        matchup = results[2].matchups["1"]
        # Unknown table types parse as the pre-paired points-based shape.
        self.assertIs(type(matchup), H2hPointsBased3)
        self.assertIsInstance(matchup, Matchup)
        self.assertEqual(matchup.away.name, "Anchorage Avalanche")
        self.assertEqual(matchup.away_score, 110.5)

    def test_other_brackets_with_rotisserie_data(self) -> None:
        t3 = TEAM_IDS[2]
        results = self.league.scoring_period_results(season=False, playoffs=True)
        playoff_result = results[5]
        self.assertIn("Consolation", playoff_result.other_brackets)
        bracket = playoff_result.other_brackets["Consolation"]
        self.assertEqual(set(bracket), {f"{t3}_{BYE_TEAM_ID}"})
        consolation_matchup = bracket[f"{t3}_{BYE_TEAM_ID}"]
        self.assertIsInstance(consolation_matchup, H2HRotisserie2)
        self.assertEqual(consolation_matchup.away.name, "Cedar Crushers")
        # The bracket's other slot is an unrecognized teamId -> bye placeholder Team
        self.assertEqual(consolation_matchup.home.name, "Bye")
        self.assertEqual(consolation_matchup.home.short, "BYE")
        # A bye slot makes this a non-contest: it's flagged and recorded as a 0.5-0.5 tie
        # (the placeholder's "Pts" cell is ignored), and renders as such.
        self.assertTrue(consolation_matchup.no_contest)
        self.assertEqual(consolation_matchup.away_score, consolation_matchup.home_score)
        self.assertEqual(str(consolation_matchup), "Playoff Period 5 Cedar Crushers vs Bye (No Contest)")
        # composite_key works against the placeholder Team just like a real one
        self.assertEqual(consolation_matchup.composite_key, f"bye_{consolation_matchup.away.id}")

    def test_bye_placeholder_team_owners(self) -> None:
        # The Bye placeholder H2HRotisserie2 fabricates for an empty bracket slot
        # isn't a league member; owners must come back empty without issuing the
        # roster request (live, that request errors out).
        results = self.league.scoring_period_results(season=False, playoffs=True)
        bye_team = results[5].other_brackets["Consolation"][f"{TEAM_IDS[2]}_{BYE_TEAM_ID}"].home
        self.assertEqual(bye_team.name, "Bye")
        calls = len(self.league.session.post_calls)
        self.assertEqual(bye_team.owners, "")
        self.assertEqual(len(self.league.session.post_calls), calls)

    def test_playoff_round_number_does_not_overwrite_season_week(self) -> None:
        # The rotisserie playoff fixture is captioned "Scoring Period: Playoffs 1"
        # (the style real NBA leagues use). The round number used to be parsed as a
        # season week number, so this playoff round landed on key 1 and clobbered
        # Period 1; it belongs at key 5 via its date range.
        results = self.league.scoring_period_results()
        self.assertEqual(set(results), {1, 2, 5})
        self.assertFalse(results[1].playoffs)
        self.assertEqual(results[1].name, "Period 1")
        self.assertTrue(results[5].playoffs)
        self.assertEqual(results[5].name, "Scoring Period: Playoffs 1")
        self.assertEqual(results[5].title, "Playoff Period 5")

    def test_add_matchups(self) -> None:
        results = self.league.scoring_period_results(playoffs=False)
        result = results[2]
        self.assertEqual(set(result.matchups), {"1", "2"})
        t1, t4 = TEAM_IDS[0], TEAM_IDS[3]
        result.add_matchups({"rows": [_matchup_cells(t1, "200.0", t4, "150.0")]})
        # add_matchups merges by stringified 1-based row position, so this overwrites key "1"...
        self.assertEqual(set(result.matchups), {"1", "2"})
        self.assertEqual(result.matchups["1"].away.name, "Anchorage Avalanche")
        self.assertEqual(result.matchups["1"].away_score, 200.0)
        self.assertEqual(result.matchups["1"].home.name, "Dockside Dragons")
        self.assertEqual(result.matchups["1"].home_score, 150.0)
        # ...while leaving the other entry untouched
        self.assertEqual(result.matchups["2"].away.name, "Bayview Bandits")


class StandingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.league = make_league()

    def test_default_standings(self) -> None:
        # Once playoffs exist, the viewless getStandings response is the PLAYOFFS view
        # (see build_standings_default), so standings() must re-request the season view.
        standings = self.league.standings()
        self.assertEqual(
            str(standings),
            (
                "Standings\n"
                "1: Anchorage Avalanche (4-0-0)\n"
                "2: Bayview Bandits (2-2-0)\n"
                "3: Cedar Crushers (1-3-0)\n"
                "4: Dockside Dragons (1-3-0)"
            ),
        )
        last_view = self.league.session.post_calls[-1]["json"]["msgs"][-1]["data"]["view"]
        self.assertEqual(last_view, "REGULAR_SEASON")
        record = standings.ranks[1]
        self.assertEqual(record.team.name, "Anchorage Avalanche")
        self.assertEqual(record.win, 4)
        self.assertEqual(record.loss, 0)
        self.assertEqual(record.tie, 0)
        # The season fixture mirrors leagues whose standings use the gb/cpf/cpa column
        # keys (and no points/wwOrder columns at all)
        self.assertEqual(record.points, 0)
        self.assertEqual(record.win_percentage, 1.0)
        self.assertEqual(record.games_back, 0.0)  # leader shows gb "-"
        self.assertEqual(record.points_for, 405.5)
        self.assertEqual(record.points_against, 300.0)
        self.assertEqual(record.streak, "W4")
        self.assertEqual(standings.ranks[3].games_back, 3.5)
        self.assertEqual(str(record), "1: Anchorage Avalanche (4-0-0)")
        self.assertIsNone(standings.scoring_period_number)

    def test_playoff_standings(self) -> None:
        standings = self.league.playoff_standings()
        self.assertEqual(len(standings.ranks), 2)
        self.assertEqual(standings.ranks[1].team.name, "Anchorage Avalanche")
        self.assertEqual(standings.ranks[1].win, 1)
        self.assertEqual(standings.ranks[2].team.name, "Bayview Bandits")
        self.assertEqual(standings.ranks[2].loss, 1)
        self.assertEqual(str(standings), "Standings\n1: Anchorage Avalanche (1-0-0)\n2: Bayview Bandits (0-1-0)")

    def test_playoff_standings_without_playoffs_raises(self) -> None:
        league = League(LEAGUE_ID, session=new_mock_session(no_playoffs=True))
        self.assertRaises(FantraxException, league.playoff_standings)
        # standings() still works without a re-request in a playoff-less league
        self.assertEqual(league.standings().ranks[1].team.name, "Anchorage Avalanche")

    def test_standings_by_period(self) -> None:
        standings = self.league.standings(scoring_period_number=2)
        self.assertEqual(standings.scoring_period_number, 2)
        self.assertIn("Period 2", str(standings))
        self.assertEqual(standings.ranks[1].team.name, "Anchorage Avalanche")
        self.assertEqual(standings.ranks[1].points, 4)
        self.assertEqual(standings.ranks[2].team.name, "Cedar Crushers")
        self.assertEqual(standings.ranks[4].points_for, 145.5)

    def test_standings_only_period(self) -> None:
        standings = self.league.standings(scoring_period_number=2, only_period=True)
        self.assertEqual(standings.ranks[1].points_for, 110.5)
        self.assertEqual(standings.ranks[3].points_for, 95.5)
        self.assertEqual(standings.ranks[1].team.name, "Anchorage Avalanche")


class TradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.league = make_league()

    def test_hand_built_trade(self) -> None:
        t1, t2 = TEAM_IDS[0], TEAM_IDS[1]
        trade = Trade(
            self.league,
            trade_data(
                "tradeset_xyz",
                t1,
                "Nov 2, 3:00 AM EDT",
                "Nov 2, 3:00 AM EDT",
                "Nov 2, 3:00 AM EDT",
                [
                    draft_pick_move(t1, t2, 2025, 2, t1),
                    draft_pick_move(t2, t1, 2025, 10, t2),
                    player_move(t2, t1, PLAYER_CENTER, 5.5, 100.5),
                ],
            ),
        )
        self.assertEqual(trade.trade_id, "tradeset_xyz")
        self.assertEqual(trade.proposed_by.name, "Anchorage Avalanche")
        self.assertEqual(trade.proposed, trade.accepted)
        self.assertEqual(trade.proposed, trade.executed)
        self.assertEqual(len(trade.moves), 3)
        self.assertEqual(
            str(trade),
            (
                "From: Anchorage Avalanche To: Bayview Bandits Pick: 2025, Round 2 (Anchorage Avalanche)\n"
                "From: Bayview Bandits To: Anchorage Avalanche Pick: 2025, Round 10 (Bayview Bandits)\n"
                "From: Bayview Bandits To: Anchorage Avalanche TradePlayer: Connor Centerman C - TOR 5.5 100.5"
            ),
        )

    def test_winter_trade_time_uses_est(self) -> None:
        # Eastern flips to EST in winter; the parser must not assume the EDT token.
        # Jan 15 only falls in-season for the end year (2025), so it resolves there.
        t1, t2 = TEAM_IDS[0], TEAM_IDS[1]
        trade = Trade(
            self.league,
            trade_data(
                "tradeset_est",
                t1,
                "Jan 15, 8:00 PM EST",
                "Jan 15, 8:00 PM EST",
                "Jan 15, 8:00 PM EST",
                [player_move(t2, t1, PLAYER_CENTER, 1.0, 1.0)],
            ),
        )
        self.assertEqual(trade.proposed, datetime(2025, 1, 15, 20, 0))

    def test_parse_datetime_out_of_season_raises(self) -> None:
        t1, t2 = TEAM_IDS[0], TEAM_IDS[1]
        bad_trade_dict = trade_data(
            "tradeset_bad",
            t1,
            "Jul 1, 3:00 AM EDT",
            "Jul 1, 3:00 AM EDT",
            "Jul 1, 3:00 AM EDT",
            [player_move(t2, t1, PLAYER_CENTER, 1.0, 1.0)],
        )
        self.assertRaises(DateNotInSeason, Trade, self.league, bad_trade_dict)

    def test_game_leap_day_does_not_crash(self) -> None:
        # Feb 29 is invalid in a non-leap candidate year; the date parser must skip the
        # bad year gracefully (DateNotInSeason) instead of raising ValueError mid-parse.
        player = Player(self.league, PLAYER_CENTER)
        self.assertRaises(DateNotInSeason, Game, self.league, player, "Thu 02/29", {"eventId": "g1", "content": "x"})

    def test_pending_trades_via_league(self) -> None:
        league = make_league()
        trades = league.pending_trades()
        self.assertEqual(len(trades), 1)
        trade = trades[0]
        self.assertEqual(trade.trade_id, "tradeset001")
        self.assertEqual(trade.proposed_by.name, "Anchorage Avalanche")
        self.assertEqual(len(trade.moves), 2)
        self.assertEqual(trade.moves[1].player.name, "Connor Centerman")
        self.assertTrue(league.logged_in)


class TradeBlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.league = make_league()

    def test_trade_blocks(self) -> None:
        blocks = self.league.trade_block()
        # Two entries with len(block) <= 2 are filtered out
        self.assertEqual(len(blocks), 3)

        first = blocks[0]
        self.assertEqual(first.team.name, "Anchorage Avalanche")
        self.assertEqual(first.note, "Looking to add scoring depth, will listen on anyone")
        self.assertEqual(str(first), "Looking to add scoring depth, will listen on anyone")
        self.assertIn("C", first.players_offered)
        self.assertIn("W", first.players_offered)
        self.assertEqual(len(first.players_offered["W"]), 2)
        self.assertIn("D", first.players_wanted)
        self.assertEqual([p.short_name for p in first.positions_offered], ["C", "W"])
        self.assertEqual([p.short_name for p in first.positions_wanted], ["D"])
        self.assertEqual(first.stats_offered, ["G", "A"])
        self.assertEqual(first.stats_wanted, ["PIM"])

        second = blocks[1]
        self.assertEqual(second.players_offered, {})
        self.assertEqual(len(second.positions_wanted), 2)
        self.assertEqual(second.stats_offered, [])

        third = blocks[2]
        self.assertEqual(third.note, "")
        self.assertEqual(third.positions_offered, [])
        self.assertIn("Skt", third.players_offered)

    def test_trade_block_not_logged_in(self) -> None:
        # Construct normally (so reset_info succeeds), then swap in a session that
        # always answers with the "not logged in" pageError to exercise that path.
        league = make_league()
        league.session = new_mock_session(force_error="not_logged_in")
        self.assertRaises(NotLoggedIn, league.trade_block)
        self.assertFalse(league.logged_in)
        self.assertRaises(NotLoggedIn, league.pending_trades)

    def test_trade_block_not_member_of_league(self) -> None:
        league = make_league()
        league.session = new_mock_session(force_error="not_member")
        self.assertRaises(NotMemberOfLeague, league.trade_block)


class TransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.league = make_league()

    def test_transactions_grouped_by_set_id(self) -> None:
        transactions = self.league.transactions(count=10)
        self.assertEqual(len(transactions), 3)

        first = transactions[0]
        self.assertEqual(first.id, "txset_a")
        self.assertEqual(first.team.name, "Anchorage Avalanche")
        self.assertEqual(first.period, 1)
        self.assertTrue(first.executed)
        self.assertEqual(len(first.players), 2)
        self.assertEqual(first.players[0].type, "WW")
        self.assertEqual(first.players[0].name, "Henry Healthy")
        self.assertEqual(first.players[0].result, "Executed")
        self.assertTrue(first.players[0].executed)
        self.assertEqual(first.players[1].type, "DROP")
        self.assertEqual(first.players[1].name, "Owen Outerbridge")
        self.assertEqual(str(first.players[0]), "WW Henry Healthy")
        self.assertIn("Henry Healthy", str(first))

        # A waiver claim that was cancelled: data the parser used to throw away.
        second = transactions[1]
        self.assertEqual(len(second.players), 1)
        self.assertEqual(second.players[0].type, "WW")
        self.assertEqual(second.players[0].name, "Sam Suspendo")
        self.assertEqual(second.period, 2)
        self.assertFalse(second.executed)
        self.assertFalse(second.players[0].executed)
        self.assertEqual(second.players[0].result, "Cancelled")

        third = transactions[2]
        self.assertEqual(len(third.players), 2)
        self.assertEqual(third.players[0].type, "FA")
        self.assertEqual(third.players[0].name, "Connor Centerman")
        self.assertEqual(third.players[0].transaction_type, "Claim")
        self.assertEqual(third.players[1].type, "DROP")
        self.assertEqual(third.players[1].name, "Ivan Ironside")

    def test_transactions_paginate_and_stitch_across_pages(self) -> None:
        # Server caps each page at 2 rows, so the 5 rows arrive over 3 pages and
        # txset_c (its two rows) straddles a page boundary -- it must still group as one.
        session = new_mock_session(tx_page_cap=2)
        league = League(LEAGUE_ID, session=session)
        transactions = league.transactions(count=10)
        self.assertEqual([t.id for t in transactions], ["txset_a", "txset_b", "txset_c"])
        self.assertEqual(len(transactions[2].players), 2)

        tx_pages = [c["json"]["msgs"][0]["data"] for c in session.post_calls if c["json"]["msgs"][0]["method"] == "getTransactionDetailsHistory"]
        self.assertGreater(len(tx_pages), 1)
        self.assertEqual([p["pageNumber"] for p in tx_pages], ["1", "2", "3"])

    def test_transactions_count_limits_results(self) -> None:
        league = League(LEAGUE_ID, session=new_mock_session(tx_page_cap=2))
        transactions = league.transactions(count=2)
        self.assertEqual([t.id for t in transactions], ["txset_a", "txset_b"])


class PositionCountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.league = make_league()

    def test_position_counts_default(self) -> None:
        team = self.league.team(TEAM_IDS[0])
        counts = team.position_counts()
        for short_name in ["C", "W", "D", "TmG"]:
            self.assertIn(short_name, counts)
        self.assertEqual(counts["C"].gp, 17)
        self.assertIsNone(counts["C"].min)
        self.assertEqual(counts["C"].max, 3)
        self.assertIsNone(counts["W"].max)
        self.assertEqual(counts["TmG"].min, 1)
        self.assertEqual(counts["TmG"].max, 7)
        self.assertEqual(counts["TmG"].name, "Team Goalie")
        self.assertEqual(str(counts["C"]), "[Center:17]:Max(3)]")

    def test_position_counts_for_period(self) -> None:
        team = self.league.team(TEAM_IDS[0])
        counts = team.position_counts(2)
        self.assertEqual(counts["C"].gp, 5)
        self.assertEqual(counts["TmG"].gp, 2)
        self.assertEqual(counts["TmG"].min, 1)
        self.assertEqual(counts["TmG"].max, 2)

    def test_position_counts_period_not_in_season(self) -> None:
        team = self.league.team(TEAM_IDS[0])
        self.assertRaises(PeriodNotInSeason, team.position_counts, 999)


class LiveScoresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.league = make_league()

    def test_live_scores(self) -> None:
        team = self.league.team(TEAM_IDS[0])
        scores = team.live_scores(date(2024, 10, 21))
        self.assertEqual(len(scores), 1)
        self.assertEqual(scores[0].name, "Connor Centerman")
        self.assertEqual(scores[0].points, 12.5)
        self.assertEqual(scores[0].points_date, date(2024, 10, 21))
        self.assertEqual(scores[0].team.name, "Anchorage Avalanche")

        team2 = self.league.team(TEAM_IDS[1])
        scores2 = team2.live_scores(date(2024, 10, 21))
        self.assertEqual(scores2[0].name, "Wendell Wingfield")
        self.assertEqual(scores2[0].points, 7.0)

    def test_live_scores_category_breakdown(self) -> None:
        team = self.league.team(TEAM_IDS[0])
        center = team.live_scores(date(2024, 10, 21))[0]
        # Per-category scoring (object2) is captured and labelled, not discarded.
        self.assertEqual(set(center.categories), {"G", "A", "PIM"})
        self.assertEqual(center.categories["G"].name, "Goals")
        self.assertEqual(center.categories["G"].value, 2.0)
        self.assertEqual(center.categories["G"].fantasy_points, 12.0)
        # Negative contributions are preserved.
        self.assertEqual(center.categories["PIM"].fantasy_points, -3.5)
        # Category fantasy points reconcile to the player's total.
        self.assertAlmostEqual(sum(c.fantasy_points for c in center.categories.values()), center.points)

        # A scorer without an object2 breakdown simply has no categories.
        winger = self.league.team(TEAM_IDS[1]).live_scores(date(2024, 10, 21))[0]
        self.assertEqual(winger.categories, {})

        # Team 3 is not part of the active matchup on this date -> no entry
        self.assertNotIn(TEAM_IDS[2], self.league.live_scores(date(2024, 10, 21)))

    def test_live_scores_date_not_in_season(self) -> None:
        team = self.league.team(TEAM_IDS[0])
        self.assertRaises(DateNotInSeason, team.live_scores, date(2024, 10, 20))
        self.assertRaises(DateNotInSeason, team.live_scores, date(2024, 7, 4))


class TeamRosterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.league = make_league()

    def test_roster(self) -> None:
        team = self.league.team(TEAM_IDS[0])
        roster = team.roster(22)
        self.assertEqual(
            str(roster),
            (
                "Anchorage Avalanche Roster\n"
                "C: Connor Centerman\n"
                "W: Wendell Wingfield\n"
                "D: Derek Defenton\n"
                "D: Empty"
            ),
        )
        self.assertEqual(roster.team.name, "Anchorage Avalanche")
        self.assertEqual(roster.period_number, 22)
        self.assertEqual(roster.period_date, date(2024, 10, 22))
        self.assertEqual(roster.active, 11)
        self.assertEqual(roster.active_max, 12)
        self.assertEqual(roster.reserve, 7)
        self.assertEqual(roster.reserve_max, 18)
        self.assertEqual(roster.injured, 1)
        self.assertEqual(roster.injured_max, 3)

        # age (universal across sports) is captured; non-salary league -> no salary cap
        # or per-player salary/contract, but draft picks are still reported.
        self.assertEqual(roster.rows[0].age, 26)
        self.assertIsNone(roster.rows[0].salary)
        self.assertIsNone(roster.rows[0].contract_year)
        self.assertIsNone(roster.salary)
        self.assertEqual(roster.cap_hit_penalties, [])
        self.assertIsNone(team.salary_cap)
        self.assertEqual(len(roster.draft_picks), 3)
        self.assertEqual(roster.draft_picks[0].year, 2026)
        self.assertEqual(roster.draft_picks[0].round, 1)
        self.assertEqual(roster.draft_picks[0].original_owner.name, "Anchorage Avalanche")
        # a traded pick records a different original owner
        self.assertEqual(roster.draft_picks[1].original_owner.name, "Bayview Bandits")
        self.assertEqual(str(roster.draft_picks[1]), "2026 Round 2")

        center_row = roster.rows[0]
        self.assertEqual(str(center_row.position), "[206:Center:C]")
        self.assertEqual(str(center_row.player), "Connor Centerman")
        self.assertEqual(center_row.total_fantasy_points, 21.8)
        self.assertEqual(center_row.fantasy_points_per_game, 3.1)
        self.assertIsNone(center_row.game_today)
        self.assertIn(_FUTURE_GAME_LABEL, center_row.future_games)
        future_game = center_row.future_games[_FUTURE_GAME_LABEL]
        # "@MTL": the player's team (TOR) is visiting, so this is an away game.
        self.assertFalse(future_game.home)
        self.assertTrue(future_game.away)
        self.assertEqual(future_game.opponent, "MTL")
        self.assertEqual(str(future_game), f"[future_p001:TOR @MTL {future_game.time}]")

        wing_row = roster.rows[1]
        self.assertEqual(str(wing_row.player), "Wendell Wingfield")
        self.assertEqual(wing_row.total_fantasy_points, 14.7)
        self.assertIsNotNone(wing_row.game_today)
        # "CAR" (no @): the player's team (BOS) is hosting, so this is a home game.
        self.assertTrue(wing_row.game_today.home)
        self.assertFalse(wing_row.game_today.away)
        self.assertEqual(wing_row.game_today.opponent, "CAR")
        self.assertEqual(wing_row.game_today.id, "today_p002")
        self.assertEqual(wing_row.future_games, {})

        empty_row = roster.rows[3]
        self.assertEqual(str(empty_row), "D: Empty")
        self.assertIsNone(empty_row.player)
        self.assertIsNone(empty_row.total_fantasy_points)
        self.assertIsNone(empty_row.game_today)

    def test_roster_period_not_in_season(self) -> None:
        team = self.league.team(TEAM_IDS[0])
        self.assertRaises(PeriodNotInSeason, team.roster, 12345)

    def test_doubleheader_future_game(self) -> None:
        # A doubleheader is one Game on a date with two start times (baseball); the
        # opponent/weekday parse despite the weekday sitting in the first content part.
        roster = self.league.team(TEAM_IDS[0]).roster(22)
        defense_row = roster.rows[2]
        game = defense_row.future_games[_FUTURE_GAME_LABEL]
        self.assertEqual(game.opponent, "BOS")
        self.assertEqual(len(game.times), 2)
        self.assertEqual([t.strftime("%I:%M%p") for t in game.times], ["01:35PM", "07:10PM"])
        # `time` is the first start time
        self.assertEqual(game.time, game.times[0])

    def test_played_game_home_away(self) -> None:
        # A played game reads "<away> <score><br/>@<home> <score> F"; the "@" side is home.
        player = Player(self.league, PLAYER_CENTER)  # team short name "TOR"
        away = Game(self.league, player, _FUTURE_GAME_LABEL, {"eventId": "g1", "content": "TOR 3<br/>@BOS 5 F"})
        self.assertEqual(away.opponent, "BOS")
        self.assertTrue(away.away)
        self.assertFalse(away.home)
        home = Game(self.league, player, _FUTURE_GAME_LABEL, {"eventId": "g2", "content": "BOS 3<br/>@TOR 5 F"})
        self.assertEqual(home.opponent, "BOS")
        self.assertTrue(home.home)
        self.assertFalse(home.away)


class SalaryCapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.league = League(LEAGUE_ID, session=new_mock_session(salary=True))

    def test_player_salary_and_contract(self) -> None:
        roster = self.league.team(TEAM_IDS[0]).roster(22)
        center = roster.rows[0]
        self.assertEqual(center.salary, 26.0)
        self.assertEqual(center.contract_year, "2026")
        self.assertEqual(center.age, 26)
        wing = roster.rows[1]
        self.assertEqual(wing.salary, 67.0)
        self.assertEqual(wing.contract_year, "2027")
        # an empty slot carries no salary/contract
        self.assertIsNone(roster.rows[3].salary)
        self.assertIsNone(roster.rows[3].contract_year)

    def test_roster_salary_cap_info(self) -> None:
        salary = self.league.team(TEAM_IDS[0]).roster(22).salary
        self.assertIsNotNone(salary)
        self.assertEqual(salary.cap, 2000.0)
        self.assertEqual(salary.used, 1951.0)
        self.assertEqual(salary.remaining, 49.0)
        self.assertEqual(salary.floor, 1250.0)
        # claim budget arrives as a comma string and is normalized to a float
        self.assertEqual(salary.claim_budget, 1604.0)

    def test_team_salary_cap_passthrough(self) -> None:
        team = self.league.team(TEAM_IDS[1])
        self.assertEqual(team.salary_cap, 2000.0)
        # second access is served from the cache (no extra roster request)
        calls = len(self.league.session.post_calls)
        self.assertEqual(team.salary_cap, 2000.0)
        self.assertEqual(len(self.league.session.post_calls), calls)

    def test_cap_hit_penalties(self) -> None:
        penalties = self.league.team(TEAM_IDS[0]).roster(22).cap_hit_penalties
        self.assertEqual(len(penalties), 1)
        penalty = penalties[0]
        self.assertEqual(penalty.player.name, "Owen Outerbridge")
        self.assertEqual(penalty.amount, 0.5)
        self.assertEqual(penalty.start_period, "1 (Mar 25/26)")
        self.assertEqual(penalty.ending_season_year, 2027)
        self.assertEqual(penalty.description, "Buyout penalty")


class PlayerFlagsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.league = make_league()

    def test_healthy_player_has_no_flags(self) -> None:
        player = Player(self.league, PLAYER_CENTER)
        self.assertFalse(player.day_to_day)
        self.assertFalse(player.out)
        self.assertFalse(player.injured_reserve)
        self.assertFalse(player.suspended)
        self.assertFalse(player.injured)

    def test_day_to_day_flag(self) -> None:
        player = Player(self.league, PLAYER_WINGER)
        self.assertTrue(player.day_to_day)
        self.assertTrue(player.injured)
        self.assertFalse(player.out)
        self.assertFalse(player.injured_reserve)
        self.assertFalse(player.suspended)

    def test_injured_reserve_flag(self) -> None:
        player = Player(self.league, PLAYER_INJURED)
        self.assertTrue(player.injured_reserve)
        self.assertTrue(player.injured)
        self.assertFalse(player.day_to_day)

    def test_out_flag(self) -> None:
        player = Player(self.league, PLAYER_OUT)
        self.assertTrue(player.out)
        self.assertTrue(player.injured)
        self.assertFalse(player.day_to_day)
        self.assertFalse(player.injured_reserve)

    def test_suspended_flag(self) -> None:
        player = Player(self.league, PLAYER_SUSPENDED)
        self.assertTrue(player.suspended)
        # Suspended is not part of `injured`
        self.assertFalse(player.injured)


class ApiErrorPathTests(unittest.TestCase):
    """Exercises fantraxapi.api._request's error handling directly with a MockSession."""

    def test_invalid_json_raises_fantrax_exception(self) -> None:
        session = new_mock_session(force_error="bad_json")
        self.assertRaises(FantraxException, _request, LEAGUE_ID, [], session)

    def test_http_error_raises_fantrax_exception(self) -> None:
        session = new_mock_session(force_error="http_error")
        self.assertRaises(FantraxException, _request, LEAGUE_ID, [], session)

    def test_unexpected_error_code_raises_fantrax_exception(self) -> None:
        session = new_mock_session(force_error="unexpected_error")
        try:
            _request(LEAGUE_ID, [], session)
            self.fail("Expected FantraxException")
        except NotLoggedIn:
            self.fail("Should not raise NotLoggedIn for UNEXPECTED_ERROR")
        except FantraxException as e:
            self.assertEqual(str(e), "Something Broke")

    def test_unknown_error_code_raises_fantrax_exception(self) -> None:
        session = new_mock_session(force_error="unknown_error")
        self.assertRaises(FantraxException, _request, LEAGUE_ID, [], session)

    def test_not_logged_in_code(self) -> None:
        session = new_mock_session(force_error="not_logged_in")
        self.assertRaises(NotLoggedIn, _request, LEAGUE_ID, [], session)

    def test_not_member_of_league_code(self) -> None:
        session = new_mock_session(force_error="not_member")
        self.assertRaises(NotMemberOfLeague, _request, LEAGUE_ID, [], session)


if __name__ == "__main__":
    unittest.main()
