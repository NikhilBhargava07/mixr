"""Exact tests for the warp-map maths. Run:  .venv/bin/python -m pytest tests/ -q
(or without pytest:  .venv/bin/python tests/test_warp.py)"""
import math
from app.core import warp

close = lambda a, b, tol=1e-9: abs(a - b) <= tol


def test_no_pins_is_identity():
    assert warp.src_to_dst([], 12.5) == 12.5
    assert warp.dst_to_src([], 12.5) == 12.5


def test_uniform_stretch_everywhere_including_beyond_the_pins():
    m = warp.uniform(1.075)
    for t in (0, 0.5, 1, 100, 231.78):
        assert close(warp.src_to_dst(m, t), t * 1.075)
        assert close(warp.dst_to_src(m, t * 1.075), t)


def test_piecewise_map_matches_the_click_track_experiment():
    m = [[0, 0], [4, 5], [8.5, 9.5]]       # first 4s -> 5s, rest 1:1
    assert close(warp.src_to_dst(m, 2), 2.5)
    assert close(warp.src_to_dst(m, 4), 5)
    assert close(warp.src_to_dst(m, 6), 7)
    assert close(warp.src_to_dst(m, 10), 11)          # extrapolated, slope 1


def test_inverse_round_trips():
    m = [[0, 0], [2, 2.4], [5, 5.1], [9, 9.6]]
    for t in [0, 0.3, 2, 3.7, 5, 8.2, 12]:
        assert close(warp.dst_to_src(m, warp.src_to_dst(m, t)), t, 1e-9)


def test_normalize_shifts_so_the_file_starts_at_zero():
    m = warp.normalize([[1, 2], [3, 5]])              # slope 1.5, dst(0) was 0.5
    assert close(warp.src_to_dst(m, 0), 0)
    assert close(warp.src_to_dst(m, 3) - warp.src_to_dst(m, 1), 3)


def test_normalize_rejects_bad_maps():
    for bad in ([[0, 0], [1, 0]],          # dst doesn't advance
                [[0, 0], [1, 5]],          # slope 5
                [[-1, 0], [1, 1]]):        # before the file
        try:
            warp.normalize(bad)
            assert False, bad
        except warp.WarpError:
            pass


def test_identity_collapses_to_no_map():
    assert warp.normalize([[0, 0], [5, 5]]) == []
    assert warp.uniform(1.0) == []


def test_rescale_window_uniform_is_just_a_ratio():
    """The rule the server used before pins existed must still hold."""
    off, ln = warp.rescale_window(warp.uniform(1.075), warp.uniform(1.0), 10.75, 20.0)
    assert close(off, 10.0) and close(ln, 20 / 1.075)


def test_rescale_window_keeps_the_same_music_under_a_piecewise_map():
    old = []
    new = [[0, 0], [4, 5], [8.5, 9.5]]
    off, ln = warp.rescale_window(old, new, 3.0, 3.0)   # source 3s..6s
    assert close(off, 3.75)                              # 3 * 1.25
    assert close(off + ln, 7.0)                          # 5 + (6 - 4)


def test_rubberband_map_covers_the_whole_file():
    frames, end = warp.rubberband_map([[0, 0], [4, 5]], duration=8.5, sr=44100)
    assert frames[0] == (0, 0)
    assert frames[-1] == (round(8.5 * 44100), round(10.625 * 44100))
    assert close(end, 10.625)


def test_signature_is_stable_and_sensitive():
    a = warp.signature([[0, 0], [1, 1.075]], 0, "beats")
    assert a == warp.signature([[0.0, 0.0], [1.0, 1.07500001]], 0.0, "beats")
    assert a != warp.signature([[0, 0], [1, 1.075]], 0, "tones")
    assert a != warp.signature([[0, 0], [1, 1.08]], 0, "beats")




def test_best_bar_picks_the_multiple_that_fits_the_song():
    dbs = [0, 2.0, 4.0, 6.0, 8.0]                  # 2s bars
    assert close(warp.best_bar(dbs, 2.0), 2.0)
    assert close(warp.best_bar(dbs, 4.0), 2.0)     # grid heard double-time
    assert close(warp.best_bar(dbs, 1.0), 2.0)     # grid heard half-time


def test_from_downbeats_locks_a_drifting_song_to_the_grid():
    dbs = [0.0, 2.1, 4.1, 6.4, 8.4]                # drifts around a 2s bar
    pins = warp.normalize(warp.from_downbeats(dbs, 2.0))
    for i, src in enumerate(dbs):
        assert close(warp.src_to_dst(pins, src), i * 2.0, 1e-6)


def test_from_downbeats_skips_an_impossible_downbeat():
    dbs = [0.0, 2.0, 2.05, 6.0, 8.0]               # 2.05 is a false positive
    pins = warp.from_downbeats(dbs, 2.0)
    assert [p[0] for p in pins] == [0.0, 2.0, 6.0, 8.0]
    warp.normalize(pins)                            # must still be a legal map


def test_from_downbeats_anchors_where_told():
    pins = warp.from_downbeats([10.0, 12.0, 14.0], 2.0, anchor_dst=30.0, anchor=0)
    assert pins[0] == [10.0, 30.0] and pins[-1] == [14.0, 34.0]


def test_key_parsing_and_transposition():
    assert warp.parse_key("F# minor") == (6, "minor")
    assert warp.parse_key("Bb major") == (10, "major")
    assert warp.parse_key("nonsense") is None
    assert warp.semitones_between("C major", "D major") == 2
    assert warp.semitones_between("C major", "A major") == -3      # not +9
    assert warp.semitones_between("C major", "F# major") == 6
    assert warp.semitones_between("C major", "") is None




def test_window_snaps_outward_and_is_stable_under_small_edits():
    a = warp.window_for(32.0, 20.0)
    assert a == (15.0, 60.0)                       # 27 -> 15, 57 -> 60
    assert warp.window_for(33.5, 19.0) == a        # a small trim reuses it
    assert warp.window_for(3.0, 5.0) == (0.0, 15.0)   # never before the file


def test_sub_map_rebases_both_axes():
    pins = [[0, 0], [4, 5], [8.5, 9.5]]
    m, base = warp.sub_map(pins, 2.0, 6.0)
    assert close(base, 2.5)                        # dst of the slice's start
    assert m[0] == [0.0, 0.0]
    assert close(m[-1][0], 4.0) and close(m[-1][1], warp.src_to_dst(pins, 6.0) - base)
    # a point inside the slice keeps its place relative to the slice
    assert close(warp.src_to_dst(m, 4.0 - 2.0), warp.src_to_dst(pins, 4.0) - base)


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in fns:
        f()
    print(f"{len(fns)} passed")
