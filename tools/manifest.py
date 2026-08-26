"""The .xml manifest that ships beside every .sbsasm, read for what the assembly lacks.

THIS IS DISTRIBUTION DATA, not a derived artifact, and that was checked rather than
assumed: of 620 original .sbsar archives in the tree, 619 are readable and 619 of those
contain both a .sbsasm and an .xml -- none without. The extracted copies are byte
identical to the archived ones, 54 of 54 compared by SHA-256. So reading `default="1"`
here stands on the same footing as reading a record out of the assembly.

WHAT IS WORTH TAKING FROM IT, measured over the corpus rather than guessed:

  output identifiers   2,479 of 2,479 declared outputs are NAMED, 100%, none missing.
                       `Assembly.outputs()` yields (uid, format, GRAYSCALE, record) and no
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
_INPUT_ANY = re.compile(r'<input uid="(\d+)"\s+identifier="([^"]+)"\s+type="(\d+)"([^>]*)')
_ALTER = re.compile(r'alteroutputs="([^"]*)"')
_GRAPH_SPLIT = re.compile(r'(?=<graph )')

_CACHE = {}


def path_for(asm):
    """The manifest beside this assembly, or None. Same stem, .xml extension."""
    p = getattr(asm, 'path', None)
    if not p:
        return None
    xml = os.path.splitext(p)[0] + '.xml'
    return xml if os.path.exists(xml) else None


_CHANNEL_CACHE = {}
_MISSING = object()


def _parsed(asm):
    key = getattr(asm, 'path', None)
    if key in _CACHE:
        return _CACHE[key]
    names, defaults, channels, alter, graphs = {}, {}, [], {}, []
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
            for uid, ident, typ, rest in _INPUT_ANY.findall(text):
                m = _ALTER.search(rest)
                if m is not None:
                    alter[int(uid)] = (int(typ), ident,
                                       {int(z) for z in m.group(1).split(',') if z})
            for block in _GRAPH_SPLIT.split(text)[1:]:
                url = re.search(r'pkgurl="([^"]*)"', block)
                graphs.append({
                    'pkgurl': url.group(1) if url else None,
                    'outputs': [int(u) for u, _i in _OUTPUT.findall(block)],
                    # DECLARATION ORDER IS LOAD-BEARING -- see image_inputs_for_output.
                    'image_inputs': [int(u) for u, _i, ty, _r in _INPUT_ANY.findall(block)
                                     if ty == '5'],
                })
        except Exception:
            names, defaults, channels, alter, graphs = {}, {}, [], {}, []
    _CACHE[key] = (names, defaults, channels, alter, graphs)
    return _CACHE[key]


def output_names(asm):
    """{output uid: identifier} -- 'basecolor', 'normal', 'roughness', ...

    Empty when no manifest sits beside the assembly, so callers must fall back rather
    than assume a name exists. It is 100% on this corpus and that is a property of the
    corpus, not a guarantee of the format.

    The identifier is the output's OWN NAME. The manifest separately carries
    `<channel names="...">`, which says what the map means to a renderer -- they usually
    coincide and are not required to. Nothing here needs the distinction yet, so the
    channel list is parsed and left unexposed rather than given an accessor no caller
    uses; `_parsed`'s third element is where it sits if a caller ever does.
    """
    return _parsed(asm)[0]


def output_channels(asm):
    """{output uid: declared channel name} -- 'baseColor', 'normal', 'ambientOcclusion'...

    WHAT THIS IS FOR, since `output_names` deliberately did not expose it. The identifier
    is the output's own name and the channel is what the map MEANS to a renderer. They
    usually coincide, which is why nothing needed the distinction; where they do not, the
    identifier can be content-free while the channel is not. StylizedCobblestoneStreet is
    the case: its six outputs are named `output`, `output_1` ... `output_5`, and the
    manifest separately declares them as baseColor, normal, roughness, ambientOcclusion,
    height and metallic. Matching that pack's exported maps by identifier pairs 0 of 12;
    by channel it pairs all of them.

    Parsed by splitting on the output tag rather than with one regex spanning both, so an
    output that declares no channel cannot borrow the next one's -- which a non-greedy
    match across `<output ...>` boundaries would happily do.
    """
    got = _CHANNEL_CACHE.get(getattr(asm, 'path', None), _MISSING)
    if got is not _MISSING:
        return got
    out = {}
    xml = path_for(asm)
    if xml:
        try:
            text = open(xml, encoding='utf-8', errors='replace').read()
            for block in text.split('<output uid="')[1:]:
                head = block.split('</output>', 1)[0]
                uid = head.split('"', 1)[0]
                m = re.search(r'<channel\s+names="([^"]*)"', head)
                if uid.isdigit() and m:
                    out[int(uid)] = m.group(1)
        except Exception:
            out = {}
    _CHANNEL_CACHE[getattr(asm, 'path', None)] = out
    return out


def name_for(asm, uid, default=None):
    """The identifier for one output uid, or `default`."""
    return output_names(asm).get(uid, default)


def image_input_defaults(asm):
    """{uid: (default string, identifier)} for type-5 image inputs that declare one.

    Only inputs with an explicit `default` attribute appear -- an input without one is
    absent from this mapping rather than present with a zero, which is the whole point.
    """
    return _parsed(asm)[1]


def alter_outputs(asm):
    """{input uid: (type code, identifier, {output uids it feeds})}.

    The manifest's own dependency claim, and the only independent statement of graph
    structure available -- everything else here is derived from the same edge walk it is
    used to check. Wired in as a CHECK rather than as data: see
    `test_closure_never_claims_a_dependency_the_manifest_denies`.

    Measured over the whole corpus, restricted to type-5 image inputs (10,837 pairs):

        both agree: reaches                        622   5.74%
        manifest YES, our closure NO               513   4.73%
        manifest NO,  our closure YES                0   0.00%
        both agree: does not reach                9702  89.53%

    The one-sidedness is the finding. If our walk were merely DIFFERENT from the
    manifest's we would miss in both directions; missing 513 while over-claiming 0 says
    our closure is a strict SUBSET, i.e. it does not see some paths.

    The mechanism was hypothesised to be sampler reads bypassing `Record.edges`, and that
    is now MEASURED and mostly refuted. A program's `samplelum`/`samplecol` (opcodes 0x33,
    0x34) carries a sampler index in token 1, and corpus-wide that index indexes INTO the
    record's own edges in 55,916 of 56,127 sampler-reading records (99.62%): sampler k is
    the record's k-th input edge, which an edge walk DOES follow. Only 0.37% are genuinely
    edge-bypassing -- 197 records whose sampler index exceeds their edge count and 14 with
    no edges at all (an FX-Map like `ie_curve` record 172 that is itself an output and asks
    for sampler 0), and those bind to the graph's k-th image input by manifest declaration
    order. So samplers are a small part of the 513, not the bulk of it; the larger causes
    are elsewhere (sub-graph instances expanded at cook time being the leading candidate).

    Consequence worth stating plainly: closure-derived counts UNDERSTATE how many root
    causes block an output, so "one fix away" rankings are optimistic, not merely rough.

    ONLY type-5 IS CHECKED. A numeric input reaches an output through `inputref` inside a
    program, which the edge graph does not model at all, so the same comparison on type 0
    or 4 would report enormous disagreement and measure nothing but that absence.
    """
    return _parsed(asm)[3]


def graphs(asm):
    """One entry per <graph> block: pkgurl, its output uids, its image-input uids.

    A single .sbsasm commonly holds many graphs -- ie_curve holds 20 -- and the assembly
    itself does not say which records belong to which. Only the manifest does.
    """
    return _parsed(asm)[4]


def image_inputs_for_output(asm, output_uid):
    """Image-input uids of the graph declaring `output_uid`, IN DECLARATION ORDER.

    This is the map a sampler index needs. An FX-Map that reaches its images through
    sampler indices carries no edge to follow -- ie_curve record 172 is an `fxmaps` with
    edges=[] that is itself a declared output, and it asks for sampler 0 -- so the only
    way to bind index k to a record is the k-th image input of the graph that owns it.

    ORDER COMES FROM THE MANIFEST AND CANNOT BE RECOVERED FROM THE ASSEMBLY. Measured
    over ie_curve's 20 graphs: only 7 have contiguous graph_input record blocks, and only
    1 has declaration order matching record order -- and that one declares a single input,
    so it satisfies both trivially. In curve_area_splatter, `curve_2` is declaration index
    2 but record 139, sitting BEFORE `back` at index 0 / record 140. Binding by record
    order would attach the wrong image and return a plausible picture from the wrong
    source, which is the failure this project treats as worse than a crash.

    Returns [] when the output is not declared by any graph block.
    """
    for g in graphs(asm):
        if output_uid in g['outputs']:
            return list(g['image_inputs'])
    return []
