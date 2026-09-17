"""The cache holds only rebuildable files, but it deletes things — so the rules
about WHAT it deletes are worth pinning down.

    .venv/bin/python -m tests.test_cache
"""
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core import audio


def _mk(d: Path, name: str, size: int, age_s: float = 3600):
    f = d / name
    f.write_bytes(b"\0" * size)
    old = time.time() - age_s
    import os
    os.utime(f, (old, old))
    return f


def with_temp_cache(fn):
    def wrapper():
        real = audio.CACHE
        with TemporaryDirectory() as d:
            audio.CACHE = Path(d)
            try:
                fn(Path(d))
            finally:
                audio.CACHE = real
    wrapper.__name__ = fn.__name__
    return wrapper


@with_temp_cache
def test_prune_drops_oldest_first_until_under_the_limit(d):
    _mk(d, "warp_old.wav", 100, age_s=9000)
    _mk(d, "warp_mid.wav", 100, age_s=5000)
    keep = _mk(d, "warp_new.wav", 100, age_s=1000)
    freed = audio.prune_cache(limit=150)
    assert freed == 200, freed
    assert keep.exists() and not (d / "warp_old.wav").exists()


@with_temp_cache
def test_prune_never_touches_a_file_being_written(d):
    fresh = _mk(d, "warp_busy.wav", 500, age_s=1)      # a render in flight
    audio.prune_cache(limit=0)
    assert fresh.exists()


@with_temp_cache
def test_prune_is_a_no_op_under_the_limit(d):
    _mk(d, "warp_a.wav", 100)
    assert audio.prune_cache(limit=10_000) == 0
    assert len(list(d.glob("*"))) == 1


@with_temp_cache
def test_clear_renders_keeps_analysis_and_waveforms(d):
    _mk(d, "warp_a.wav", 100); _mk(d, "win_b.wav", 100); _mk(d, "c.wav", 100)
    _mk(d, "wave_d_1600.json", 10); _mk(d, "an_e.json", 10)
    audio.clear_cache("renders")
    left = sorted(f.name for f in d.glob("*"))
    assert left == ["an_e.json", "wave_d_1600.json"], left


@with_temp_cache
def test_clear_all_empties_the_cache(d):
    _mk(d, "warp_a.wav", 100); _mk(d, "an_e.json", 10)
    audio.clear_cache("all")
    assert list(d.glob("*")) == []


def test_cache_dir_is_separate_from_user_work():
    """The guarantee that makes clearing safe: projects, stems and exported
    mixes are not inside the cache directory."""
    root = audio.ROOT
    for other in (root / "app" / "_projects", root / "app" / "_stems",
                  root / "mixes", root / "library" / "audio"):
        assert audio.CACHE not in other.parents and other != audio.CACHE


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in fns:
        f()
    print(f"{len(fns)} passed")
