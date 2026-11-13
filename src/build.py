"""
Gran build: skeletons (glyphs.py) -> outlines -> OTF (CFF), TTF (glyf), WOFF2, UFO.

Four weights (Light, Regular, Bold, Black), each upright and oblique: 8 styles.

Run:  .venv/bin/python src/build.py
"""
import math
import os
import shutil
import sys

import shapely
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Polygon, box as sbox
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from fontTools.agl import UV2AGL
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable

sys.path.insert(0, os.path.dirname(__file__))
from glyphs import GLYPHS, ALIASES, SW, XH, stroke  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
UPM = 1000
FAMILY = "Gran"
VERSION = "0.3"
COPYRIGHT = "Copyright 2026 The Gran Project Authors (https://github.com/ungurenko/gran-font)"
LICENSE_TEXT = "This Font Software is licensed under the SIL Open Font License, Version 1.1. This license is available with a FAQ at: https://openfontlicense.org"
LICENSE_URL = "https://openfontlicense.org"
HK = 0.93          # horizontal strokes are 7% thinner than vertical ones
SLANT = 10.0       # degrees, oblique

# name, vertical stroke width, usWeightClass
WEIGHTS = [("Light", 56, 300), ("Regular", 78, 400), ("Bold", 100, 700), ("Black", 134, 900)]


# ------------------------------------------------------------------ geometry
def expand(pts):
    """Apply per-vertex chamfers: (x, y, c) -> two points cutting the corner."""
    n = len(pts)
    out = []
    for i, p in enumerate(pts):
        x, y = float(p[0]), float(p[1])
        c = float(p[2]) if len(p) > 2 else 0.0
        if c and 0 < i < n - 1:
            px, py = pts[i - 1][0], pts[i - 1][1]
            nx, ny = pts[i + 1][0], pts[i + 1][1]
            pc = len(pts[i - 1]) > 2 and pts[i - 1][2] and i - 1 > 0
            nc = len(pts[i + 1]) > 2 and pts[i + 1][2] and i + 1 < n - 1
            d1 = math.hypot(px - x, py - y)
            d2 = math.hypot(nx - x, ny - y)
            k1 = min(c, d1 * (0.5 if pc else 1.0))
            k2 = min(c, d2 * (0.5 if nc else 1.0))
            k = min(k1, k2)
            out.append((x + (px - x) / d1 * k, y + (py - y) / d1 * k))
            out.append((x + (nx - x) / d2 * k, y + (ny - y) / d2 * k))
        else:
            out.append((x, y))
    clean = [out[0]]
    for q in out[1:]:
        if math.hypot(q[0] - clean[-1][0], q[1] - clean[-1][1]) > 1e-6:
            clean.append(q)
    return clean


def pw(v, src, dst):
    """Piecewise-linear map with slope 1 outside the knots."""
    if v <= src[0]:
        return dst[0] + (v - src[0])
    if v >= src[-1]:
        return dst[-1] + (v - src[-1])
    for i in range(len(src) - 1):
        if src[i] <= v <= src[i + 1]:
            t = (v - src[i]) / (src[i + 1] - src[i])
            return dst[i] + t * (dst[i + 1] - dst[i])
    return v


def make_warp(spec, lower, w):
    """Move centre-lines for a new stroke width so outer edges and stroke ends stay where they are.

    The skeleton is drawn for a stroke of 100 (centre-lines 50 units inside the outer edge).
    For a stroke w the centre-lines must sit w/2 inside the edge instead.
    """
    if abs(w - 100) < 1e-9 or spec["sw"] != 100:
        return None
    h = w / 2.0
    W = spec["W"]
    ymin, ymax = spec["clip"]
    top = XH if lower else 700
    xk = None
    if W > 100:
        xk = ([0, 50, W - 50, W], [0, h, W - h, W])
    yk = None
    if ymin <= 0 and ymax >= top:
        src = sorted(set([ymin, 0, 50, top - 50, top, ymax]))
        dstmap = {ymin: ymin, 0: 0, 50: h, top - 50: top - h, top: top, ymax: ymax}
        yk = (src, [dstmap[s] for s in src])

    def warp(pt):
        x, y = pt
        if xk:
            x = pw(x, *xk)
        if yk:
            y = pw(y, *yk)
        return (x, y)

    return warp


