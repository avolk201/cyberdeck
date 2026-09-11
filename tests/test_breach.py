import pygame
import pytest

from cyberdeck.ui.breach_protocol import HexBreachProtocol, HEX_TOKENS
from cyberdeck.stats import session_stats


@pytest.fixture()
def breach():
    pygame.font.init()
    rect = pygame.Rect(0, 0, 800, 480)
    font = pygame.font.SysFont("courier", 22)
    return HexBreachProtocol(rect, font)


@pytest.fixture(autouse=True)
def _reset_streak():
    saved = session_stats.streak
    yield
    session_stats.streak = saved


def test_grid_shape(breach):
    assert len(breach.grid) == breach.grid_size
    for row in breach.grid:
        assert len(row) == breach.grid_size
        for tok in row:
            assert tok in HEX_TOKENS


def test_three_daemons_valid_seqs(breach):
    assert len(breach.daemons) == 3
    for d in breach.daemons:
        assert len(d["seq"]) == d["len"] if "len" in d else len(d["seq"]) >= 2
        assert d["matched_index"] == 0
        assert d["uploaded"] is False


def test_initial_axis_is_row_zero(breach):
    assert breach.is_row_selection is True
    assert breach.active_index == 0


def test_commit_move_switches_axis(breach):
    assert breach.is_row_selection is True
    breach._commit_move(0, 2)
    assert breach.is_row_selection is False
    assert breach.active_index == 2  # now column 2
    breach._commit_move(3, 2)
    assert breach.is_row_selection is True
    assert breach.active_index == 3  # now row 3


def test_buffer_fills(breach):
    breach._commit_move(0, 0)
    assert len(breach.buffer) == 1
    breach._commit_move(1, 0)
    assert len(breach.buffer) == 2


def test_timer_starts_on_first_move(breach):
    assert breach.timer_started is False
    breach._commit_move(0, 0)
    assert breach.timer_started is True


def test_selectable_coords_exclude_selected(breach):
    coords = breach._get_selectable_coords()
    assert (0, 0) in coords
    breach._commit_move(0, 0)
    # Now on column 0; (0,0) already selected so not selectable
    coords = breach._get_selectable_coords()
    assert (0, 0) not in coords


def test_cursor_move_wraps(breach):
    selectable = breach._get_selectable_coords()
    n = len(selectable)
    breach.move_cursor(-1)  # wraps to last
    assert breach.cursor_idx == n - 1
    breach.move_cursor(1)
    assert breach.cursor_idx == 0


def test_buffer_full_without_match_fails(breach):
    # Force all daemon seqs to a token not present in grid picks we choose.
    for d in breach.daemons:
        d["seq"] = ["ZZ"] * 2
    for i in range(breach.buffer_size):
        if breach.solved or breach.failed:
            break
        coord = breach.get_current_cursor_coord()
        breach._commit_move(coord[0], coord[1])
    assert breach.failed is True
    assert breach.solved is False


def test_threat_level_tracks_streak_capped(breach):
    session_stats.streak = 0
    assert breach.threat_level() == 0
    session_stats.streak = 3
    assert breach.threat_level() == 3
    session_stats.streak = 99
    assert breach.threat_level() == breach.max_threat


def test_adaptive_time_decreases_with_streak(breach):
    session_stats.streak = 0
    t0 = breach._adaptive_time()
    session_stats.streak = 2
    t2 = breach._adaptive_time()
    assert t0 == breach.base_time
    assert t2 < t0


def test_adaptive_time_has_floor(breach):
    session_stats.streak = 1000
    assert breach._adaptive_time() == breach.min_time


def test_update_syncs_time_before_start(breach):
    session_stats.streak = 4
    breach.timer_started = False
    breach.update()
    assert breach.time_limit == breach._adaptive_time()
    assert breach.time_limit < breach.base_time
    assert breach.time_remaining == breach.time_limit
