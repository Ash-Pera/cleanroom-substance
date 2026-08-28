"""Read Substance `.sbsar` packages without the Substance engine.

    import sbsarx

    pkg = sbsarx.open_package("Bricks.sbsar")
    print(pkg.graph.identifier, [o.identifier for o in pkg.outputs])
    for res in pkg.resources:
        print(res)                      # L8 1024x1024 grayscale, 1048576 bytes
        pkg.write(res, "out/")

What this reads is the *embedded image data* a package carries, and the interface the
manifest publishes. It does not evaluate the procedural graph: a package that computes
its maps at cook time carries no images to extract, and this will report none.

**The format does not record whether an embedded image is a source input or a cached
output.** Both occur, and nothing in the bytes distinguishes them — see `README.md`.
Nothing here guesses.

Derived from the clean-room format description in the parent project; see FORMAT-NOTES.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import assembly, container, imaging, manifest, resources
from .assembly import Assembly, NotAnAssembly
from .container import NotAPackage
from .manifest import Graph, Input, Manifest, Output
from .resources import Resource

__version__ = "0.1.0"

__all__ = [
    "open_package", "open_assembly", "Package",
    "Resource", "Graph", "Input", "Output", "Manifest", "Assembly",
    "NotAPackage", "NotAnAssembly",
]


@dataclass
class Package:
    """An opened `.sbsar`, or a bare `.sbsasm` with no manifest."""

    path: Path
    assembly: Assembly
    manifest: Manifest | None = None

    @property
    def graph(self) -> Graph | None:
        return self.manifest.graph if self.manifest else None

    @property
    def graphs(self) -> tuple[Graph, ...]:
        return self.manifest.graphs if self.manifest else ()

    @property
    def outputs(self) -> tuple[Output, ...]:
        """Outputs the manifest declares. Not a mapping onto `resources`."""
        return tuple(o for g in self.graphs for o in g.outputs)

    @property
    def inputs(self) -> tuple[Input, ...]:
        return tuple(i for g in self.graphs for i in g.inputs)

    @property
    def resources(self) -> list[Resource]:
        """Every embedded image the assembly describes, in segment order."""
        if self._resources is None:
            self._resources = resources.resources(self.assembly)
        return self._resources

    _resources: list[Resource] | None = None

    def payload(self, res: Resource) -> bytes:
        """The resource's bytes: raw pixels, or a complete JPEG file."""
        return resources.payload(self.assembly, res)

    def coverage(self) -> dict:
        """How completely the resources account for the head-of-file segment."""
        return resources.segment_report(self.assembly, self.resources)

    def write(self, res: Resource, directory, stem: str | None = None) -> Path:
        """Write one resource to `directory`. JPEG resources are written verbatim."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        stem = stem or imaging.suggested_name(res)
        data = self.payload(res)
        if res.is_jpeg:
            target = directory / (stem + ".jpg")
            target.write_bytes(data)
            return target
        target = directory / (stem + ".png")
        imaging.to_pillow(res, data).save(target)
        return target


def open_package(path) -> Package:
    """Open a `.sbsar`. Reads the whole assembly into memory."""
    path = Path(path)
    with container.unpacked(path) as (asm_path, xml_path):
        asm = assembly.load(asm_path)
        man = manifest.parse(xml_path.read_bytes()) if xml_path else None
    return Package(path=path, assembly=asm, manifest=man)


def open_assembly(path) -> Package:
    """Open a bare `.sbsasm`, with no manifest to name anything."""
    path = Path(path)
    return Package(path=path, assembly=assembly.load(path), manifest=None)
