from unittest.mock import MagicMock
from app.models.models import Participant
from app.services.draft_engine import build_snake_order


def _p(pid: int, order: int) -> Participant:
    p = MagicMock(spec=Participant)
    p.id = pid
    p.draft_order = order
    return p


def test_two_participants_two_rounds():
    p1, p2 = _p(1, 1), _p(2, 2)
    order = build_snake_order([p1, p2], total_rounds=2)
    assert order == [1, 2, 2, 1]


def test_two_participants_four_rounds():
    p1, p2 = _p(1, 1), _p(2, 2)
    order = build_snake_order([p1, p2], total_rounds=4)
    assert order == [1, 2, 2, 1, 1, 2, 2, 1]


def test_three_participants_two_rounds():
    p1, p2, p3 = _p(1, 1), _p(2, 2), _p(3, 3)
    order = build_snake_order([p1, p2, p3], total_rounds=2)
    assert order == [1, 2, 3, 3, 2, 1]


def test_three_participants_four_rounds():
    p1, p2, p3 = _p(1, 1), _p(2, 2), _p(3, 3)
    order = build_snake_order([p1, p2, p3], total_rounds=4)
    # R1 forward, R2 backward, R3 forward, R4 backward
    assert order == [1, 2, 3, 3, 2, 1, 1, 2, 3, 3, 2, 1]


def test_single_participant():
    p = _p(42, 1)
    order = build_snake_order([p], total_rounds=3)
    assert order == [42, 42, 42]


def test_single_round():
    p1, p2 = _p(10, 1), _p(20, 2)
    order = build_snake_order([p1, p2], total_rounds=1)
    assert order == [10, 20]


def test_draft_order_respected():
    # p1 has draft_order=2, p2 has draft_order=1 → p2 picks first
    p1, p2 = _p(1, 2), _p(2, 1)
    order = build_snake_order([p1, p2], total_rounds=2)
    assert order[0] == 2   # p2 (draft_order=1) goes first
    assert order[1] == 1   # p1 (draft_order=2) goes second
    assert order[2] == 1   # reverses for round 2
    assert order[3] == 2


def test_total_picks_equals_participants_times_rounds():
    participants = [_p(i, i) for i in range(1, 6)]
    rounds = 18
    order = build_snake_order(participants, total_rounds=rounds)
    assert len(order) == len(participants) * rounds


def test_each_participant_appears_once_per_round():
    p1, p2, p3 = _p(1, 1), _p(2, 2), _p(3, 3)
    order = build_snake_order([p1, p2, p3], total_rounds=6)
    for round_idx in range(6):
        chunk = order[round_idx * 3: (round_idx + 1) * 3]
        assert sorted(chunk) == [1, 2, 3]


def test_odd_rounds_forward_even_rounds_backward():
    p1, p2, p3 = _p(1, 1), _p(2, 2), _p(3, 3)
    order = build_snake_order([p1, p2, p3], total_rounds=4)
    assert order[:3] == [1, 2, 3]    # round 1 (index 0): forward
    assert order[3:6] == [3, 2, 1]   # round 2 (index 1): backward
    assert order[6:9] == [1, 2, 3]   # round 3 (index 2): forward
    assert order[9:12] == [3, 2, 1]  # round 4 (index 3): backward
