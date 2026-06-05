"""
Livesport.cz / Flashscore scraper.

Používá interní Flashscore API (flashscore.ninja) s proprietárním
¬-odděleným formátem. Token x-fsign je statický, uložený v jejich JS.

Endpointy:
  f_1_0_2_cs_1          — dnešní/aktuální výsledky všech fotbalových zápasů
  dc_1_{matchId}         — metadata zápasu (skóre, čas, týmy)
  df_sui_1_{matchId}     — incidents: góly, asistence, střídání, karty

Minuty na hřišti:
  Nastoupil od začátku = 90 min (pokud nebyl střídán ven)
  Střídán ven v min X  = X minut
  Střídán dovnitř v min X = (90 - X) minut
  Nastoupil od začátku ale střídán dovnitř/ven = kombinace
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

import requests

from app.providers.base import BaseFootballDataProvider, PlayerData, MatchData, PlayerStatsData

_BASE = "https://1.flashscore.ninja/1/x/feed"
_HEADERS = {
    "x-fsign": "SW9D1eZo",
    "Referer": "https://www.livesport.cz/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}
_REQUEST_DELAY = 1.0  # sekundy mezi requesty

# Flashscore tournament ID pro MS 2026
WC_2026_TOURNAMENT_ID = "zeSHfCx3"

# Typy incidentů v df_sui feedu
_INCIDENT_GOAL = "Gól"
_INCIDENT_OWN_GOAL = "Vlastní gól"
_INCIDENT_SUB_IN = "Střídání"
_INCIDENT_SUB_OUT = "Střídání - Out"


def _fetch(path: str) -> str:
    url = f"{_BASE}/{path}"
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    time.sleep(_REQUEST_DELAY)
    return resp.text


def _parse_feed(raw: str) -> list[dict]:
    """Parsuje ¬-oddělený Flashscore formát do seznamu slovníků."""
    records = []
    for block in raw.split("~"):
        block = block.strip()
        if not block:
            continue
        record: dict[str, str] = {}
        for pair in block.split("¬"):
            if "÷" in pair:
                key, _, val = pair.partition("÷")
                record[key] = val
        if record:
            records.append(record)
    return records


def _parse_minute(minute_str: str) -> int:
    """'75'' → 75, '90+2'' → 92, '45+3'' → 48"""
    s = minute_str.replace("'", "").strip()
    if "+" in s:
        base, extra = s.split("+", 1)
        try:
            return int(base) + int(extra)
        except ValueError:
            pass
    try:
        return int(s)
    except ValueError:
        return 0


