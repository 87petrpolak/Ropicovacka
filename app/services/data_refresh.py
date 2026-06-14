"""Ingests data from a provider into the DB. Idempotent."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.providers.base import BaseFootballDataProvider, RefreshResult
from app.models.models import (
    FootballPlayer, Match, PlayerMatchStats, Round, DataRefreshLog,
    Position
)
from app.services.scoring import compute_points


def run_refresh(
    db: Session,
    provider: BaseFootballDataProvider,
    game_id: int,
    import_players: bool = True,
    import_matches: bool = True,
) -> RefreshResult:
    result = RefreshResult()
    last_match_id = None

    try:
        if import_players:
            _import_players(db, provider, result)

        if import_matches:
            matches_data = provider.fetch_matches()
            for md in matches_data:
                match = _upsert_match(db, md, game_id, result)
                if match is None:
                    continue
                last_match_id = match.external_id or str(match.id)
                if md.external_id:
                    # Přeskoč stats pro dokončené zápasy které už mají statistiky v DB
                    already_has_stats = (
                        match.is_finished and
                        db.query(PlayerMatchStats).filter(
                            PlayerMatchStats.match_id == match.id
                        ).first() is not None
                    )
                    if not already_has_stats:
                        stats_data = provider.fetch_player_stats(md.external_id)
                        for sd in stats_data:
                            _upsert_stats(db, sd, match, result)
                        _recompute_match_points(db, match, game_id)

        db.commit()
    except Exception as e:
        db.rollback()
        result.errors.append(str(e))

    log = DataRefreshLog(
        provider=type(provider).__name__,
        records_added=result.records_added,
        records_updated=result.records_updated,
        records_skipped=0,
        last_match_external_id=last_match_id,
        notes="; ".join(result.errors) if result.errors else None,
        success=len(result.errors) == 0,
    )
    db.add(log)
    db.commit()

    return result


def _import_players(db: Session, provider: BaseFootballDataProvider, result: RefreshResult):
    players_data = provider.fetch_players()
    for pd in players_data:
        existing = None
        if pd.external_id:
            existing = db.query(FootballPlayer).filter(
                FootballPlayer.external_id == pd.external_id
            ).first()
        if existing is None:
            existing = db.query(FootballPlayer).filter(
                FootballPlayer.name == pd.name,
                FootballPlayer.country == pd.country,
            ).first()

        if existing is None:
            db.add(FootballPlayer(
                name=pd.name,
                country=pd.country,
                position=pd.position,
                club=pd.club,
                external_id=pd.external_id,
            ))
            result.players_added += 1


def _upsert_match(db: Session, md, game_id: int, result: RefreshResult):
    match = None
    if md.external_id:
        match = db.query(Match).filter(Match.external_id == md.external_id).first()

    round_ = None
    if md.round_name or md.round_number is not None:
        round_ = _get_or_create_round(db, game_id, md.round_name, md.round_number)

    if match is None:
        match = Match(
            game_id=game_id,
            home_team=md.home_team,
            away_team=md.away_team,
            home_score=md.home_score,
            away_score=md.away_score,
            played_at=md.played_at,
            external_id=md.external_id,
            is_finished=md.is_finished,
            round_id=round_.id if round_ else None,
        )
        db.add(match)
        db.flush()
        result.matches_added += 1
    else:
        match.home_score = md.home_score
        match.away_score = md.away_score
        match.is_finished = md.is_finished
        if round_:
            match.round_id = round_.id
        result.matches_updated += 1

    # Auto-přiřaď kolo podle pořadí zápasů týmu (1. zápas → Kolo 1 atd.)
    if not match.round_id:
        _assign_round_by_team_order(db, game_id, match)

    return match


def _assign_round_by_team_order(db: Session, game_id: int, match: Match) -> None:
    """
    Přiřadí zápas ke kolu podle toho, kolikátý zápas tým hraje.
    1. zápas týmu → Kolo 1, 2. zápas → Kolo 2, atd.
    Kolo musí v DB existovat (vytvoříš ho v Administraci).
    """
    if not match.home_team or not match.played_at:
        return

    # Kolik předchozích zápasů home_team odehrál (před tímto zápasem)?
    prev_count = db.query(Match).filter(
        Match.game_id == game_id,
        Match.id != match.id,
        or_(
            Match.home_team == match.home_team,
            Match.away_team == match.home_team,
        ),
        Match.played_at < match.played_at,
    ).count()

    round_number = prev_count + 1

    round_ = db.query(Round).filter(
        Round.game_id == game_id,
        Round.round_number == round_number,
    ).first()

    if round_:
        match.round_id = round_.id


def _upsert_stats(db: Session, sd, match: Match, result: RefreshResult):
    player = None
    if sd.player_external_id:
        player = db.query(FootballPlayer).filter(
            FootballPlayer.external_id == sd.player_external_id
        ).first()
    if player is None:
        player = db.query(FootballPlayer).filter(
            FootballPlayer.name == sd.player_name
        ).first()
    if player is None:
        result.errors.append(f"Player not found: {sd.player_name}")
        return

    existing = db.query(PlayerMatchStats).filter(
        PlayerMatchStats.match_id == match.id,
        PlayerMatchStats.player_id == player.id,
    ).first()

    if existing is None:
        db.add(PlayerMatchStats(
            match_id=match.id,
            player_id=player.id,
            goals=sd.goals,
            assists=sd.assists,
            played=sd.played,
            minutes_played=sd.minutes_played,
            team_won=sd.team_won,
            clean_sheet=sd.clean_sheet,
        ))
        result.stats_added += 1
    else:
        existing.goals = sd.goals
        existing.assists = sd.assists
        existing.played = sd.played
        existing.minutes_played = sd.minutes_played
        existing.team_won = sd.team_won
        existing.clean_sheet = sd.clean_sheet
        result.stats_updated += 1


def _recompute_match_points(db: Session, match: Match, game_id: int):
    from app.models.models import PointsRule
    from app.services.scoring import rules_from_db
    db_rules = db.query(PointsRule).filter(PointsRule.game_id == game_id).all()
    scoring_rules = rules_from_db(db_rules)

    stats_list = db.query(PlayerMatchStats).filter(
        PlayerMatchStats.match_id == match.id
    ).all()
    for stats in stats_list:
        player = db.get(FootballPlayer, stats.player_id)
        if player:
            bd = compute_points(stats, Position(player.position), scoring_rules)
            stats.computed_points = bd.total


def _get_or_create_round(
    db: Session, game_id: int, name: str | None, number: int | None
) -> Round:
    query = db.query(Round).filter(Round.game_id == game_id)
    if number is not None:
        query = query.filter(Round.round_number == number)
    elif name:
        query = query.filter(Round.name == name)
    round_ = query.first()
    if round_ is None:
        round_ = Round(
            game_id=game_id,
            name=name or f"Kolo {number}",
            round_number=number or 0,
        )
        db.add(round_)
        db.flush()
    return round_
