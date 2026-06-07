"""Live integration tests that hit the real Fantrax API.

Requires FANTRAX_USERNAME, FANTRAX_PASSWORD, and LEAGUE_ID env vars (e.g. via a
.env file) for a league matching the hardcoded expectations below. Logged-in
tests drive a headless Chrome via Selenium to obtain session cookies unless
LOCAL=True and a cached `fantraxloggedin.cookie` is present.

For tests that don't require live credentials or a specific league's data, see
test_mocked_api.py.
"""

import os
import pickle
import sys
import time
import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from dotenv import load_dotenv
from requests import Session
from selenium import webdriver
from selenium.webdriver import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from fantraxapi import League, NotLoggedIn, NotTeamInLeague
from fantraxapi.exceptions import DateNotInSeason, FantraxException, NotMemberOfLeague, PeriodNotInSeason
from fantraxapi.objs import Trade

"""
import logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())
"""

load_dotenv()

league_id = os.environ["LEAGUE_ID"]
local = os.environ["LOCAL"] == "True"
username = os.environ["FANTRAX_USERNAME"]
password = os.environ["FANTRAX_PASSWORD"]
cookie_filepath = "fantraxloggedin.cookie"
py_version = f"{sys.version_info.major}.{sys.version_info.minor}"

team_names = [
    "Bunch of Yahoos",
    "Pirate Horde",
    "Dude Where’s Makar?",
    "Former Ice Dancers",
    "MacKstreet Boys",
    "Son of a Mich",
    "Kashyyyk Wookies 🏴‍☠️",
    "Momma Ain't Raise No Bitch",
    "Rantanen With The Devil",
    "Maple leaving in the first",
    "Team Will",
    "The Teasiest of McBulges",
]


def add_cookie_to_session(session: Session) -> None:
    if local and os.path.exists(cookie_filepath):
        with open(cookie_filepath, "rb") as f:
            for cookie in pickle.load(f):
                session.cookies.set(cookie["name"], cookie["value"])
    else:
        service = Service(ChromeDriverManager().install())

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--window-size=1920,1600")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36")

        with webdriver.Chrome(service=service, options=options) as driver:
            driver.get("https://www.fantrax.com/login")
            username_box = WebDriverWait(driver, 10).until(expected_conditions.presence_of_element_located((By.XPATH, "//input[@formcontrolname='email']")))
            username_box.send_keys(username)
            password_box = WebDriverWait(driver, 10).until(expected_conditions.presence_of_element_located((By.XPATH, "//input[@formcontrolname='password']")))
            password_box.send_keys(password)
            password_box.send_keys(Keys.ENTER)
            time.sleep(5)

            cookies = driver.get_cookies()
            if local:
                with open(cookie_filepath, "wb") as cookie_file:
                    pickle.dump(driver.get_cookies(), cookie_file)

            for cookie in cookies:
                session.cookies.set(cookie["name"], cookie["value"])


class LiveAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.league = League(league_id)

    def test_info(self) -> None:
        self.assertRaises(FantraxException, League, "jdaffngkjfngjkdf")
        self.assertEqual(self.league.name, "Cowley's Chaos")
        self.assertEqual(self.league.year, "2024-25 NHL")

        self.assertIsInstance(self.league.start_date, datetime)
        self.assertIsInstance(self.league.end_date, datetime)
        self.assertLess(self.league.start_date, self.league.end_date)

        self.assertTrue(self.league.team_lookup)
        for team in self.league.teams:
            self.assertEqual(self.league.team_lookup[team.id], team)

        self.assertTrue(self.league.scoring_periods_lookup)
        self.assertEqual(len(self.league.scoring_periods_lookup), len(self.league.scoring_periods))
        for period in self.league.scoring_periods.values():
            self.assertEqual(self.league.scoring_periods_lookup[period.range], period)
            self.assertLessEqual(period.start, period.end)

    def test_positions(self) -> None:
        self.assertIn("206", self.league.positions)
        self.assertEqual(self.league.positions["206"].name, "Center")
        self.assertEqual(self.league.positions["206"], self.league.positions["206"])
        self.assertNotEqual(self.league.positions["206"], next(p for k, p in self.league.positions.items() if k != "206"))

    def test_status(self) -> None:
        self.assertEqual(self.league.status["3"].name, "Inj Res")
        self.assertEqual(self.league.status["4"].code, "FREE_AGENT")
        self.assertEqual(self.league.status["3"], self.league.status["3"])
        self.assertNotEqual(self.league.status["3"], self.league.status["4"])

    def test_scoring_dates(self) -> None:
        self.assertEqual(len(self.league.scoring_dates), 178)
        values = self.league.scoring_dates.values()
        for day_date in [
            date(year=2024, month=10, day=4),
            date(year=2024, month=10, day=5),
            date(year=2024, month=10, day=8),
            date(year=2024, month=10, day=9),
            date(year=2025, month=4, day=16),
            date(year=2025, month=4, day=17),
        ]:
            self.assertIn(day_date, values)

        self.assertEqual(self.league.scoring_dates[77], date(year=2024, month=12, day=19))
        for day_date in [
            date(year=2024, month=10, day=2),
            date(year=2024, month=10, day=3),
            date(year=2024, month=10, day=6),
            date(year=2024, month=10, day=7),
            date(year=2025, month=4, day=18),
            date(year=2025, month=4, day=19),
        ]:
            self.assertNotIn(day_date, values)

    def test_scoring_periods(self) -> None:
        self.assertEqual(len(self.league.scoring_periods), 25)
        self.assertEqual(str(self.league.scoring_periods[3]), "[3:2024-10-21 - 2024-10-27]")
        self.assertNotEqual(self.league.scoring_periods[8], self.league.scoring_periods[12])
        self.assertEqual(self.league.scoring_periods[9], "9")
        self.assertEqual(self.league.scoring_periods[17], 17)
        self.assertEqual(self.league.scoring_periods[5].start, date(year=2024, month=11, day=4))
        self.assertEqual(self.league.scoring_periods[5].end, date(year=2024, month=11, day=10))
        self.assertEqual(self.league.scoring_periods[13].start, date(year=2024, month=12, day=30))
        self.assertEqual(self.league.scoring_periods[21].end, date(year=2025, month=3, day=16))

        # ScoringPeriod.__eq__ cross-league: same period number but a different league_id must not be equal.
        other_league = SimpleNamespace(league_id="some-other-league-id")
        other_period = SimpleNamespace(league=other_league, number=self.league.scoring_periods[9].number)
        self.assertFalse(self.league.scoring_periods[9].__eq__(other_period))
        same_league_period = SimpleNamespace(league=self.league, number=self.league.scoring_periods[9].number)
        self.assertTrue(self.league.scoring_periods[9].__eq__(same_league_period))
        self.assertFalse(self.league.scoring_periods[9] == 9.5)
        self.assertFalse(self.league.scoring_periods[9] == "not-numeric")

    def test_teams(self) -> None:
        for team in self.league.teams:
            self.assertIn(team.name, team_names)
            self.assertTrue(team.id)
            self.assertTrue(team.short)
            self.assertIsInstance(team.short, str)
            self.assertTrue(team.logo.startswith("http"))
            self.assertEqual(str(team), team.name)
        self.assertRaises(NotTeamInLeague, self.league.team, "NotAProperTeamID")
        self.assertEqual(self.league.team("wookie").name, "Kashyyyk Wookies 🏴‍☠️")

    def test_scoring_period_results(self) -> None:
        results = self.league.scoring_period_results()
        self.assertTrue(len(results) == 25)
        self.assertTrue(results[10].days == 7)
        self.assertTrue(results[19].days == 21)
        self.assertTrue(results[19].matchups[2].winner()[1] == 630.2)
        self.assertTrue(results[19].matchups[2].winner()[3] == 541.4)
        self.assertFalse(results[22].playoffs)
        self.assertTrue(results[23].playoffs)
        self.assertTrue(results[23].days == 7)
        self.assertTrue(results[25].playoffs)
        self.assertTrue(results[25].days == 11)
        self.assertTrue(results[25].matchups[0].winner()[1] == 762.2)
        self.assertTrue(results[25].matchups[0].winner()[3] == 685.5)
        self.assertTrue(str(results[21].matchups[3]) == "Period 21 Bunch of Yahoos (400.0) vs Kashyyyk Wookies 🏴‍☠️ (368.6)")
        self.assertTrue(results[21].matchups[2].difference() == 178.3)
        self.assertTrue(results[21].matchups[3].difference() == 31.4)
        self.assertEqual(
            str(results[25]),
            (
                "Playoffs - Round 3\n"
                "11 Days (Mon Apr 07, 2025 - Thu Apr 17, 2025)\n"
                "Complete\n"
                "Playoff Period 25 Bunch of Yahoos (762.2) vs The Teasiest of McBulges (685.5)\n"
                "3rd Place\n"
                "Playoff Period 25 Kashyyyk Wookies 🏴‍☠️ (835.9) vs Son of a Mich (778.6)\n"
                "7th Place\n"
                "Playoff Period 25 Pirate Horde (535.7) vs Dude Where’s Makar? (432.7)\n"
                "Toilet Bowl\n"
                "Playoff Period 25 MacKstreet Boys (668.9) vs Maple leaving in the first (597.8)"
            ),
        )

        # Structural invariants that must hold for any ScoringPeriodResult, regardless of league/season.
        for number, result in results.items():
            self.assertEqual(result.period.number, number)
            self.assertLessEqual(result.start, result.end)
            self.assertEqual(result.next, result.end + timedelta(days=1))
            self.assertEqual(result.days, (result.next - result.start).days)
            self.assertEqual(result.range, f"{result.start.strftime('%Y-%m-%d')} - {result.end.strftime('%Y-%m-%d')}")
            self.assertEqual(result.title, f"{'Playoff ' if result.playoffs else ''}Period {result.period.number}")
            # Exactly one of complete/current/future must be true.
            self.assertEqual(sum([result.complete, result.current, result.future]), 1)
            self.assertIsInstance(result.complete, bool)
            self.assertIsInstance(result.current, bool)
            self.assertIsInstance(result.future, bool)
            for matchup in result.matchups:
                self.assertIs(matchup.scoring_period, result)
                self.assertIsInstance(matchup.away_score, float)
                self.assertIsInstance(matchup.home_score, float)
                self.assertGreaterEqual(matchup.difference(), 0.0)
                winner, winner_score, loser, loser_score = matchup.winner()
                if winner is None:
                    self.assertEqual(matchup.away_score, matchup.home_score)
                    self.assertEqual(matchup.difference(), 0.0)
                else:
                    self.assertGreaterEqual(winner_score, loser_score)
                    self.assertEqual(matchup.difference(), winner_score - loser_score)
                    self.assertIn(winner, (matchup.away, matchup.home))
                    self.assertIn(loser, (matchup.away, matchup.home))
                    self.assertNotEqual(winner, loser)

    def test_standings(self) -> None:
        standings = self.league.standings()

        self.assertEqual(
            str(standings),
            (
                "Standings\n"
                "1: Kashyyyk Wookies 🏴‍☠️ (18-4-0)\n"
                "2: Bunch of Yahoos (18-4-0)\n"
                "3: Son of a Mich (15-7-0)\n"
                "4: Maple leaving in the first (15-7-0)\n"
                "5: The Teasiest of McBulges (13-9-0)\n"
                "6: MacKstreet Boys (10-12-0)\n"
                "7: Dude Where’s Makar? (10-12-0)\n"
                "8: Pirate Horde (10-12-0)\n"
                "9: Momma Ain't Raise No Bitch (8-14-0)\n"
                "10: Rantanen With The Devil (8-14-0)\n"
                "11: Former Ice Dancers (6-16-0)\n"
                "12: Team Will (1-21-0)"
            ),
        )

        self.assertTrue(standings.ranks[4].points == 30)
        self.assertTrue(standings.ranks[6].team.name == "MacKstreet Boys")
        self.assertTrue(standings.ranks[1].points_for == 10813.2)
        self.assertTrue(str(standings.ranks[6]) == "6: MacKstreet Boys (10-12-0)")

        # Structural/range invariants on Record fields that hold for any league.
        for rank, record in standings.ranks.items():
            self.assertEqual(record.rank, rank)
            self.assertIs(record.standings, standings)
            self.assertIsInstance(record.win, int)
            self.assertIsInstance(record.loss, int)
            self.assertIsInstance(record.tie, int)
            self.assertGreaterEqual(record.win, 0)
            self.assertGreaterEqual(record.loss, 0)
            self.assertGreaterEqual(record.tie, 0)
            self.assertIsInstance(record.win_percentage, float)
            self.assertGreaterEqual(record.win_percentage, 0.0)
            self.assertLessEqual(record.win_percentage, 1.0)
            self.assertIsInstance(record.games_back, int)
            self.assertGreaterEqual(record.games_back, 0)
            self.assertIsInstance(record.wavier_wire_order, int)
            self.assertIsInstance(record.points_for, float)
            self.assertIsInstance(record.points_against, float)
            self.assertGreaterEqual(record.points_for, 0.0)
            self.assertGreaterEqual(record.points_against, 0.0)
            self.assertIsInstance(record.streak, str)
        # The top rank should have the lowest (best, i.e. zero) games-back value.
        self.assertEqual(standings.ranks[1].games_back, 0)

        standings = self.league.standings(scoring_period_number=11)
        self.assertTrue(standings.ranks[7].points == 10)
        self.assertTrue(standings.ranks[3].team.name == "Son of a Mich")
        self.assertTrue(standings.ranks[12].points_for == 3479.8)

        standings = self.league.standings(scoring_period_number=6, only_period=True)
        self.assertTrue(standings.ranks[5].points == 2)
        self.assertTrue(standings.ranks[2].team.name == "Bunch of Yahoos")
        self.assertTrue(standings.ranks[1].points_for == 532.8)

    def test_pending_trades(self) -> None:
        pending_trade = Trade(
            self.league,
            {
                "txSetId": "fdsafdas",
                "creatorTeamId": "er0c60arm15b60vy",
                "usefulInfo": [
                    {"name": "Proposed", "value": "Dec 5, 3:00 AM EDT"},
                    {"name": "Accepted", "value": "Dec 5, 3:00 AM EDT"},
                    {"name": "To be executed", "value": "Dec 5, 3:00 AM EDT"},
                ],
                "moves": [
                    {
                        "draftPick": {"year": 2025, "round": 2, "origOwnerTeam": {"id": "er0c60arm15b60vy"}},
                        "from": {"teamId": "er0c60arm15b60vy"},
                        "to": {"teamId": "e28qwtvwm15b60vy"},
                    },
                    {
                        "draftPick": {"year": 2025, "round": 10, "origOwnerTeam": {"id": "e28qwtvwm15b60vy"}},
                        "from": {"teamId": "e28qwtvwm15b60vy"},
                        "to": {"teamId": "er0c60arm15b60vy"},
                    },
                    {
                        "scorer": {
                            "teamName": "Colorado Avalanche",
                            "scorerId": "02f9l",
                            "posIdsNoFlex": ["206"],
                            "posShortNames": "C",
                            "icons": [],
                            "posIds": ["206", "208"],
                            "name": "Nathan MacKinnon",
                            "teamShortName": "COL",
                            "shortName": "N. MacKinnon",
                        },
                        "scorePerGame": 10.5,
                        "score": 852.5,
                        "from": {"teamId": "e28qwtvwm15b60vy"},
                        "to": {"teamId": "er0c60arm15b60vy"},
                    },
                ],
            },
        )
        self.assertEqual(
            str(pending_trade),
            (
                "From: Kashyyyk Wookies 🏴‍☠️ To: Dude Where’s Makar? Pick: 2025, Round 2 (Kashyyyk Wookies 🏴‍☠️)\n"
                "From: Dude Where’s Makar? To: Kashyyyk Wookies 🏴‍☠️ Pick: 2025, Round 10 (Dude Where’s Makar?)\n"
                "From: Dude Where’s Makar? To: Kashyyyk Wookies 🏴‍☠️ TradePlayer: Nathan MacKinnon C - COL 10.5 852.5"
            ),
        )

        # Trade datetime parsing/ordering: each must be a datetime within the league's season,
        # and proposed <= accepted <= executed must hold for any valid trade.
        for dt in (pending_trade.proposed, pending_trade.accepted, pending_trade.executed):
            self.assertIsInstance(dt, datetime)
            self.assertGreaterEqual(dt, self.league.start_date)
            self.assertLessEqual(dt, self.league.end_date)
        self.assertLessEqual(pending_trade.proposed, pending_trade.accepted)
        self.assertLessEqual(pending_trade.accepted, pending_trade.executed)
        self.assertEqual(pending_trade.proposed_by.id, "er0c60arm15b60vy")

        # _parse_datetime should raise DateNotInSeason for a date entirely outside the season's start/end years.
        out_of_season_trade_data = {
            "txSetId": "fdsafdas2",
            "creatorTeamId": "er0c60arm15b60vy",
            "usefulInfo": [
                {"name": "Proposed", "value": "Jul 4, 3:00 AM EDT"},
                {"name": "Accepted", "value": "Jul 4, 3:00 AM EDT"},
                {"name": "To be executed", "value": "Jul 4, 3:00 AM EDT"},
            ],
            "moves": [],
        }
        self.assertRaises(DateNotInSeason, Trade, self.league, out_of_season_trade_data)

        # TradePlayer/Player injury flags driven by icons[].typeId: with an empty icons list every flag is False.
        trade_player = next(m for m in pending_trade.moves if hasattr(m, "player"))
        self.assertFalse(trade_player.player.day_to_day)
        self.assertFalse(trade_player.player.out)
        self.assertFalse(trade_player.player.injured_reserve)
        self.assertFalse(trade_player.player.suspended)
        self.assertFalse(trade_player.player.injured)
        self.assertEqual(trade_player.player.injured, trade_player.player.day_to_day or trade_player.player.out or trade_player.player.injured_reserve)

    def test_trade_block(self) -> None:
        self.assertRaises(NotLoggedIn, self.league.pending_trades)
        self.assertRaises(NotLoggedIn, self.league.trade_block)
        add_cookie_to_session(self.league.session)
        trade_block = self.league.trade_block()
        self.assertEqual(
            str(trade_block),
            (
                "[Looking to swap a 9th rd pick and trade up in the next draft\n"
                "Barkov +9th for a 5th\n"
                "Zbad +9th for a 5th\n"
                "Breadman +9th for an 8th, I’d be willing to let these guys go for the right picks, Looking for picks., "
                "Looking to add a producing winger, send dem picks, These players are keepers for next 10 years, draft pics send them!]"
            ),
        )
        self.assertEqual(str(trade_block[1]), "I’d be willing to let these guys go for the right picks")
        self.assertEqual(str(trade_block[1]), "I’d be willing to let these guys go for the right picks")
        self.assertEqual(len(trade_block[4].players_offered), 2)
        self.assertIn("C", trade_block[4].players_offered)
        self.assertIn("D", trade_block[4].players_offered)
        self.assertEqual(len(trade_block[4].players_offered["C"]), 3)
        self.assertEqual(len(trade_block[4].players_offered["D"]), 1)
        self.assertEqual(len(trade_block[4].positions_wanted), 0)
        self.assertEqual(len(trade_block[5].players_offered), 0)
        self.assertEqual(len(trade_block[5].positions_wanted), 2)

        league = League("fdutr5ehmgr5bjm6")
        add_cookie_to_session(league.session)
        self.assertRaises(NotMemberOfLeague, league.trade_block)

    def test_transactions(self) -> None:
        transactions = self.league.transactions(count=160)
        self.assertTrue(len(transactions) == 160)
        self.assertTrue(len(transactions[147].players) == 2)
        self.assertTrue(transactions[147].players[0].type == "WW")
        self.assertTrue(transactions[147].players[0].name == "Pavel Dorofeyev")
        self.assertTrue(transactions[147].players[1].type == "DROP")
        self.assertTrue(transactions[147].players[1].name == "Owen Tippett")
        self.assertTrue(len(transactions[83].players) == 1)
        self.assertTrue(transactions[83].players[0].type == "DROP")
        self.assertTrue(transactions[83].players[0].name == "Brock Faber")
        self.assertTrue(len(transactions[46].players) == 2)
        self.assertTrue(transactions[46].players[0].type == "FA")
        self.assertTrue(transactions[46].players[0].name == "Filip Hronek")
        self.assertTrue(transactions[46].players[1].type == "DROP")
        self.assertTrue(transactions[46].players[1].name == "Ryan Leonard")

        # Structural invariants for Transaction/TransactionPlayer that hold for any league/data.
        for transaction in transactions:
            self.assertTrue(transaction.id)
            self.assertIsInstance(transaction.team, type(self.league.teams[0]))
            self.assertIsInstance(transaction.date, datetime)
            self.assertEqual(str(transaction), str(transaction.players))
            for player in transaction.players:
                self.assertTrue(player.type)
                self.assertEqual(str(player), f"{player.type} {player.name}")
                self.assertIsInstance(player.day_to_day, bool)
                self.assertIsInstance(player.out, bool)
                self.assertIsInstance(player.injured_reserve, bool)
                self.assertIsInstance(player.suspended, bool)
                self.assertIsInstance(player.injured, bool)
                self.assertEqual(player.injured, player.day_to_day or player.out or player.injured_reserve)
                self.assertTrue(player.positions)
                self.assertTrue(player.all_positions)

    def test_position_counts(self) -> None:
        team = self.league.team("wookie")
        counts = team.position_counts()
        for position in ["W", "C", "D", "TmG"]:
            self.assertIn(position, counts)
        self.assertTrue(counts["C"].gp == 17)
        self.assertIsNone(counts["W"].min)
        self.assertIsNone(counts["D"].max)
        self.assertTrue(counts["TmG"].gp == 8)
        self.assertTrue(counts["TmG"].max == 7)
        counts = team.position_counts(11)
        self.assertTrue(counts["C"].gp == 7)
        self.assertIsNone(counts["W"].min)
        self.assertIsNone(counts["D"].max)
        self.assertTrue(counts["TmG"].gp == 4)
        self.assertTrue(counts["TmG"].max == 4)

    def test_live_scores(self) -> None:
        team = self.league.team("wookie")
        scoring_date = date(year=2024, month=10, day=18)
        scores = team.live_scores(scoring_date)
        self.assertEqual(str(scores), "[Anthony Beauvillier, Samuel Girard]")
        self.assertEqual(scores[0].name, "Anthony Beauvillier")
        self.assertEqual(scores[1].points, 7.0)
        self.assertRaises(DateNotInSeason, team.live_scores, date(year=2024, month=10, day=6))
        self.assertRaises(DateNotInSeason, team.live_scores, date(year=2024, month=7, day=18))

        # LivePlayer-specific attributes: points_date matches the queried date and team is resolved.
        for player in scores:
            self.assertEqual(player.points_date, scoring_date)
            self.assertEqual(player.team, team)
            self.assertIsInstance(player.points, float)
            self.assertIsInstance(player.injured, bool)
            self.assertEqual(player.injured, player.day_to_day or player.out or player.injured_reserve)

    def test_team_roster(self) -> None:
        team = self.league.team("wookie")
        self.assertRaises(PeriodNotInSeason, team.roster, 500)
        roster = team.roster(8)
        self.assertEqual(
            str(roster),
            (
                "Kashyyyk Wookies 🏴‍☠️ Roster\n"
                "C: Joel Eriksson Ek\n"
                "C: Jack Hughes\n"
                "W: Jake Guentzel\n"
                "W: David Pastrnak\n"
                "W: Mark Stone\n"
                "W: Alex Tuch\n"
                "D: Adam Fox\n"
                "D: Seth Jones\n"
                "D: Alec Martinez\n"
                "D: Empty\n"
                "Skt: Tomas Hertl\n"
                "C: Josh Norris\n"
                "W: Viktor Arvidsson\n"
                "W: Andrei Kuzmenko\n"
                "W: Tom Wilson\n"
                "D: Darnell Nurse\n"
                "D: Alexander Romanov\n"
                "C: Boone Jenner\n"
                "TmG: Vegas\n"
                "TmG: Nashville"
            ),
        )
        self.assertEqual(roster.active, 11)
        self.assertEqual(roster.active_max, 12)
        self.assertEqual(roster.reserve, 7)
        self.assertEqual(roster.reserve_max, 18)
        self.assertEqual(roster.injured, 1)
        self.assertEqual(roster.injured_max, 3)
        self.assertEqual(str(roster.rows[1].position), "[206:Center:C]")
        self.assertEqual(str(roster.rows[1].player), "Jack Hughes")
        self.assertEqual(roster.rows[1].total_fantasy_points, 21.8)
        self.assertIsNone(roster.rows[1].game_today)
        self.assertEqual(str(roster.rows[2].player), "Jake Guentzel")
        self.assertEqual(roster.rows[2].total_fantasy_points, 14.7)
        self.assertEqual(str(roster.rows[2].game_today), "[062yw:CAR @TBL]")
        self.assertIn("Thu 4/17", roster.rows[2].future_games)
        self.assertEqual(str(roster.rows[2].future_games["Thu 4/17"]), "[063yr:NYR @TBL]")

        # Structural invariants for RosterRow/Game/Position that hold for any roster.
        for row in roster.rows:
            self.assertIs(row.roster, roster)
            self.assertIsInstance(row.position, type(roster.rows[1].position))
            self.assertEqual(row.position, row.position)
            if row.player is None:
                self.assertEqual(str(row), f"{row.position.short_name}: Empty")
            else:
                self.assertEqual(str(row), f"{row.position.short_name}: {row.player}")

            games = ([row.game_today] if row.game_today else []) + list(row.future_games.values())
            for game in games:
                self.assertTrue(game.id)
                self.assertIs(game.player, row.player)
                self.assertNotEqual(game.home, game.away)
                self.assertTrue(game.opponent)
                self.assertIsInstance(game.date, date)
                self.assertGreaterEqual(game.date, self.league.start_date.date())
                self.assertLessEqual(game.date, self.league.end_date.date())
                self.assertNotEqual(game.opponent, row.player.team_short_name)
                self.assertEqual(game, game)
                self.assertEqual(
                    str(game),
                    f"[{game.id}:{f'{game.opponent} @{game.player.team_short_name}' if game.home else f'{game.player.team_short_name} @{game.opponent}'}{f' {game.time}' if game.time else ''}]",
                )
