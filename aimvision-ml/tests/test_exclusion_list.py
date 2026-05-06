"""Exclusion list: append-only, idempotent, hex-validated."""

from __future__ import annotations

import pytest

from aimvision_ml.data.exclusion_list import ExclusionList


def test_creates_file_on_init(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "exclusion.txt"
    excl = ExclusionList(p)
    assert p.exists()
    assert excl.count() == 0


def test_add_and_contains(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "exclusion.txt"
    excl = ExclusionList(p)
    h = "a" * 64
    excl.add(h)
    assert excl.contains(h)
    assert not excl.contains("b" * 64)
    assert excl.count() == 1


def test_add_is_idempotent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "exclusion.txt"
    excl = ExclusionList(p)
    h = "c" * 64
    excl.add(h)
    excl.add(h)
    excl.add(h)
    assert excl.count() == 1
    # File should also reflect single line.
    assert p.read_text().strip().splitlines() == [h]


def test_persists_across_instances(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "exclusion.txt"
    excl1 = ExclusionList(p)
    excl1.add("d" * 64)
    excl2 = ExclusionList(p)
    assert excl2.contains("d" * 64)
    assert excl2.count() == 1


def test_rejects_non_hex(tmp_path) -> None:  # type: ignore[no-untyped-def]
    excl = ExclusionList(tmp_path / "exclusion.txt")
    with pytest.raises(ValueError):
        excl.add("not-a-hash")
    with pytest.raises(ValueError):
        excl.add("ABCDEF" * 8)  # uppercase rejected; we require lowercase


def test_corrupt_file_detected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "exclusion.txt"
    p.write_text("not-a-hash\n")
    excl = ExclusionList(p)
    with pytest.raises(ValueError):
        excl.contains("a" * 64)


def test_reload_picks_up_external_writes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "exclusion.txt"
    excl = ExclusionList(p)
    excl.add("a" * 64)
    # Simulate the erasure pipeline appending out-of-process.
    with p.open("a") as f:
        f.write("b" * 64 + "\n")
    excl.reload()
    assert excl.contains("b" * 64)
    assert excl.count() == 2
