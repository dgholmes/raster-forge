"""GDAL subprocess execution — install discovery, environment, streaming.

Every GDAL invocation in RasterForge goes through this module. Nothing else
constructs a command line, and nothing anywhere constructs a *shell string*:
`run()` takes an argument list and always uses `shell=False`. That is the
boundary that makes "never execute user-supplied shell commands" (PRD §17)
structurally true rather than a promise.

Three hard-won facts about the Windows/QGIS setup, each of which cost a
crash or a silent failure to discover:

1.  **`gdal2tiles.exe` crashes.** The Python entry-point wrapper shipped in
    `apps\\Python312\\Scripts` dies with an access violation (0xC0000005)
    when launched directly. The working invocation is the bundled
    interpreter running the module:
        <root>\\apps\\Python312\\python.exe -m osgeo_utils.gdal2tiles
    OSGeo4W has no `osgeo_utils` at all, so QGIS is the only viable install
    on this platform.

2.  **The inherited PATH must be discarded.** `bin\\o4w_env.bat` rebuilds
    PATH from scratch (`<root>\\bin;system32;...`) before anything runs.
    Inheriting the ambient PATH lets a foreign GDAL/PROJ DLL load first and
    the process dies. We replicate the clean path, plus `PYTHONHOME`,
    `GDAL_DATA`, `GDAL_DRIVER_PATH` and `PROJ_DATA` exactly as
    `etc\\ini\\*.bat` sets them.

3.  **Progress and phase headers arrive on different streams.** gdal2tiles
    writes "Generating Base Tiles:" to stderr and the `0...10...20...`
    ruler to stdout, and the ruler carries no newline until the phase
    finishes. We merge the streams and expose a partial-output callback so
    a progress bar can move during a phase instead of jumping at the end.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Sequence

__all__ = [
    "GdalNotFound",
    "GdalProcessCancelled",
    "GdalRunner",
    "active_install",
    "find_gdal_tool",
    "gdal2tiles_argv",
    "gdal_diagnostics",
    "gdal_env",
]

EXE_TOOLS = ("gdalinfo", "gdal_translate", "gdalwarp", "gdaladdo", "gdal_create")

_IS_WINDOWS = sys.platform.startswith("win")
_EXE = ".exe" if _IS_WINDOWS else ""


class GdalNotFound(RuntimeError):
    """A required GDAL executable or install could not be located."""


class GdalProcessCancelled(Exception):
    """The subprocess was terminated because the job was cancelled."""


# --------------------------------------------------------------------------
# Install discovery
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class GdalInstall:
    """A resolved GDAL installation.

    `root` is None for a plain system install (Linux, Docker, conda), where
    the tools are on PATH and the ambient environment is already correct.
    """
    root: Path | None
    bin_dir: Path | None
    python: Path | None          # bundled interpreter (OSGeo4W/QGIS layouts)
    gdal_data: Path | None
    proj_data: Path | None
    driver_path: Path | None

    @property
    def is_bundled(self) -> bool:
        return self.root is not None


def _first_dir(root: Path, *rels: str) -> Path | None:
    for rel in rels:
        p = root / rel
        if p.is_dir():
            return p
    return None


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []

    explicit = os.environ.get("GDAL_ROOT", "").strip() or os.environ.get("GDAL_BIN_DIR", "").strip()
    if explicit:
        p = Path(explicit)
        roots.append(p.parent if p.name.lower() == "bin" else p)

    if _IS_WINDOWS:
        for base in (Path("C:/Program Files"), Path("C:/Program Files (x86)")):
            if base.is_dir():
                # Newest QGIS first: "QGIS 3.42.2" sorts above "QGIS 3.28.1".
                roots.extend(sorted(base.glob("QGIS *"), reverse=True))
        roots.extend([Path("C:/OSGeo4W"), Path("C:/OSGeo4W64")])

    seen: set[Path] = set()
    out: list[Path] = []
    for r in roots:
        try:
            if r.is_dir() and r not in seen:
                seen.add(r)
                out.append(r)
        except OSError:
            continue
    return out


def _build_install(root: Path) -> GdalInstall | None:
    """Describe `root` as an install, or None if it is not usable."""
    bin_dir = _first_dir(root, "bin")
    if bin_dir is None:
        return None

    python: Path | None = None
    # The bundled interpreter lives in apps/Python3xx; the version moves
    # between releases, so glob rather than hardcode.
    for cand in sorted((root / "apps").glob("Python3*/python.exe"), reverse=True):
        if cand.is_file():
            python = cand
            break
    if python is None:
        cand = root / "apps" / "Python3" / "python.exe"
        python = cand if cand.is_file() else None

    return GdalInstall(
        root=root,
        bin_dir=bin_dir,
        python=python,
        gdal_data=_first_dir(root, "apps/gdal/share/gdal", "share/gdal"),
        proj_data=_first_dir(root, "share/proj", "apps/proj/share/proj"),
        driver_path=_first_dir(root, "apps/gdal/lib/gdalplugins", "lib/gdalplugins"),
    )


def _has_gdal2tiles(inst: GdalInstall) -> bool:
    """Whether this install can actually generate tiles.

    OSGeo4W ships gdalinfo and gdal_translate but no `osgeo_utils` package,
    so it can inspect a raster and never tile one. Preferring an install
    that can do the whole job avoids a pipeline that fails halfway.
    """
    if inst.python is None:
        return False
    site = inst.python.parent / "Lib" / "site-packages" / "osgeo_utils" / "gdal2tiles.py"
    return site.is_file()


@lru_cache(maxsize=1)
def active_install() -> GdalInstall:
    """The install RasterForge will use. Prefers one that can tile."""
    candidates: list[GdalInstall] = []
    for root in _candidate_roots():
        inst = _build_install(root)
        if inst is not None:
            candidates.append(inst)

    for inst in candidates:
        if _has_gdal2tiles(inst):
            return inst

    if candidates:
        # Usable for inspection, but tiling will fail with a clear error.
        return candidates[0]

    # System install (Linux, Docker, conda): tools on PATH, env already right.
    if shutil.which("gdalinfo"):
        return GdalInstall(
            root=None, bin_dir=None, python=None,
            gdal_data=None, proj_data=None, driver_path=None,
        )

    raise GdalNotFound(
        "No GDAL installation found. On Windows, install QGIS (which bundles "
        "gdal2tiles) or set GDAL_ROOT to an OSGeo4W-style install root."
    )


# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------

def _clean_windows_path(inst: GdalInstall) -> str:
    """Replicate bin\\o4w_env.bat + etc\\ini\\*.bat PATH construction.

    o4w_env.bat deliberately discards the inherited PATH. Keeping it lets a
    foreign gdal/proj/sqlite DLL win the load order, which manifests as an
    access violation rather than a readable error.
    """
    assert inst.root is not None
    windir = os.environ.get("SystemRoot", r"C:\Windows")
    parts: list[str] = []
    for p in (
        inst.root / "apps" / "qt5" / "bin",
        inst.root / "apps" / "Python312" / "Scripts",
        inst.root / "apps" / "gdal" / "bin",
        inst.bin_dir,
    ):
        if p is not None and Path(p).is_dir():
            parts.append(str(p))
    if inst.python is not None:
        scripts = inst.python.parent / "Scripts"
        if scripts.is_dir() and str(scripts) not in parts:
            parts.insert(1, str(scripts))
    parts.extend([f"{windir}\\system32", windir, f"{windir}\\system32\\WBem"])

    seen: set[str] = set()
    ordered = []
    for p in parts:
        low = p.lower()
        if low not in seen:
            seen.add(low)
            ordered.append(p)
    return os.pathsep.join(ordered)


def gdal_env() -> dict[str, str]:
    """The environment every GDAL subprocess runs under."""
    inst = active_install()

    if not inst.is_bundled:
        # System install: trust the ambient environment, add only UTF-8 hygiene.
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        return env

    # Bundled (QGIS / OSGeo4W): start from a copy with every variable that
    # could redirect DLL or data lookup removed, then set them explicitly.
    drop = {
        "PATH", "PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP",
        "GDAL_DATA", "GDAL_DRIVER_PATH", "PROJ_LIB", "PROJ_DATA",
    }
    env = {k: v for k, v in os.environ.items() if k.upper() not in drop}

    env["PATH"] = _clean_windows_path(inst)
    if inst.python is not None:
        env["PYTHONHOME"] = str(inst.python.parent)
    if inst.gdal_data is not None:
        env["GDAL_DATA"] = str(inst.gdal_data)
    if inst.driver_path is not None:
        env["GDAL_DRIVER_PATH"] = str(inst.driver_path)
    if inst.proj_data is not None:
        # PROJ 9 reads PROJ_DATA; PROJ 6-8 read PROJ_LIB. Set both.
        env["PROJ_DATA"] = str(inst.proj_data)
        env["PROJ_LIB"] = str(inst.proj_data)

    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["GDAL_FILENAME_IS_UTF8"] = "YES"
    # gdal2tiles emits a FutureWarning on stderr for every worker process.
    # Beyond being noise in the job log, it interleaves with the stdout
    # progress ruler and corrupts it mid-line.
    env.setdefault("PYTHONWARNINGS", "ignore::FutureWarning")
    # Buffer VSI reads — QGIS sets this and it measurably helps large rasters.
    env.setdefault("VSI_CACHE", "TRUE")
    env.setdefault("VSI_CACHE_SIZE", "1000000")
    return env


# --------------------------------------------------------------------------
# Tool resolution
# --------------------------------------------------------------------------

@lru_cache(maxsize=None)
def find_gdal_tool(name: str) -> Path:
    """Locate a GDAL executable (gdalinfo, gdal_translate, ...).

    Note: gdal2tiles is NOT resolved here — it is not runnable as an exe on
    Windows. Use `gdal2tiles_argv()`.
    """
    if name == "gdal2tiles":
        raise GdalNotFound(
            "gdal2tiles must be launched via gdal2tiles_argv(), not as an "
            "executable — the Windows .exe wrapper crashes."
        )

    inst = active_install()
    filename = f"{name}{_EXE}"

    if inst.bin_dir is not None:
        candidate = inst.bin_dir / filename
        if candidate.is_file():
            return candidate
    if inst.root is not None:
        for d in sorted((inst.root / "apps").glob("*/bin")):
            candidate = d / filename
            if candidate.is_file():
                return candidate

    on_path = shutil.which(name)
    if on_path:
        return Path(on_path)

    raise GdalNotFound(f"Could not locate '{name}' in {inst.root or 'PATH'}.")


def gdal2tiles_argv() -> list[str]:
    """The argv prefix that actually runs gdal2tiles on this machine.

    On a bundled install this is the interpreter plus `-m osgeo_utils.gdal2tiles`;
    launching the shipped .exe wrapper instead produces an access violation.
    """
    inst = active_install()

    override = os.environ.get("GDAL2TILES_PATH", "").strip()
    if override:
        p = Path(override)
        if not p.exists():
            raise GdalNotFound(f"GDAL2TILES_PATH points at a missing path: {p}")
        if p.suffix.lower() == ".py":
            python = str(inst.python) if inst.python else sys.executable
            return [python, str(p)]
        return [str(p)]

    if inst.is_bundled:
        if inst.python is None:
            raise GdalNotFound(
                f"GDAL install at {inst.root} has no bundled Python interpreter, "
                "so gdal2tiles cannot be run. Install QGIS or set GDAL2TILES_PATH."
            )
        if not _has_gdal2tiles(inst):
            raise GdalNotFound(
                f"The GDAL install at {inst.root} does not ship the osgeo_utils "
                "package, so it cannot generate tiles. OSGeo4W has this problem; "
                "install QGIS, which bundles gdal2tiles."
            )
        return [str(inst.python), "-m", "osgeo_utils.gdal2tiles"]

    for name in ("gdal2tiles.py", "gdal2tiles"):
        found = shutil.which(name)
        if found:
            return [found]
    return [sys.executable, "-m", "osgeo_utils.gdal2tiles"]


def gdal_diagnostics() -> dict[str, str | None]:
    """Resolved paths and environment — surfaced on the admin page."""
    out: dict[str, str | None] = {}
    try:
        inst = active_install()
        out["install_root"] = str(inst.root) if inst.root else "(system PATH)"
        out["bundled_python"] = str(inst.python) if inst.python else None
        out["can_tile"] = "yes" if (not inst.is_bundled or _has_gdal2tiles(inst)) else "no"
    except GdalNotFound as exc:
        out["install_root"] = f"NOT FOUND — {exc}"
        return out

    for name in EXE_TOOLS:
        try:
            out[name] = str(find_gdal_tool(name))
        except GdalNotFound as exc:
            out[name] = f"NOT FOUND — {exc}"
    try:
        out["gdal2tiles"] = " ".join(gdal2tiles_argv())
    except GdalNotFound as exc:
        out["gdal2tiles"] = f"NOT FOUND — {exc}"

    env = gdal_env()
    for key in ("GDAL_DATA", "PROJ_DATA", "GDAL_DRIVER_PATH", "PYTHONHOME"):
        out[key] = env.get(key)
    return out


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------

class GdalRunner:
    """Runs one GDAL subprocess at a time, streaming its output.

    Two callbacks, because gdal2tiles needs both:

    * `on_line`    — a completed line (terminated by \\n or \\r). Use for logs.
    * `on_partial` — the in-progress buffer, throttled. gdal2tiles' progress
      ruler ("0...10...20...") emits no newline until the phase ends, so a
      line-only reader would show nothing for minutes and then jump to 100%.
    """

    PARTIAL_INTERVAL_S = 0.25

    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._cancelled = threading.Event()
        self._lock = threading.Lock()

    # -- control ---------------------------------------------------------

    def cancel(self) -> None:
        """Terminate the running subprocess, if any. Safe to call repeatedly."""
        self._cancelled.set()
        with self._lock:
            proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
        except Exception:
            pass
        # gdal2tiles spawns a worker pool; give it a moment, then insist.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and proc.poll() is None:
            time.sleep(0.1)
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    # -- running ---------------------------------------------------------

    def run(
        self,
        args: Sequence[str] | Iterable[str],
        on_line: Callable[[str], None] | None = None,
        on_partial: Callable[[str], None] | None = None,
        timeout: int | None = None,
    ) -> int:
        """Run `args`, streaming output. Returns the exit code.

        Raises GdalProcessCancelled if cancelled, TimeoutError on timeout.
        """
        argv = [str(a) for a in args]
        if self._cancelled.is_set():
            raise GdalProcessCancelled("Cancelled before start")

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if _IS_WINDOWS else 0

        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # merge: headers (stderr) interleave with ruler (stdout)
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=0,
            env=gdal_env(),
            shell=False,  # never a shell — see module docstring
            creationflags=creationflags,
        )
        with self._lock:
            self._proc = proc

        started = time.monotonic()
        last_partial = 0.0
        buf: list[str] = []
        try:
            assert proc.stdout is not None
            while True:
                ch = proc.stdout.read(1)
                if ch == "":
                    break

                if ch in ("\n", "\r"):
                    if buf:
                        segment = "".join(buf).strip()
                        buf.clear()
                        if segment and on_line is not None:
                            on_line(segment)
                        last_partial = 0.0
                else:
                    buf.append(ch)
                    now = time.monotonic()
                    if on_partial is not None and (now - last_partial) >= self.PARTIAL_INTERVAL_S:
                        last_partial = now
                        on_partial("".join(buf).strip())

                if timeout is not None and (time.monotonic() - started) > timeout:
                    self.cancel()
                    raise TimeoutError(
                        f"{Path(argv[0]).name} exceeded its {timeout}s time limit"
                    )

            if buf:
                segment = "".join(buf).strip()
                if segment and on_line is not None:
                    on_line(segment)
            code = proc.wait()
        finally:
            with self._lock:
                self._proc = None

        if self._cancelled.is_set():
            raise GdalProcessCancelled(f"{Path(argv[0]).name} was cancelled")
        return code

    def run_capture(self, args: Iterable[str], timeout: int | None = None) -> tuple[int, str]:
        """Run `args` and return (exit_code, full_output)."""
        chunks: list[str] = []
        code = self.run(args, on_line=chunks.append, timeout=timeout)
        return code, "\n".join(chunks)