def stroke_geom(pts, sw, clip, warp):
    pts2 = expand(pts)
    if warp:
        pts2 = [warp(p) for p in pts2]
    # stretch y by 1/HK, buffer uniformly, squeeze back: horizontals become sw*HK
    line = LineString([(x, y / HK) for x, y in pts2])
    g = line.buffer(sw / 2.0, cap_style="flat", join_style="mitre", mitre_limit=8.0)
    g = affinity.scale(g, xfact=1.0, yfact=HK, origin=(0, 0))
    if clip:
        g = g.intersection(sbox(-5000, clip[0], 5000, clip[1]))
    return g


def glyph_geom(spec, lower, w, slant):
    W = spec["W"]
    k = w / 100.0
    warp = make_warp(spec, lower, w)
    parts = []
    for s in spec["strokes"]:
        if isinstance(s, dict):
            pts, sw, clip = s["pts"], s["sw"] or spec["sw"], s["clip"]
        else:
            pts, sw, clip = s, spec["sw"], None
        parts.append(stroke_geom(pts, sw * k, clip, warp))
    g = unary_union(parts)
    ymin, ymax = spec["clip"]
    g = g.intersection(sbox(0, ymin, W, ymax))
    if slant:
        g = affinity.skew(g, xs=slant, ys=0, origin=(0, 0))
    g = shapely.set_precision(g, 1.0)
    g = shapely.simplify(g, 0.3)
    g = shapely.set_precision(g, 1.0)
    return g


def polygons(g):
    if g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    if isinstance(g, MultiPolygon):
        return [p for p in g.geoms if p.area > 40]
    return [p for p in getattr(g, "geoms", []) if isinstance(p, Polygon) and p.area > 40]


def contours(g, dx, ccw_outer):
    """Closed integer contours. CFF: outer counter-clockwise. TrueType: outer clockwise."""
    res = []
    for p in polygons(g):
        p = orient(p, sign=1.0 if ccw_outer else -1.0)
        rings = [p.exterior] + list(p.interiors)
        for r in rings:
            pts = [(int(round(x + dx)), int(round(y))) for x, y in list(r.coords)[:-1]]
            if len(pts) >= 3:
                res.append(pts)
    return res


def draw(pen, cons):
    for c in cons:
        pen.moveTo(c[0])
        for pt in c[1:]:
            pen.lineTo(pt)
        pen.closePath()


# ------------------------------------------------------------------ glyph set
def glyph_name(ch):
    cp = ord(ch)
    if cp == 0x20:
        return "space"
    if cp < 0x250 and cp in UV2AGL:
        return UV2AGL[cp]
    return "uni%04X" % cp


def spacing_factor(w):
    """Lighter weights get a little more air, heavier ones a little less."""
    return 1.0 + (100.0 - w) / 100.0 * 0.4


def metrics(spec, f):
    l, r = spec["sb"]
    l, r = int(round(l * f)), int(round(r * f))
    return l, spec["W"] + l + r


# ------------------------------------------------------------------ kerning
KERN_GROUPS = [
    ("AА", "TVWYТУ", -70), ("TVWYТУ", "AА", -70),
    ("AА", "OCGQОС", -20), ("OCGQОС", "AА", -20),
    ("LЛ", "TVWYТУ", -90), ("LЛ", "ТУ", -90),
    ("PРFГ", "AАЛ", -70), ("PРF", ",.", -90),
    ("TТ", "aceoprsuwyzаеоясу", -50), ("VWYУ", "aceoprsuvwyаеоясу", -40),
    ("ЛД", "ТУ", -60), ("ТУ", "ЛД", -50), ("Я", "У", -20),
    ("Г", "аеоясд", -50),
    ("rг", ",.", -80), ("vwyу", ",.", -70), ("TY", ",.", -70),
    ("АЛДЯ", "ТУ", -60),
    ("1", "1", -30), ("7", "4", -30),
    ("ЪЬ", "ТУ", -30),
    ("kкжх", "oсеоа", -20),
]


def kern_fea(f=1.0):
    seen = {}
    for lefts, rights, val in KERN_GROUPS:
        for a in lefts:
            for b in rights:
                if (a in GLYPHS or a in ALIASES) and (b in GLYPHS or b in ALIASES):
                    seen[(glyph_name(a), glyph_name(b))] = int(round(val * f))
    lines = ["feature kern {"]
    for (a, b), v in sorted(seen.items()):
        lines.append("  pos %s %s %d;" % (a, b, v))
    lines.append("} kern;")
    return "\n".join(lines)


