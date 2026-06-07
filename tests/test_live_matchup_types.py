"""Live tests that verify matchup parsing across (sport, matchup_type) combinations.

Fantrax leagues vary along two axes that affect how scoring period results are
parsed: the sport (NHL, NBA, ...) and the head-to-head matchup_type/tableType
(H2hRotisserie2, H2hPointsBased3, ...). Each combination is supplied via its own
LEAGUE_ID_<SPORT>_<MATCHUP_TYPE> env var (see .env). Combinations without a
configured league ID are skipped -- fill one in once a real league for that
combination is found.

These tests only need a public league ID, not login credentials, so they're kept
separate from the heavier, login-driven tests in test_live_api.py.
"""

import os
import unittest

from dotenv import load_dotenv

from fantraxapi import League
from fantraxapi.objs.scoring_period import H2HRotisserie2, H2hPointsBased3

load_dotenv()

# (sport, matchup_type) -> (env var holding the league ID, expected Matchup subclass)
COMBINATIONS = {
    ("NBA", "H2hRotisserie2"): ("LEAGUE_ID_NBA_H2HROTISSERIE2", H2HRotisserie2),
    ("NBA", "H2hPointsBased3"): ("LEAGUE_ID_NBA_H2HPOINTSBASED3", H2hPointsBased3),
    ("NHL", "H2hRotisserie2"): ("LEAGUE_ID_NHL_H2HROTISSERIE2", H2HRotisserie2),
    ("NHL", "H2hPointsBased3"): ("LEAGUE_ID_NHL_H2HPOINTSBASED3", H2hPointsBased3),
}


class MatchupTypeTests(unittest.TestCase):
    def test_combinations(self) -> None:
        configured = [
            (sport, matchup_type, os.environ[env_var], matchup_cls)
            for (sport, matchup_type), (env_var, matchup_cls) in COMBINATIONS.items()
            if os.environ.get(env_var)
        ]
        if not configured:
            self.skipTest("No LEAGUE_ID_<SPORT>_<MATCHUP_TYPE> env vars configured")

        for sport, matchup_type, league_id, matchup_cls in configured:
            with self.subTest(sport=sport, matchup_type=matchup_type):
                league = League(league_id)
                self.assertIn(sport, league.year)

                results = league.scoring_period_results(playoffs=False)
                self.assertTrue(results)
                for result in results.values():
                    self.assertEqual(result.matchup_type, matchup_type)
                    self.assertTrue(result.matchups)
                    for matchup in result.matchups.values():
                        self.assertIsInstance(matchup, matchup_cls)
                        self.assertIsInstance(matchup.away_score, float)
                        self.assertIsInstance(matchup.home_score, float)
