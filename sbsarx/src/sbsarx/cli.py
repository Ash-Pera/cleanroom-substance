"""Command line: `sbsarx list`, `sbsarx extract`, `sbsarx audit`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, imaging, open_assembly, open_package
from .container import MissingExtractor, NotAPackage
from .assembly import NotAnAssembly


def _open(path: Path):
    path = Path(path)
    return open_assembly(path) if path.suffix == ".sbsasm" else open_package(path)


def _print_list(pkg, show_inputs: bool) -> None:
    print(pkg.path.name)
    for graph in pkg.graphs:
        print("  graph  %s" % graph.identifier)
        if graph.author:
            print("         author %s" % graph.author)
        print("  declared outputs (%d)" % len(graph.outputs))
        for out in graph.outputs:
            usage = (" [%s]" % out.usage) if out.usage else ""
            print("      %-20s%s" % (out.identifier, usage))
        if show_inputs and graph.inputs:
            print("  declared inputs (%d)" % len(graph.inputs))
            for inp in graph.inputs:
                print("      %-20s %-8s %s" % (inp.identifier, inp.type, inp.label))

    res = pkg.resources
    print("  embedded images (%d)" % len(res))
    for r in res:
        print("      %2d  %-7s %5dx%-5d %-9s %10d bytes  @%d"
              % (r.index, r.format, r.width, r.height,
                 "colour" if r.colour else "grayscale", r.size, r.offset))
    cov = pkg.coverage()
    if cov["segment_bytes"]:
        print("  segment %d bytes, %d covered by descriptors%s"
              % (cov["segment_bytes"], cov["covered_bytes"],
                 ", tiles exactly" if cov["tiles_exactly"] else ""))
    if res and pkg.graphs:
        print("  note: the format does not record which embedded image corresponds to "
              "which\n        declared output, or whether an image is a source input at all.")


def cmd_list(args) -> int:
    for path in args.paths:
        _print_list(_open(path), args.inputs)
    return 0


def cmd_extract(args) -> int:
    for path in args.paths:
        pkg = _open(path)
        out = Path(args.output) / Path(path).stem if len(args.paths) > 1 else Path(args.output)
        written = []
        for res in pkg.resources:
            if res.is_jpeg or imaging.available():
                target = pkg.write(res, out)
                written.append((res, target))
                lossy = " (16-bit colour reduced to 8)" if imaging.lossy_on_write(res) else ""
                print("%s  %s%s" % (target, res, lossy))
            else:
                print("skipped %s: needs Pillow and NumPy" % imaging.suggested_name(res),
                      file=sys.stderr)
        if not pkg.resources:
            print("%s: no embedded images — this package computes its maps at cook time"
                  % Path(path).name, file=sys.stderr)
        if args.sidecar and written:
            _write_sidecar(pkg, written, out)
    return 0


def _write_sidecar(pkg, written, out: Path) -> None:
    doc = {
        "package": pkg.path.name,
        "sbsarx_version": __version__,
        "graphs": [
            {
                "identifier": g.identifier, "label": g.label, "author": g.author,
                "declared_outputs": [
                    {"identifier": o.identifier, "usage": o.usage, "uid": o.uid}
                    for o in g.outputs
                ],
            }
            for g in pkg.graphs
        ],
        "embedded_images": [
            {
                "index": r.index, "file": target.name, "format": r.format,
                "width": r.width, "height": r.height, "channels": r.channels,
                "depth": r.depth, "colour": r.colour, "offset": r.offset,
                "bytes": r.size,
            }
            for r, target in written
        ],
        "coverage": pkg.coverage(),
        "caveat": (
            "The .sbsasm does not record which embedded image corresponds to which "
            "declared output, nor whether an image is a source input rather than a "
            "cached output. No correspondence is implied by the ordering here."
        ),
    }
    (out / "sbsarx.json").write_text(json.dumps(doc, indent=2))


def cmd_audit(args) -> int:
    """Run the reader over a corpus and report what it can and cannot account for."""
    total = with_images = tiled = failed = 0
    images = 0
    formats: dict[str, int] = {}
    problems = []
    for path in args.paths:
        total += 1
        try:
            pkg = _open(path)
            res = pkg.resources
        except (NotAPackage, NotAnAssembly, MissingExtractor) as exc:
            failed += 1
            problems.append((Path(path).name, str(exc)[:60]))
            continue
        if not res:
            continue
        with_images += 1
        images += len(res)
        for r in res:
            formats[r.format] = formats.get(r.format, 0) + 1
        cov = pkg.coverage()
        if cov["tiles_exactly"]:
            tiled += 1
        elif args.verbose:
            problems.append((Path(path).name,
                             "gaps=%d overlaps=%d covered=%d/%d"
                             % (cov["internal_gaps"], cov["overlaps"],
                                cov["covered_bytes"], cov["segment_bytes"])))
    print("packages read            %d" % total)
    print("  failed to parse        %d" % failed)
    print("  with embedded images   %d" % with_images)
    print("  segment tiled exactly  %d / %d" % (tiled, with_images))
    print("images described         %d" % images)
    for name, count in sorted(formats.items(), key=lambda kv: -kv[1]):
        print("  %-7s %d" % (name, count))
    if problems:
        print("\nnot fully accounted for:")
        for name, why in problems[:40]:
            print("  %-40s %s" % (name, why))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="sbsarx",
        description="Read Substance .sbsar packages without the Substance engine.")
    parser.add_argument("--version", action="version", version="sbsarx " + __version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="show a package's interface and embedded images")
    p.add_argument("paths", nargs="+")
    p.add_argument("--inputs", action="store_true", help="also list declared inputs")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("extract", help="write the embedded images to disk")
    p.add_argument("paths", nargs="+")
    p.add_argument("-o", "--output", default=".", help="output directory")
    p.add_argument("--no-sidecar", dest="sidecar", action="store_false",
                   help="do not write sbsarx.json alongside the images")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("audit", help="run the reader over a corpus and report coverage")
    p.add_argument("paths", nargs="+")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="list every package not fully accounted for")
    p.set_defaults(func=cmd_audit)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (NotAPackage, NotAnAssembly, MissingExtractor) as exc:
        print("sbsarx: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
