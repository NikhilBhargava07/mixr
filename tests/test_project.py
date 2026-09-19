"""Project-level tempo changes. Run: .venv/bin/python -m tests.test_project"""
from app.core import warp
from app.core.project import Project, Track, Clip

close = lambda a, b, tol=1e-9: abs(a - b) <= tol


def demo():
    """98 BPM project: a clip warped from 126 BPM, and an unwarped one."""
    p = Project(name="t", bpm=98.0, downbeats=[0.0, 2.449, 4.898])
    t = Track(name="warped")
    t.clips.append(Clip(name="w", start=4.0, offset=10.0, length=20.0,
                        warp=warp.uniform(126.0 / 98.0)))
    u = Track(name="plain")
    u.clips.append(Clip(name="u", start=8.0, offset=0.0, length=3.0))
    p.tracks += [t, u]
    return p


def test_speeding_up_keeps_everything_on_the_grid():
    p = demo()
    r = p.retempo(100.8)
    c = p.tracks[0].clips[0]
    assert close(r, 98 / 100.8)
    # the warped clip now plays 126 -> 100.8
    assert close(warp.overall_stretch(c.warp), 126.0 / 100.8, 1e-9)
    # and keeps its place in bars: 4s at 98 BPM is the same bar as 3.889s at 100.8
    assert close(c.start, 4.0 * 98 / 100.8)
    assert close(c.offset, 10.0 * 98 / 100.8) and close(c.length, 20.0 * 98 / 100.8)
    assert close(p.downbeats[1], 2.449 * 98 / 100.8)
    assert p.bpm == 100.8


def test_unwarped_clips_move_but_keep_their_length():
    p = demo()
    p.retempo(100.8)
    u = p.tracks[1].clips[0]
    assert close(u.start, 8.0 * 98 / 100.8)
    assert u.length == 3.0 and u.warp == []


def test_round_trip_returns_the_original_numbers():
    p = demo()
    before = [(c.start, c.offset, c.length, list(c.warp))
              for t in p.tracks for c in t.clips]
    p.retempo(100.8); p.retempo(98.0)
    after = [(c.start, c.offset, c.length, list(c.warp)) for t in p.tracks for c in t.clips]
    for (a, b, c1, w1), (d, e, f, w2) in zip(before, after):
        assert close(a, d, 1e-9) and close(b, e, 1e-9) and close(c1, f, 1e-9)
        for (x1, y1), (x2, y2) in zip(w1, w2):
            assert close(x1, x2, 1e-6) and close(y1, y2, 1e-6)


def test_an_impossible_tempo_changes_nothing():
    p = demo()
    snapshot = p.to_dict()
    for bad in (10.0, 400.0, 260.0):        # 260 would need a 2.6x stretch
        try:
            p.retempo(bad)
            assert False, bad
        except warp.WarpError:
            pass
    assert p.to_dict() == snapshot          # all-or-nothing


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in fns:
        f()
    print(f"{len(fns)} passed")
