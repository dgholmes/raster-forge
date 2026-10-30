"""LocalPublisher's optional directory mirror (TILE_PUBLISH_DIR).

Pure filesystem tests: a fake pyramid is laid out by hand, so these run
without GDAL. The round-trip through the real pipeline is in test_api.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from raster.publisher import LocalPublisher, PublishError

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _fake_pyramid(root: Path, zooms=(14, 15)) -> Path:
    for z in zooms:
        for x in range(2):
            d = root / str(z) / str(x)
            d.mkdir(parents=True, exist_ok=True)
            (d / "7.png").write_bytes(PNG)
    return root


def _publish(publisher: LocalPublisher, slug: str, tiles: Path, meta: Path):
    return publisher.publish(
        slug=slug, tiles_dir=tiles, metadata_path=meta,
        min_zoom=14, max_zoom=15, bounds=[127.0, 37.0, 127.1, 37.1],
        center=[127.05, 37.05], display_name="Test",
    )


def test_no_publish_dir_means_no_mirror(tmp_path):
    tiles = _fake_pyramid(tmp_path / "tiles")
    pub = LocalPublisher("http://host/tiles")
    assert pub.publish_dir is None
    assert pub.published_dir_for("abc") is None

    result = _publish(pub, "abc", tiles, tmp_path / "meta" / "metadata.json")
    assert result.url_template == "http://host/tiles/abc/{z}/{x}/{y}.png"
    assert (tmp_path / "meta" / "metadata.json").is_file()
    assert not list(tmp_path.glob("abc*"))


def test_from_config_treats_blank_dir_as_disabled():
    assert LocalPublisher.from_config({"TILE_PUBLIC_BASE": "http://h/t"}).publish_dir is None
    assert LocalPublisher.from_config(
        {"TILE_PUBLIC_BASE": "http://h/t", "TILE_PUBLISH_DIR": "   "}
    ).publish_dir is None
    pub = LocalPublisher.from_config(
        {"TILE_PUBLIC_BASE": "http://h/t/", "TILE_PUBLISH_DIR": "/srv/2Dtile"}
    )
    assert pub.publish_dir == Path("/srv/2Dtile")
    assert pub.tile_public_base == "http://h/t"


def test_publish_mirrors_pyramid_and_metadata_into_slug_folder(tmp_path):
    tiles = _fake_pyramid(tmp_path / "storage" / "tiles")
    publish_dir = tmp_path / "2Dtile"
    pub = LocalPublisher("http://host/2Dtile", publish_dir)

    _publish(pub, "gangnam-rgb", tiles, tmp_path / "storage" / "metadata.json")

    mirror = publish_dir / "gangnam-rgb"
    assert (mirror / "14" / "0" / "7.png").read_bytes() == PNG
    assert (mirror / "15" / "1" / "7.png").read_bytes() == PNG
    doc = json.loads((mirror / "metadata.json").read_text(encoding="utf-8"))
    assert doc["tile_url_template"] == "http://host/2Dtile/gangnam-rgb/{z}/{x}/{y}.png"
    assert doc["tile_count"] == 4
    # No staging or retired leftovers next to the slug folder.
    assert sorted(p.name for p in publish_dir.iterdir()) == ["gangnam-rgb"]


def test_republish_replaces_previous_mirror(tmp_path):
    publish_dir = tmp_path / "2Dtile"
    pub = LocalPublisher("http://host/2Dtile", publish_dir)
    meta = tmp_path / "metadata.json"

    first = _fake_pyramid(tmp_path / "first", zooms=(14, 15))
    _publish(pub, "s", first, meta)
    stale = publish_dir / "s" / "15" / "1" / "7.png"
    assert stale.is_file()

    # A regenerated pyramid without zoom 15: the old z15 tiles must not linger.
    second = _fake_pyramid(tmp_path / "second", zooms=(14,))
    pub.publish(
        slug="s", tiles_dir=second, metadata_path=meta, min_zoom=14, max_zoom=14,
        bounds=None, center=None, display_name="Test",
    )
    assert (publish_dir / "s" / "14" / "0" / "7.png").is_file()
    assert not stale.exists()
    assert sorted(p.name for p in publish_dir.iterdir()) == ["s"]


def test_rename_moves_mirror_and_unpublish_removes_it(tmp_path):
    publish_dir = tmp_path / "2Dtile"
    pub = LocalPublisher("http://host/2Dtile", publish_dir)
    _publish(pub, "old-name", _fake_pyramid(tmp_path / "t"), tmp_path / "m.json")

    pub.rename("old-name", "new-name")
    assert not (publish_dir / "old-name").exists()
    assert (publish_dir / "new-name" / "14" / "0" / "7.png").is_file()

    pub.rename("never-published", "whatever")  # nothing to move: silent

    pub.unpublish("new-name")
    assert not (publish_dir / "new-name").exists()
    pub.unpublish("new-name")  # idempotent


def test_rename_and_unpublish_are_noops_without_publish_dir(tmp_path):
    pub = LocalPublisher("http://host/tiles")
    pub.rename("a", "b")
    pub.unpublish("a")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("bad", ["../escape", "a/b", "", "Upper", "-lead", "trail-", "a..b"])
def test_mirror_refuses_slugs_that_are_not_plain_dir_names(tmp_path, bad):
    pub = LocalPublisher("http://host/2Dtile", tmp_path / "2Dtile")
    with pytest.raises(PublishError):
        pub.published_dir_for(bad)
    with pytest.raises(PublishError):
        _publish(pub, bad, _fake_pyramid(tmp_path / "t"), tmp_path / "m.json")
    assert not (tmp_path / "2Dtile").exists() or not list((tmp_path / "2Dtile").iterdir())


def test_mirror_failure_leaves_previous_mirror_and_skips_metadata(tmp_path, monkeypatch):
    publish_dir = tmp_path / "2Dtile"
    pub = LocalPublisher("http://host/2Dtile", publish_dir)
    meta = tmp_path / "metadata.json"
    _publish(pub, "s", _fake_pyramid(tmp_path / "first"), meta)
    before = (publish_dir / "s" / "metadata.json").read_text(encoding="utf-8")
    meta.unlink()

    import raster.publisher as mod

    def boom(src, dst, *a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(mod.shutil, "copytree", boom)
    with pytest.raises(PublishError, match="disk full"):
        _publish(pub, "s", _fake_pyramid(tmp_path / "second"), meta)

    # The tile host still serves the previous version, nothing half-written
    # is visible, and the storage-side metadata was not rewritten.
    assert (publish_dir / "s" / "metadata.json").read_text(encoding="utf-8") == before
    assert sorted(p.name for p in publish_dir.iterdir()) == ["s"]
    assert not meta.exists()
