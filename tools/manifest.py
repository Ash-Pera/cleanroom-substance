"""The .xml manifest that ships beside every .sbsasm, read for what the assembly lacks.

THIS IS DISTRIBUTION DATA, not a derived artifact, and that was checked rather than
assumed: of 620 original .sbsar archives in the tree, 619 are readable and 619 of those
contain both a .sbsasm and an .xml -- none without. The extracted copies are byte
identical to the archived ones, 54 of 54 compared by SHA-256. So reading `default="1"`
here stands on the same footing as reading a record out of the assembly.

WHAT IS WORTH TAKING FROM IT, measured over the corpus rather than guessed:

  output identifiers   2,479 of 2,479 declared outputs are NAMED, 100%, none missing.
                       `Assembly.outputs()` yields (uid, format, colour, record) and no
                       name, so this is the only source. The vocabulary is the same one
                       the reference renders use -- basecolor 349, normal 352, roughness
                       336, height 331, metallic 171, ambientocclusion 156 -- which turns
                       pairing a render against its reference from a filename guess into
                       an exact uid lookup.

  type-5 defaults      the constant the engine substitutes for an UNCONNECTED image
                       input. The assembly header cannot supply this: a type-5 input with
                       `default=NONE` arrives in header['inputs'] as (0,0,0,0), identical
                       to one that genuinely defaults to zero, so only the .xml separates
                       "defaults to 0" from "has no default".

WHAT IS NOT WORTH TAKING: numeric input defaults. All 3,955 manifest inputs appear in
`header['inputs']` with matching values, so the assembly already has them. (A first
comparison reported 207 disagreements; every one was float32 storage -- 0.321839 against
0.32183900475502014 -- and not a difference at all.)

STILL UNWIRED, and the reason this module exists as a seam rather than two helpers:
`alteroutputs` declares which outputs each input feeds. Cross-checked against the
edge-following closure on image inputs it agrees 233 times, contradicts 251, and is
contradicted 0 times -- our walk is a strict SUBSET, so it misses paths (samplers reach
images without an edge). Also unread: 310 `<sbspreset>` blocks carrying 7,507 values,
none of which are in the header, which holds only the default set.
"""
import os
import re

_OUTPUT = re.compile(r'<output\s+uid="(\d+)"\s+identifier="([^"]+)"', re.S)
_INPUT5 = re.compile(r'<input uid="(\d+)"\s+identifier="([^"]+)"\s+type="5"([^>]*)')
_DEFAULT = re.compile(r'default="([^"]*)"')
_CHANNEL = re.compile(r'<channel names="([^"]+)"')

_CACHE = {}


def path_for(asm):
    """The manifest beside this assembly, or None. Same stem, .xml extension."""
    p = getattr(asm, 'path', None)
    if not p:
        return None
    xml = os.path.splitext(p)[0] + '.xml'
    return xml if os.path.exists(xml) else None


def _parsed(asm):
    key = getattr(asm, 'path', None)
    if key in _CACHE:
        return _CACHE[key]
    names, defaults, channels = {}, {}, []
    xml = path_for(asm)
    if xml:
        try:
            text = open(xml, encoding='utf-8', errors='replace').read()
            names = {int(u): i for u, i in _OUTPUT.findall(text)}
            for uid, ident, rest in _INPUT5.findall(text):
                m = _DEFAULT.search(rest)
                if m:
                    defaults[int(uid)] = (m.group(1), ident)
            channels = _CHANNEL.findall(text)
        except Exception:
            names, defaults, channels = {}, {}, []
    _CACHE[key] = (names, defaults, channels)
    return _CACHE[key]


def output_names(asm):
    """{output uid: identifier} -- 'basecolor', 'normal', 'roughness', ...

    Empty when no manifest sits beside the assembly, so callers must fall back rather
    than assume a name exists. It is 100% on this corpus and that is a property of the
    corpus, not a guarantee of the format.
    """
    return _parsed(asm)[0]


def name_for(asm, uid, default=None):
    """The identifier for one output uid, or `default`."""
    return output_names(asm).get(uid, default)


def channel_names(asm):
    """Channel semantics in declaration order: baseColor, normal, roughness, ...

    Separate from `output_names`: the identifier is the output's own name, while a
    channel says what the map MEANS to a renderer. They usually coincide and are not
    required to.
    """
    return _parsed(asm)[2]


def image_input_defaults(asm):
    """{uid: (default string, identifier)} for type-5 image inputs that declare one.

    Only inputs with an explicit `default` attribute appear -- an input without one is
    absent from this mapping rather than present with a zero, which is the whole point.
    """
    return _parsed(asm)[1]
