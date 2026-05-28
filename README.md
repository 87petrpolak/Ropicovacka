# Ropičovačka 2026 — World Cup Fantasy Draft

A lightweight Streamlit web app for running a fantasy draft game on top of the FIFA World Cup 2026.

---

## Setup

### Requirements

- Python 3.11+
- pip

### Install

```bash
pip install -r requirements.txt
```

### Run

```bash
streamlit run main.py
```

The app opens at `http://localhost:8501`. A SQLite database (`ropicovacka.db`) is created automatically in the working directory.

To use a different database path:

```bash
ROPICOVACKA_DB=/path/to/game.db streamlit run main.py
```

### Tests

```bash
pytest
```

---

## Quick start

1. **Home** — create a new game (e.g. "Friends Draft 2026").
2. **Participants** — add each player (name, optional email, draft order).
3. **Players** — import the player pool via CSV (see format below).
4. **Draft Room** — start a draft session and run the snake draft.
5. **Admin** — create tournament rounds and set lineup deadlines.
6. **Lineup Nomination** — before each round, each participant picks their 11.
7. **Match Stats Import** — upload match results and player stats after each round.
8. **Leaderboard** — see standings overall and per round.

---

## Rules

### Squad
Each participant drafts **18 players**: 11 starters + 7 substitutes.

### Starting lineup constraints
| Position | Count |
|----------|-------|
| Goalkeeper | Exactly 1 |
| Defenders | 3–5 |
| Midfielders | 3–5 |
| Forwards | 1–3 |

### Draft
- Snake draft — pick order reverses every round
- Each player can only be drafted once
- No transfers during the tournament

### Lineup nomination
- Before each round, each participant nominates 11 players from their 18-player squad
- Only nominated players score points — no automatic substitutions
- Lineups lock at a configurable deadline

### Scoring
| Event | Positions | Points |
|-------|-----------|--------|
| Goal | All | 25 |
| Assist | All | 20 |
| Team win | All | 10 |
| Clean sheet | Goalkeeper | 25 |
| Clean sheet | Defender | 10 |

---

## CSV formats

### players.csv

```csv
name,country,position,club,external_id
Kylian Mbappé,France,FWD,Real Madrid,fr_mbappe
Mike Maignan,France,GK,AC Milan,fr_maignan
William Saliba,France,DEF,Arsenal,fr_saliba
Antoine Griezmann,France,MID,Atlético Madrid,fr_griezmann
```

- `position`: one of `GK`, `DEF`, `MID`, `FWD`
- `club` and `external_id` are optional
- `external_id` is used to avoid duplicates on re-import

### matches.csv

```csv
home_team,away_team,home_score,away_score,played_at,external_id,round_name,round_number,is_finished
France,Argentina,2,1,2026-06-15 18:00,match_001,Group Stage MD1,1,true
```

- `played_at`: `YYYY-MM-DD` or `YYYY-MM-DD HH:MM`
- `external_id` deduplicates on re-import
- `is_finished`: `true` or `false` (default `true`)

### stats.csv

```csv
player_name,player_external_id,match_external_id,goals,assists,played,team_won,clean_sheet
Kylian Mbappé,fr_mbappe,match_001,1,1,true,true,false
```

- `match_external_id` must match a value in `matches.csv`
- `player_external_id` is optional but improves matching accuracy
- `played`, `team_won`, `clean_sheet`: `true` or `false`

Sample files live in [`data/samples/`](data/samples/).

---

## Data model

| Table | Description |
|-------|-------------|
| `games` | One game per tournament run |
| `participants` | Players in the game |
| `football_players` | Real-world players available for drafting |
| `draft_sessions` | A draft run for a game |
| `draft_picks` | Individual picks in a draft session |
| `rounds` | Tournament rounds (group stage, R16, …) |
| `matches` | Match results |
| `player_match_stats` | Per-player stats for each match |
| `lineup_nominations` | A participant's nominated 11 for a given round |
| `lineup_slots` | Individual player slots within a nomination |
| `points_rules` | Configurable scoring rules per game |
| `data_refresh_logs` | Audit log of every data import |

---

## Data providers

The app uses a pluggable `BaseFootballDataProvider` interface:

- **`CsvFootballDataProvider`** — reads from CSV files (fully implemented, used in MVP)
- **`LivesportFootballDataProvider`** — stub placeholder for future HTML scraping

> **Note on Livesport scraping:** If implemented, HTML scraping is fragile and subject to terms of service, rate limiting, IP blocks, and HTML structure changes. Prefer an official football data API (e.g. football-data.org, API-Football) when available.

### Adding a new provider

Implement the three abstract methods in `BaseFootballDataProvider`:

```python
class MyProvider(BaseFootballDataProvider):
    def fetch_players(self) -> list[PlayerData]: ...
    def fetch_matches(self, since=None) -> list[MatchData]: ...
    def fetch_player_stats(self, match_external_id: str) -> list[PlayerStatsData]: ...
```

Then pass an instance to `run_refresh(db, provider, game_id)`.

---

## Project structure

```
main.py                     # Streamlit entrypoint
requirements.txt
app/
  db.py                     # SQLAlchemy engine + Base
  state.py                  # Streamlit session-state helpers
  models/
    models.py               # All ORM models
  pages/
    home.py
    participants.py
    players.py
    draft_room.py
    squads.py
    lineup.py
    match_import.py
    data_refresh.py
    leaderboard.py
    rules.py
    admin.py
  services/
    scoring.py              # compute_points logic
    squad_validator.py      # Squad and lineup validation
    draft_engine.py         # Snake draft logic
    lineup_manager.py       # Lineup nomination management
    leaderboard.py          # Leaderboard computation
    data_refresh.py         # Idempotent data ingestion
  providers/
    base.py                 # Abstract provider interface
    csv_provider.py         # CSV-based provider
    livesport_provider.py   # Stub for Livesport scraping
tests/
  test_scoring.py
  test_squad_validator.py
  test_draft_engine.py
data/
  samples/
    players.csv
    matches.csv
    stats.csv
```

---

## Future roadmap

- Live data connector (football-data.org or API-Football)
- Knockout round point multipliers (1.2× R16 … 2× Final)
- Team bonuses (World Cup winner +30, finalist +20, bronze +10)
- Individual award bonuses (Golden Boot, Golden Ball, etc.)
- Optional limited transfers (e.g. 2 after group stage)
- Countdown timer for lineup deadlines
- Public read-only leaderboard URL
- Deploy to Streamlit Community Cloud / Railway / Render
