"""The `.xml` manifest that travels beside the assembly in a `.sbsar`.

This is the layer every existing tool reads. It carries the published interface —
graph identity, inputs, outputs and presets — but no graph topology and no pixels.
It is parsed here so that a resource can be reported next to what the package claims
to produce.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

#: Manifest type codes, as published in the DTD.
TYPES = {
    0: "float1", 1: "float2", 2: "float3", 3: "float4", 4: "int1",
    5: "image", 6: "string", 7: "font", 8: "int2", 9: "int3", 10: "int4",
}


@dataclass(frozen=True)
class Output:
    uid: str
    identifier: str
    usages: tuple[str, ...]
    label: str
    width: int | None
    height: int | None

    @property
    def usage(self) -> str:
        """The first declared channel usage — `baseColor`, `normal`, `roughness`, ..."""
        return self.usages[0] if self.usages else ""


@dataclass(frozen=True)
class Input:
    uid: str
    identifier: str
    type: str
    label: str
    default: str | None


@dataclass(frozen=True)
class Graph:
    pkgurl: str
    label: str
    category: str
    author: str
    outputs: tuple[Output, ...] = ()
    inputs: tuple[Input, ...] = ()
    presets: tuple[str, ...] = ()

    @property
    def identifier(self) -> str:
        return self.pkgurl.rsplit("/", 1)[-1] if self.pkgurl else self.label


@dataclass(frozen=True)
class Manifest:
    formatversion: str
    graphs: tuple[Graph, ...] = field(default=())

    @property
    def graph(self) -> Graph | None:
        """The single graph, for the overwhelmingly common one-graph package."""
        return self.graphs[0] if len(self.graphs) == 1 else None


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse(xml_bytes: bytes) -> Manifest:
    root = ET.fromstring(xml_bytes)
    graphs = []
    for g in root.iter("graph"):
        outputs = []
        for o in g.iter("output"):
            gui = o.find("outputgui")
            usages = tuple(
                c.get("names", "") for c in o.iter("channel") if c.get("names")
            )
            outputs.append(Output(
                uid=o.get("uid", ""),
                identifier=o.get("identifier", ""),
                usages=usages,
                label=gui.get("label", "") if gui is not None else "",
                width=_int(o.get("width")),
                height=_int(o.get("height")),
            ))
        inputs = []
        for i in g.iter("input"):
            gui = i.find("inputgui")
            inputs.append(Input(
                uid=i.get("uid", ""),
                identifier=i.get("identifier", ""),
                type=TYPES.get(_int(i.get("type")), i.get("type", "")),
                label=gui.get("label", "") if gui is not None else "",
                default=i.get("default"),
            ))
        presets = tuple(
            p.get("label", "") for p in g.iter("sbspreset")
        )
        graphs.append(Graph(
            pkgurl=g.get("pkgurl", ""), label=g.get("label", ""),
            category=g.get("category", ""), author=g.get("author", ""),
            outputs=tuple(outputs), inputs=tuple(inputs), presets=presets,
        ))
    return Manifest(formatversion=root.get("formatversion", ""), graphs=tuple(graphs))
