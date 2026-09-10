"""Progress parsing and parameter validation — the parts that must be right
without running GDAL."""
import pytest

from raster.pipeline import (
    Gdal2TilesProgress,
    PipelineError,
    RulerProgress,
    TileParams,
)


# --- ruler parsing --------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("0", 0),
    ("0...10...20", 20),
    ("0...10...20...30...40...50...60...70...80...90...100 - done.", 100),
    ("0...10...100 - done.", 100),
])
def test_parses_real_rulers(text, expected):
    assert RulerProgress.parse(text) == expected


@pytest.mark.parametrize("text", [
    "Warning 3: Cannot find tms_MapML_APSTILE.json (GDAL_DATA is not defined)",
    "Generating Base Tiles:",
    "ERROR 1: Failed to open file",
    "",
    "Input file size is 2048, 2048",
])
def test_rejects_non_rulers(text):
    """A warning containing a digit must never be read as a percentage."""
    assert RulerProgress.parse(text) is None


# --- phase mapping --------------------------------------------------------

def test_base_phase_maps_to_first_70_percent():
    p = Gdal2TilesProgress(lo=0, hi=100)
    p.feed("Generating Base Tiles:")
    assert p.feed("0...10...20...30") == (21, "Generating base tiles (30%)")


def test_overview_phase_maps_to_last_30_percent():
    p = Gdal2TilesProgress(lo=0, hi=100)
    p.feed("Generating Base Tiles:")
    p.feed("0...10...100 - done.")
    p.feed("Generating Overview Tiles:")
    assert p.feed("0...10...20...30...40...50") == (85, "Generating overview tiles (50%)")


def test_respects_custom_span():
    """The pipeline runs tiling inside 15..95 of overall job progress."""
    p = Gdal2TilesProgress(lo=15, hi=95)
    p.feed("Generating Base Tiles:")
    assert p.feed("0...100 - done.")[0] == 71  # 15 + 0.7*80


def test_ignores_unrelated_output():
    p = Gdal2TilesProgress()
    assert p.feed("Warning 3: Cannot find tms_MapML_APSTILE.json") is None


def test_suppresses_duplicate_updates():
    p = Gdal2TilesProgress()
    p.feed("Generating Base Tiles:")
    first = p.feed("0...10...20")
    assert first is not None
    assert p.feed("0...10...20") is None, "identical progress must not re-emit"


def test_ruler_before_header_is_treated_as_base():
    p = Gdal2TilesProgress(lo=0, hi=100)
    assert p.feed("0...10...50")[0] == 35


# --- parameter validation -------------------------------------------------

def test_accepts_valid_params():
    p = TileParams(min_zoom=14, max_zoom=21).validated()
    assert p.resampling == "bilinear" and p.processes >= 1


@pytest.mark.parametrize("kwargs,fragment", [
    (dict(min_zoom=14, max_zoom=23), "between 0 and 22"),
    (dict(min_zoom=-1, max_zoom=10), "between 0 and 22"),
    (dict(min_zoom=18, max_zoom=14), "greater than maximum"),
    (dict(min_zoom=14, max_zoom=18, resampling="rm -rf /"), "Unsupported resampling"),
    (dict(min_zoom=14, max_zoom=18, nodata_mode="whatever"), "auto, preserve or remove"),
])
def test_rejects_invalid_params(kwargs, fragment):
    with pytest.raises(PipelineError) as exc:
        TileParams(**kwargs).validated()
    assert fragment in str(exc.value)


def test_clamps_process_count():
    assert TileParams(14, 18, processes=999).validated().processes == 16
    assert TileParams(14, 18, processes=0).validated().processes == 1


# --- multi-pass overview handling ----------------------------------------

def test_overview_restart_advances_to_next_pass_instead_of_going_backwards():
    """gdal2tiles emits one ruler per overview zoom level, each restarting at
    0. Naively parsing them made the bar jump 73% -> 71%."""
    p = Gdal2TilesProgress(lo=15, hi=95, overview_passes=3)
    p.feed("Generating Base Tiles:")
    p.feed("0...100 - done.")
    p.feed("Generating Overview Tiles:")

    seen = []
    for ruler in ("0...50", "0...100 - done.",   # pass 1
                  "0...50", "0...100 - done.",   # pass 2 (restart)
                  "0...50", "0...100 - done."):  # pass 3 (restart)
        update = p.feed(ruler)
        if update:
            seen.append(update[0])

    assert seen == sorted(seen), f"progress went backwards: {seen}"
    assert seen[-1] == 95, seen


def test_progress_never_decreases_even_on_unexpected_output():
    p = Gdal2TilesProgress(lo=0, hi=100)
    p.feed("Generating Base Tiles:")
    high = p.feed("0...90")[0]
    after = p.feed("0...10")
    assert after is None or after[0] >= high


def test_parses_ruler_that_lost_its_leading_zero_to_interleaved_stderr():
    """gdal2tiles writes the ruler to stdout and warnings to stderr. When they
    interleave, the ruler's leading '0' is swallowed into the warning segment
    and the remainder arrives as '...10...20...'. Anchoring the parser on '0'
    silently froze the progress bar for the whole job."""
    assert RulerProgress.parse("...10...20...30") == 30
    assert RulerProgress.parse("...10...100 - done.") == 100


def test_bare_number_is_not_a_ruler():
    """Guard the relaxed regex: a lone integer must not read as a percentage."""
    assert RulerProgress.parse("42") is None
    assert RulerProgress.parse("1024 1024") is None
