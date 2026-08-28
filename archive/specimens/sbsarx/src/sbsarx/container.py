"""The `.sbsar` container.

A plain 7-zip archive, magic `37 7A BC AF 27 1C`, laid out identically in every
specimen examined:

    assemblies/content/0000/<name>.sbsasm     compiled graph
    assemblies/content/0000/<name>.xml        manifest: inputs, outputs, GUI, presets
    assemblies/content/0000/thumbnail.png     icon

Extraction uses `py7zr` when it is installed and falls back to `bsdtar` or `7z` on the
path, so the package works without a compiled dependency either way.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

SEVENZIP_MAGIC = b"7z\xbc\xaf\x27\x1c"


class NotAPackage(ValueError):
    pass


class MissingExtractor(RuntimeError):
    pass


def is_package(path) -> bool:
    with open(path, "rb") as fh:
        return fh.read(6) == SEVENZIP_MAGIC


def _extract_py7zr(path: Path, dest: Path) -> bool:
    try:
        import py7zr
    except ImportError:
        return False
    with py7zr.SevenZipFile(path, "r") as archive:
        archive.extractall(path=dest)
    return True


def _extract_external(path: Path, dest: Path) -> bool:
    if shutil.which("bsdtar"):
        cmd = ["bsdtar", "-xf", str(path), "-C", str(dest)]
    elif shutil.which("7z"):
        cmd = ["7z", "x", "-y", "-o" + str(dest), str(path)]
    elif shutil.which("7za"):
        cmd = ["7za", "x", "-y", "-o" + str(dest), str(path)]
    else:
        return False
    return subprocess.run(cmd, capture_output=True).returncode == 0


def unpack(path, dest) -> Path:
    """Unpack a `.sbsar` into `dest` and return the directory holding the content."""
    path, dest = Path(path), Path(dest)
    if not is_package(path):
        raise NotAPackage("%s is not a 7-zip archive" % path)
    if not (_extract_py7zr(path, dest) or _extract_external(path, dest)):
        raise MissingExtractor(
            "no way to read a 7-zip archive: install py7zr (pip install py7zr) "
            "or put bsdtar or 7z on the PATH"
        )
    return dest


def contents(directory) -> tuple[Path | None, Path | None]:
    """Locate the assembly and manifest inside an unpacked package."""
    directory = Path(directory)
    asm = next(iter(sorted(directory.rglob("*.sbsasm"))), None)
    xml = next(iter(sorted(directory.rglob("*.xml"))), None)
    return asm, xml


class unpacked:
    """Context manager yielding (assembly_path, manifest_path) for a `.sbsar`."""

    def __init__(self, path):
        self.path = Path(path)
        self._tmp = None

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="sbsarx-")
        unpack(self.path, self._tmp.name)
        asm, xml = contents(self._tmp.name)
        if asm is None:
            raise NotAPackage("no .sbsasm inside %s" % self.path)
        return asm, xml

    def __exit__(self, *exc):
        self._tmp.cleanup()
        return False