# ------------------------------------------------------------------ naming
def style_names(wname, italic):
    """RIBBI styles share the family; Light and Black are their own families (name IDs 16/17)."""
    if wname == "Bold":
        fam, sub = FAMILY, ("Bold Italic" if italic else "Bold")
    elif wname == "Regular":
        fam, sub = FAMILY, ("Italic" if italic else "Regular")
    else:
        fam, sub = "%s %s" % (FAMILY, wname), ("Italic" if italic else "Regular")
    typo_sub = wname + (" Italic" if italic else "")
    full = "%s %s" % (FAMILY, typo_sub)
    ps = "%s-%s%s" % (FAMILY, wname, "Italic" if italic else "")
    return fam, sub, typo_sub, full, ps


# ------------------------------------------------------------------ fonts
def common(fb, cmap, metr, wname, wclass, italic, kf):
    fam, sub, typo_sub, full, ps = style_names(wname, italic)
    fb.setupCharacterMap(cmap)
    fb.setupHorizontalMetrics(metr)
    fb.setupHorizontalHeader(ascent=950, descent=-250, lineGap=0)
    name = {
        "copyright": COPYRIGHT,
        "licenseDescription": LICENSE_TEXT,
        "licenseInfoURL": LICENSE_URL,
        "vendorURL": "https://github.com/ungurenko/gran-font",
        "familyName": fam,
        "styleName": sub,
        "uniqueFontIdentifier": "%s-%s" % (ps, VERSION),
        "fullName": full,
        "version": "Version %s" % VERSION,
        "psName": ps,
        "description": "Gran: faceted display sans with Latin and Cyrillic.",
    }
    if fam != FAMILY:
        name["typographicFamily"] = FAMILY
        name["typographicSubfamily"] = typo_sub
    fb.setupNameTable(name)
    sel = 0x80
    if italic:
        sel |= 0x01
    if wname == "Bold":
        sel |= 0x20
    if sub == "Regular":
        sel |= 0x40
    fb.setupOS2(
        version=4,
        sTypoAscender=800, sTypoDescender=-200, sTypoLineGap=200,
        usWinAscent=950, usWinDescent=250,
        sxHeight=520, sCapHeight=700,
        usWeightClass=wclass, usWidthClass=5, fsType=0,
        achVendID="GRAN", fsSelection=sel,
        ulCodePageRange1=(1 << 0) | (1 << 2),
        ulUnicodeRange1=(1 << 0) | (1 << 1), ulUnicodeRange2=(1 << 2),
    )
    fb.setupPost(isFixedPitch=0, underlinePosition=-100, underlineThickness=60 + int(wclass / 15),
                 italicAngle=-SLANT if italic else 0)
    fb.font["head"].macStyle = (1 if wname == "Bold" else 0) | (2 if italic else 0)
    addOpenTypeFeaturesFromString(fb.font, kern_fea(kf))


def export_ufo(path, wname, w, wclass, order, metr, cmap, outlines, kf):
    """Editable source: UFO3 with straight-line outlines and the kerning feature."""
    from fontTools.ufoLib import UFOWriter

    if os.path.isdir(path):
        shutil.rmtree(path)

    class Info:
        pass

    info = Info()
    info.familyName = FAMILY
    info.styleName = wname
    info.unitsPerEm = UPM
    info.ascender = 800
    info.descender = -200
    info.capHeight = 700
    info.xHeight = 520
    info.versionMajor = 0
    info.versionMinor = 3
    info.copyright = COPYRIGHT
    info.openTypeOS2WeightClass = wclass
    info.openTypeHheaAscender = 950
    info.openTypeHheaDescender = -250
    info.openTypeOS2TypoAscender = 800
    info.openTypeOS2TypoDescender = -200
    info.openTypeOS2TypoLineGap = 200
    info.openTypeOS2WinAscent = 950
    info.openTypeOS2WinDescent = 250

    writer = UFOWriter(path, formatVersion=3)
    writer.writeInfo(info)
    gs = writer.getGlyphSet()
    rev = {}
    for cp, n in cmap.items():
        rev.setdefault(n, []).append(cp)

    class G:
        pass

    for n in order:
        g = G()
        g.width = metr[n][0]
        g.height = 0
        g.unicodes = sorted(rev.get(n, []))
        cons = outlines[n][0] if outlines[n] else []

        def drawPoints(pen, cons=cons):
            for c in cons:
                pen.beginPath()
                for pt in c:
                    pen.addPoint(pt, segmentType="line")
                pen.endPath()

        gs.writeGlyph(n, g, drawPoints)
    gs.writeContents()
    writer.writeLayerContents()
    writer.writeFeatures(kern_fea(kf))
    writer.close()