class LivesportProvider(BaseFootballDataProvider):
    """
    Scraper pro livesport.cz (Flashscore backend).

    tournament_id: Flashscore ID turnaje (default = MS 2026)
    """

    def __init__(
        self,
        tournament_id: str = WC_2026_TOURNAMENT_ID,
        request_delay: float = _REQUEST_DELAY,
    ):
        self.tournament_id = tournament_id
        _HEADERS  # použito globálně, delay se aplikuje v _fetch

    def fetch_players(self) -> list[PlayerData]:
        # Hráče importujeme přes CSV — Flashscore nemá roster endpoint v free feedu
        return []

    def fetch_matches(self, since: Optional[datetime] = None) -> list[MatchData]:
        """
        Vrátí dokončené zápasy turnaje.

        Flashscore obecný feed (f_1_0_2_cs_1) obsahuje všechny dnešní výsledky.
        Pro historická data nebo konkrétní turnaj musíme filtrovat přes tournament feed.
        """
        raw = _fetch("f_1_0_2_cs_1")
        records = _parse_feed(raw)

        matches = []
        current_tournament_id = None

        for rec in records:
            # ZEE = tournament external ID (začátek sekce turnaje)
            if "ZEE" in rec:
                current_tournament_id = rec.get("ZEE", "")
                continue

            # AA = match ID (zápasový záznam)
            if "AA" not in rec:
                continue

            # Filtrujeme jen náš turnaj, pokud je nastaven
            if self.tournament_id and current_tournament_id != self.tournament_id:
                continue

            # AB÷3 = zápas dokončen
            if rec.get("AB") != "3":
                continue

            played_at = None
            raw_ts = rec.get("AD", "")
            if raw_ts:
                try:
                    played_at = datetime.utcfromtimestamp(int(raw_ts))
                except (ValueError, OSError):
                    pass

            if since and played_at and played_at <= since:
                continue

            home_score = int(rec.get("AG", 0) or 0)
            away_score = int(rec.get("AH", 0) or 0)

            matches.append(MatchData(
                home_team=rec.get("AE", ""),
                away_team=rec.get("AF", ""),
                home_score=home_score,
                away_score=away_score,
                played_at=played_at,
                external_id=rec["AA"],
                is_finished=True,
            ))

        return matches

    def fetch_player_stats(self, match_external_id: str) -> list[PlayerStatsData]:
        """
        Načte góly, asistence a minuty na hřišti pro daný zápas.
        Vrací záznamy jen pro hráče kteří skórovali, nahrávali nebo byli střídáni.
        Hráči co odehráli celý zápas bez incidentů zde nebudou — je potřeba je doplnit
        ze sestavy (CSV import).
        """
        # Nejdřív metadata zápasu (skóre pro výhru/čisté konto)
        dc_raw = _fetch(f"dc_1_{match_external_id}")
        dc = _parse_feed(dc_raw)
        match_meta = dc[0] if dc else {}

        home_score = int(match_meta.get("DG", 0) or 0)
        away_score = int(match_meta.get("DH", 0) or 0)

        # Incidents feed
        raw = _fetch(f"df_sui_1_{match_external_id}")
        records = _parse_feed(raw)

        # IA÷1 = domácí tým, IA÷2 = hosté
        home_won = home_score > away_score
        away_won = away_score > home_score
        home_clean = away_score == 0
        away_clean = home_score == 0

        # Sbíráme data per hráč (player_url jako klíč)
        players: dict[str, dict] = {}

        # Sledujeme sekci poločasu (AC = poločas header)
        current_section = None
        match_duration = 90  # základní hrací doba

        for rec in records:
            if "AC" in rec:
                current_section = rec["AC"]
                continue

            if "III" not in rec:
                continue

            incident_type = rec.get("IK", "")
            team_side = rec.get("IA", "")  # "1" = domácí, "2" = hosté
            player_name = rec.get("IF", "").strip()
            player_url = rec.get("IU", "").strip()
            player_id = rec.get("IM", "").strip()
            minute = _parse_minute(rec.get("IB", "0"))

            if not player_name:
                continue

            key = player_url or player_name
            if key not in players:
                team_won = (team_side == "1" and home_won) or (team_side == "2" and away_won)
                clean_sheet = (team_side == "1" and home_clean) or (team_side == "2" and away_clean)
                players[key] = {
                    "player_external_id": player_id or None,
                    "player_name": player_name,
                    "match_external_id": match_external_id,
                    "goals": 0,
                    "assists": 0,
                    "played": True,
                    "minutes_played": match_duration,  # default = celý zápas, upravíme při střídání
                    "team_won": team_won,
                    "clean_sheet": clean_sheet,
                    "_sub_out_minute": None,
                    "_sub_in_minute": None,
                    "_team_side": team_side,
                }

            p = players[key]

            if incident_type == _INCIDENT_GOAL:
                p["goals"] += 1

            elif incident_type == "Asistace" or (incident_type == _INCIDENT_GOAL and rec.get("INX")):
                # Asistence může být jako samostatný záznam nebo inline v gólu
                # INX přítomný = asistující hráč je v dalším záznamu
                pass

            elif incident_type == _INCIDENT_SUB_OUT:
                p["_sub_out_minute"] = minute
                p["minutes_played"] = minute

            elif incident_type == _INCIDENT_SUB_IN:
                p["_sub_in_minute"] = minute
                p["minutes_played"] = match_duration - minute
                p["played"] = True

        # Druhý průchod pro asistence — jsou linkované s gólem přes INX/IOX
        # Ve feedu je asistující hráč ve vedlejším záznamu (IE÷ a IF÷ v rámci téhož bloku)
        raw2 = _fetch(f"df_sui_1_{match_external_id}")
        self._parse_assists(raw2, players, match_external_id, home_won, away_won, home_clean, away_clean, match_duration)

        return [
            PlayerStatsData(
                player_external_id=p["player_external_id"],
                player_name=p["player_name"],
                match_external_id=p["match_external_id"],
                goals=p["goals"],
                assists=p["assists"],
                played=p["played"],
                minutes_played=p["minutes_played"],
                team_won=p["team_won"],
                clean_sheet=p["clean_sheet"],
            )
            for p in players.values()
        ]

    def _parse_assists(
        self,
        raw: str,
        players: dict,
        match_external_id: str,
        home_won: bool,
        away_won: bool,
        home_clean: bool,
        away_clean: bool,
        match_duration: int,
    ) -> None:
        """
        Ve Flashscore feedu jsou asistence zakódovány takto v gólové události:
          IE÷3¬INX÷1¬IOX÷0¬IF÷<střelec>¬IU÷<url>¬ICT÷¬IK÷Gól¬IM÷<id>
          IE÷... (druhý výskyt IF) = asistující hráč
        Přesněji: blok obsahuje opakující se IF÷/IU÷/IK÷ páry pro střelce i asistenta.
        Parsujeme raw znovu, tentokrát extrahujeme asistenta z gólového bloku.
        """
        for block in raw.split("~"):
            if "IK÷Gól" not in block and "IK÷gól" not in block.lower():
                continue

            pairs = block.split("¬")
            team_side = ""
            ie_entries: list[tuple[str, str, str, str]] = []  # (IE, IF, IU, IK)

            i = 0
            current_ie = ""
            current_if = ""
            current_iu = ""
            current_im = ""
            current_ik = ""

            for pair in pairs:
                if "÷" not in pair:
                    continue
                k, _, v = pair.partition("÷")
                if k == "IA":
                    team_side = v
                elif k == "IE":
                    # Nový hráč v bloku — ulož předchozího
                    if current_if:
                        ie_entries.append((current_ie, current_if, current_iu, current_im, current_ik))
                    current_ie = v
                    current_if = ""
                    current_iu = ""
                    current_im = ""
                    current_ik = ""
                elif k == "IF":
                    current_if = v.strip()
                elif k == "IU":
                    current_iu = v.strip()
                elif k == "IM":
                    current_im = v.strip()
                elif k == "IK":
                    current_ik = v.strip()

            if current_if:
                ie_entries.append((current_ie, current_if, current_iu, current_im, current_ik))

            # ie_entries[0] = střelec (IK=Gól), ie_entries[1] = asistent (IK=Asistace nebo prázdný)
            for ie, name, url, pid, ik in ie_entries:
                if ik in ("Asistace", "Asistence", "") and name:
                    key = url or name
                    if key not in players:
                        team_won = (team_side == "1" and home_won) or (team_side == "2" and away_won)
                        clean_sheet = (team_side == "1" and home_clean) or (team_side == "2" and away_clean)
                        players[key] = {
                            "player_external_id": pid or None,
                            "player_name": name,
                            "match_external_id": match_external_id,
                            "goals": 0,
                            "assists": 0,
                            "played": True,
                            "minutes_played": match_duration,
                            "team_won": team_won,
                            "clean_sheet": clean_sheet,
                            "_sub_out_minute": None,
                            "_sub_in_minute": None,
                            "_team_side": team_side,
                        }
                    players[key]["assists"] += 1
