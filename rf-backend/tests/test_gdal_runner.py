from pathlib import Path

import pytest

from raster.gdal_runner import (
    GdalRunner,
    active_install,
    find_gdal_tool,
    gdal2tiles_argv,
    gdal_diagnostics,
    gdal_env,
)


@pytest.mark.parametrize("tool", ["gdalinfo", "gdal_translate"])
def test_finds_required_exe_tools(tool):
    assert find_gdal_tool(tool).is_file()


def test_gdal2tiles_is_not_resolved_as_an_exe():
    """The Windows .exe wrapper segfaults; callers must use gdal2tiles_argv()."""
    from raster.gdal_runner import GdalNotFound
    with pytest.raises(GdalNotFound):
        find_gdal_tool("gdal2tiles")


def test_gdal2tiles_argv_is_runnable():
    argv = gdal2tiles_argv()
    assert argv, "gdal2tiles must resolve to something"
    assert Path(argv[0]).exists(), argv


def test_env_defines_gdal_data_and_proj():
    env = gdal_env()
    assert Path(env["GDAL_DATA"]).is_dir()
    if active_install().is_bundled:
        assert Path(env["PROJ_DATA"]).is_dir()
        assert "PYTHONHOME" in env, "PYTHONHOME is required or gdal2tiles crashes"


def test_bundled_env_discards_inherited_path():
    """Inheriting PATH lets a foreign GDAL DLL load first -> access violation."""
    inst = active_install()
    if not inst.is_bundled:
        pytest.skip("system install keeps the ambient PATH by design")
    import os
    env = gdal_env()
    assert env["PATH"] != os.environ.get("PATH")
    assert str(inst.bin_dir).lower() in env["PATH"].lower()


def test_runner_streams_lines_and_returns_zero():
    lines = []
    rc = GdalRunner().run([str(find_gdal_tool("gdalinfo")), "--version"], on_line=lines.append)
    assert rc == 0
    assert any("GDAL" in line for line in lines), lines


def test_gdal2tiles_help_runs_without_crashing():
    """Regression guard for the 0xC0000005 access violation."""
    rc, out = GdalRunner().run_capture(gdal2tiles_argv() + ["--help"], timeout=120)
    assert rc == 0, f"gdal2tiles crashed with rc={rc}"
    assert "profile" in out.lower()


def test_diagnostics_reports_a_tiling_capable_install():
    diag = gdal_diagnostics()
    assert diag["can_tile"] == "yes", diag