def build_style(wname, w, wclass, italic):
    slant = SLANT if italic else 0.0
    f = spacing_factor(w)
    stem = "%s-%s%s" % (FAMILY, wname, "Italic" if italic else "")

    # glyph geometry, cached per source character (aliases reuse it)
    cache = {}
    for ch, spec in GLYPHS.items():
        cache[ch] = glyph_geom(spec, ch.islower(), w, slant)
    items = {ch: (GLYPHS[ch], cache[ch]) for ch in GLYPHS}
    for ch, src in ALIASES.items():
        items[ch] = (GLYPHS[src], cache[src])

    # .notdef: a frame
    nd_spec = {"W": 440, "sw": 100, "clip": (0, 700), "sb": (50, 50),
               "strokes": [stroke([(220, 30), (410, 30), (410, 670), (30, 670), (30, 30), (220, 30)], sw=60)]}
    nd_geom = glyph_geom(nd_spec, False, 100, slant)

    order = [".notdef", "space"]
    cmap = {0x20: "space"}
    entries = {".notdef": (nd_spec, nd_geom)}
    for ch in sorted(items, key=ord):
        n = glyph_name(ch)
        cmap[ord(ch)] = n
        entries[n] = items[ch]
        order.append(n)
    order = list(dict.fromkeys(order))

    metr, outlines = {}, {}
    for n in order:
        if n == "space":
            metr[n] = (int(round(260 * f)), 0)
            outlines[n] = None
            continue
        spec, geom = entries[n]
        lsb_off, adv = metrics(spec, f)
        cons_ttf = contours(geom, lsb_off, ccw_outer=False)
        cons_cff = contours(geom, lsb_off, ccw_outer=True)
        xs = [p[0] for c in cons_ttf for p in c]
        metr[n] = (adv, min(xs) if xs else 0)
        outlines[n] = (cons_ttf, cons_cff)

    # --- TTF
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(order)
    glyphs = {}
    for n in order:
        pen = TTGlyphPen(None)
        if outlines[n]:
            draw(pen, outlines[n][0])
        glyphs[n] = pen.glyph()
    fb.setupGlyf(glyphs)
    common(fb, cmap, metr, wname, wclass, italic, f)
    gasp = newTable("gasp")
    gasp.gaspRange = {0xFFFF: 0x000F}
    fb.font["gasp"] = gasp
    ttf_path = os.path.join(DIST, stem + ".ttf")
    fb.save(ttf_path)

    # --- OTF (CFF)
    fam, sub, typo_sub, full, ps = style_names(wname, italic)
    fb = FontBuilder(UPM, isTTF=False)
    fb.setupGlyphOrder(order)
    charstrings = {}
    for n in order:
        pen = T2CharStringPen(metr[n][0], None)
        if outlines[n]:
            draw(pen, outlines[n][1])
        charstrings[n] = pen.getCharString()
    fb.setupCFF(ps, {"FullName": full, "FamilyName": fam, "Weight": wname,
                     "version": VERSION, "Notice": COPYRIGHT,
                     "ItalicAngle": -SLANT if italic else 0},
                charstrings, {})
    common(fb, cmap, metr, wname, wclass, italic, f)
    otf_path = os.path.join(DIST, stem + ".otf")
    fb.save(otf_path)

    # --- WOFF2
    t = TTFont(ttf_path)
    t.flavor = "woff2"
    t.save(os.path.join(DIST, stem + ".woff2"))

    if not italic:
        export_ufo(os.path.join(DIST, stem + ".ufo"), wname, w, wclass, order, metr, cmap, outlines, f)

    return stem, cmap, len(order)


def build():
    os.makedirs(DIST, exist_ok=True)
    fonts_dir = os.path.join(ROOT, "test", "fonts")
    os.makedirs(fonts_dir, exist_ok=True)
    cmap = {}
    for wname, w, wclass in WEIGHTS:
        for italic in (False, True):
            stem, cmap, n = build_style(wname, w, wclass, italic)
            print("%-18s glyphs %d  otf %6d  ttf %6d  woff2 %5d" % (
                stem, n,
                os.path.getsize(os.path.join(DIST, stem + ".otf")),
                os.path.getsize(os.path.join(DIST, stem + ".ttf")),
                os.path.getsize(os.path.join(DIST, stem + ".woff2"))))
            for ext in ("otf", "ttf", "woff2"):
                shutil.copyfile(os.path.join(DIST, stem + "." + ext), os.path.join(fonts_dir, stem + "." + ext))

    cps = sorted(cp for cp in cmap if cp != 0x20)
    with open(os.path.join(ROOT, "test", "codepoints.js"), "w") as fh:
        fh.write("window.GRAN_CODEPOINTS = %s;\n" % cps)


if __name__ == "__main__":
    build()
