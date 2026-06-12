from typing import TYPE_CHECKING

from .base import FantraxBaseObject
from .team import Team

if TYPE_CHECKING:
    from .league import League


class Standings(FantraxBaseObject):
    """Represents a single Standings.

    Attributes:
        league (League): The League instance this object belongs to.
        scoring_period_number (int): Period Number.
        ranks (dict[int, Record]): Team Ranks and their Records.

    """

    def __init__(self, league: "League", data: dict, scoring_period_number: int | None = None) -> None:
        super().__init__(league, data)
        self.scoring_period_number: int | None = scoring_period_number
        self.ranks: dict[int, Record] = {}
        fields = {c["key"]: i for i, c in enumerate(self._data["header"]["cells"])}
        for obj in self._data["rows"]:
            team_id = obj["fixedCells"][1]["teamId"]
            rank = int(obj["fixedCells"][0]["content"])
            self.ranks[rank] = Record(self, team_id, rank, fields, obj["cells"])

    def __str__(self) -> str:
        output = "Standings"
        if self.scoring_period_number:
            output += f" Period {self.scoring_period_number}"
        for rank, record in self.ranks.items():
            output += f"\n{record}"
        return output


class Record(FantraxBaseObject):
    """Represents a single Record of a Standings.

    Attributes:
        league (League): The League instance this object belongs to.
        standings (Standings): The Standings instance this Record belongs to.
        team (Team): Team.
        rank (int): Standings Rank.
        win (int): Number of Wins.
        loss (int): Number of Losses.
        tie (int): Number of Ties.
        points (int): Number of Points.
        win_percentage (float): Win Percentage.
        games_back (float): Number of Games Back.
        wavier_wire_order (int): Wavier Wire Claim Order.
        points_for (float): Fantasy Points For.
        points_against (float): Fantasy Points Against.
        streak (str): Streak.

    """

    def __init__(self, standings: Standings, team_id: str, rank: int, fields: dict, data: dict) -> None:
        super().__init__(standings.league, data)
        self.standings: Standings = standings
        self.team: Team = self.league.team(team_id)
        self.rank: int = rank
        def content(*keys: str) -> str | None:
            # Column keys vary by league: e.g. games back / fantasy points for / against
            # arrive as gamesback/pointsFor/pointsAgainst in some leagues and gb/cpf/cpa in others.
            return next((self._data[fields[key]]["content"] for key in keys if key in fields), None)

        self.win: int = int(content("win") or 0)
        self.loss: int = int(content("loss") or 0)
        self.tie: int = int(content("tie") or 0)
        self.points: int = int(content("points") or 0)
        winpc_raw = content("winpc")
        self.win_percentage: float = float(winpc_raw) if winpc_raw and winpc_raw != "-" else 0.0
        gb_raw = content("gamesback", "gb")
        self.games_back: float = float(gb_raw) if gb_raw and gb_raw != "-" else 0.0
        self.wavier_wire_order: int = int(content("wwOrder") or 0)
        pf_raw = content("pointsFor", "cpf")
        self.points_for: float = float(pf_raw.replace(",", "")) if pf_raw else 0.0
        pa_raw = content("pointsAgainst", "cpa")
        self.points_against: float = float(pa_raw.replace(",", "")) if pa_raw else 0.0
        self.streak: str = content("streak") or ""

    def __str__(self) -> str:
        return f"{self.rank}: {self.team} ({self.win}-{self.loss}-{self.tie})"
