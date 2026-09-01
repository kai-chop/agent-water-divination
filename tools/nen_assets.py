# -*- coding: utf-8 -*-
"""nen_assets — generate the repo's diagrams and social preview from the pattern files.

Hand-drawn diagrams rot. Rename a type, add a language, change what a signal is called, and the
picture in the README quietly starts lying. So nothing here is drawn by hand: the six vessels, their
names and their reactions all come out of `patterns/*.json`, which is also what the tools read. Fork
this, rename a type, re-run, and the diagram agrees with the code again.

The vessel geometry is imported from nen_report, so the picture in the README and the picture in
your own report are the same drawing, not two drawings that look alike.

Output is SVG with presentation attributes rather than CSS classes, and an opaque background:
  - some renderers strip <style> out of an SVG served as an image, which would leave every shape
    unfilled and the diagram blank
  - a transparent background turns dark text invisible on a dark README

  python tools/nen_assets.py                 # English wording -> assets/*.svg
  python tools/nen_assets.py --lang ja       # Japanese wording -> assets/*.ja.svg

The social preview needs to be a raster image, which nothing in this repo can produce without a
dependency. `--png` shells out to a headless browser if you have one; otherwise the SVG is there
and any converter will do.

Self-test: python tools/nen_assets.py --self-test
"""
import argparse
import html
import io
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import nen_corpus as corpus      # noqa: E402
import nen_report as report      # noqa: E402
import nen_signals as signals    # noqa: E402  (also the single source of the axis catalogue)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ASSETS_VERSION = "1"

# One opaque palette for every asset. Dark ground so the images read the same on a light or a dark
# README -- these are pictures, not pages, and they cannot follow the reader's theme.
INK = "#0b1315"
SURFACE = "#101b1d"
LINE = "#26383c"
TEXT = "#e3ecea"
SOFT = "#9db0ad"
FAINT = "#6e8380"
WATER = "#4fc2cc"
FILL = "#1d5a63"
LEAF = "#9ac25f"
SAND = "#b7a888"
GLASS = "#4b6469"
RUST = "#d9765c"

# nen_report draws with CSS classes so the report can follow the reader's theme. Assets cannot,
# so the same markup is rewritten to presentation attributes here.
CLASS_TO_ATTR = {
    'class="w"': 'fill="%s"' % FILL,
    'class="g"': 'fill="none" stroke="%s" stroke-width="1.6" stroke-linejoin="round"' % GLASS,
    'class="lf"': 'fill="%s"' % LEAF,
    'class="sp"': 'fill="%s"' % SAND,
    'class="sh"': 'fill="none" stroke="%s" stroke-width="1.2"' % SURFACE,
    '<g class="spin">': "<g>",
}

FONT = ("system-ui,-apple-system,'Segoe UI',Roboto,'Hiragino Sans',"
        "'Yu Gothic UI',Meiryo,sans-serif")
SERIF = "Georgia,'Hiragino Mincho ProN','Yu Mincho',serif"
MONO = "ui-monospace,'Cascadia Mono',Consolas,monospace"

E = html.escape


def inline_vessel(tid):
    """report's vessel markup, with classes rewritten to attributes a bare renderer keeps."""
    markup = report.GLASS.get(tid, "") + report.GLASS_BODY
    for cls, attr in CLASS_TO_ATTR.items():
        markup = markup.replace(cls, attr)
    return markup


def _text(x, y, s, size=14, fill=TEXT, family=FONT, anchor="middle", weight="400", spacing=None):
    extra = ' letter-spacing="%s"' % spacing if spacing else ""
    return ('<text x="%s" y="%s" font-family="%s" font-size="%s" fill="%s" '
            'text-anchor="%s" font-weight="%s"%s>%s</text>'
            % (x, y, family, size, fill, anchor, weight, extra, E(s)))


def _wrap(s, width):
    """Break a line for SVG, which has no text flow. Splits on spaces where there are any, and
    by character count where there are not -- Japanese has no spaces to split on."""
    if " " in s:
        words, lines, cur = s.split(), [], ""
        for w in words:
            if len(cur) + len(w) + 1 > width and cur:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            lines.append(cur)
        return lines
    step = max(1, width // 2)
    return [s[i:i + step] for i in range(0, len(s), step)]


def _svg(w, h, body, title):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" '
            'role="img" aria-label="%s">\n<title>%s</title>\n'
            '<rect width="%d" height="%d" fill="%s"/>\n%s\n</svg>\n'
            % (w, h, w, h, E(title), E(title), w, h, INK, body))


# ---------------------------------------------------------------- the six vessels

def six_vessels(types, w=1120, h=330):
    """The six types as the reactions they are named for, straight out of the pattern files."""
    body = ['<rect x="1" y="1" width="%d" height="%d" fill="%s" stroke="%s"/>'
            % (w - 2, h - 2, SURFACE, LINE)]
    body.append(_text(w // 2, 46, "The six vessels", 20, TEXT, SERIF, weight="700"))
    # "the water" would be wrong: five reactions happen to the water and the sixth to the leaf
    body.append(_text(w // 2, 72, "which way the glass reacts is which type you are", 13, FAINT))

    n = len(types) or 1
    col = w / n
    for i, t in enumerate(types):
        cx = col * i + col / 2
        body.append('<g transform="translate(%.1f,100) scale(1.35)">%s</g>'
                    % (cx - 40, inline_vessel(t["id"])))
        body.append(_text(cx, 245, t["label"], 16, TEXT, SERIF, weight="700"))
        body.append(_text(cx, 264, t.get("label_en", ""), 11, WATER, MONO))
        for j, line in enumerate(_wrap(t.get("reaction", ""), 18)[:2]):
            body.append(_text(cx, 288 + j * 15, line, 11, FAINT))
    return _svg(w, h, "\n".join(body), "The six vessels of the water divination")


# ---------------------------------------------------------------- the gate

def gate(w=1120, h=360, lang="en"):
    """The repo's actual claim: measuring is the easy half, and the interview is a gate."""
    en = lang != "ja"
    stages = [
        ("1  MEASURE", "a date window",
         "Reads only what you typed. Counts six types' signals." if en
         else "自分が打った発話だけを読み、6系統のシグナルを数える"),
        ("2  INTERVIEW", "what the numbers cannot settle",
         "Was this quote yours? Is that zero an inability, or no occasion?" if en
         else "この引用はあなたの言葉か。その0は能力か、機会が無かっただけか"),
        ("3  VERDICT", "only once they are answered",
         "Names the type, on evidence you confirmed." if en
         else "確認の取れた証拠の上でだけ、系統を名指しする"),
    ]
    body = [_text(w // 2, 44, "Measuring is the easy half" if en else "測るのは簡単な方の半分",
                  20, TEXT, SERIF, weight="700")]

    bw, gap, y = 320, 40, 80
    for i, (num, sub, desc) in enumerate(stages):
        x = i * (bw + gap)
        accent = WATER if i == 2 else SOFT
        body.append('<rect x="%d" y="%d" width="%d" height="150" fill="%s" stroke="%s"/>'
                    % (x, y, bw, SURFACE, LINE))
        body.append('<rect x="%d" y="%d" width="4" height="150" fill="%s"/>' % (x, y, accent))
        body.append(_text(x + 22, y + 34, num, 13, accent, MONO, anchor="start", spacing="1.5"))
        body.append(_text(x + 22, y + 58, sub, 12, FAINT, FONT, anchor="start"))
        for j, line in enumerate(_wrap(desc, 40)[:4]):
            body.append(_text(x + 22, y + 88 + j * 19, line, 13, TEXT, FONT, anchor="start"))
        if i < len(stages) - 1:
            ax = x + bw + gap / 2
            body.append('<path d="M%.0f %d L%.0f %d" stroke="%s" stroke-width="1.5"/>'
                        % (ax - 12, y + 75, ax + 10, y + 75, LINE))
            body.append('<path d="M%.0f %d l-7 -5 l0 10 Z" fill="%s"/>' % (ax + 12, y + 75, LINE))

    # Every wrapped line is drawn and the box grows to fit. Slicing to a fixed line count is how a
    # diagram silently loses the second half of its own sentence.
    ry = y + 190
    line = ("Until every blocking question is answered, `verdict` refuses. Saying \"no, I pasted "
            "that\" revokes the quote — and if that drops a type below the two quotes a verdict "
            "needs, the verdict goes too." if en else
            "blocking の質問が全部埋まるまで verdict は拒否する。「それは貼り付け」と答えると引用は"
            "証拠から剥奪され、必要な2件を割れば判定ごと落ちる。")
    lines = _wrap(line, 100 if en else 46)
    box_h = 34 + len(lines) * 20 + 14
    body.append('<rect x="0" y="%d" width="%d" height="%d" fill="%s" stroke="%s"/>'
                % (ry, w, box_h, SURFACE, RUST))
    body.append(_text(24, ry + 26, "NO VERDICT" if en else "断定は出ない", 13, RUST, MONO,
                      anchor="start", spacing="1.5"))
    for j, ln in enumerate(lines):
        body.append(_text(24, ry + 50 + j * 20, ln, 13, SOFT, FONT, anchor="start"))
    h = max(h, ry + box_h + 16)
    return _svg(w, h, "\n".join(body),
                "measure, then interview, then verdict — and the verdict is refused until the "
                "interview is answered")


# ---------------------------------------------------------------- the six axes

def six_axes(types, w=1120, h=430, lang="en"):
    """Each aptitude against its own outcome. Drawn from signals.AXES, which is the same table
    the measurement reads, so the picture cannot claim an axis the code does not count."""
    en = lang != "ja"
    # a type can own more than one axis, so the table is grouped by type, not keyed by it
    cat = {}
    for _aid, tid, label, unit, _detail in signals.axis_catalogue():
        cat.setdefault(tid, []).append((label, unit))
    body = [_text(w // 2, 44,
                  "Six aptitudes, six separate quantities" if en else "6つの適性に、6つの別々の量",
                  20, TEXT, SERIF, weight="700")]
    body.append(_text(w // 2, 70,
                      "different outcome, different denominator, different unit -- so they can "
                      "disagree" if en else
                      "結果変数も分母も単位も別だから、互いに食い違える", 13, FAINT))

    y = 96
    row_h = 46
    rows = sum(max(1, len(cat.get(t["id"], []))) for t in types)
    body.append('<rect x="0" y="%d" width="%d" height="%d" fill="%s" stroke="%s"/>'
                % (y, w, row_h * rows + 30, SURFACE, LINE))
    body.append(_text(24, y + 22, "TYPE" if en else "系統", 10, FAINT, MONO,
                      anchor="start", spacing="1.4"))
    body.append(_text(250, y + 22, "ITS OWN AXIS" if en else "固有の軸", 10, FAINT, MONO,
                      anchor="start", spacing="1.4"))
    body.append(_text(850, y + 22, "DENOMINATOR" if en else "分母", 10, FAINT, MONO,
                      anchor="start", spacing="1.4"))

    row = 0
    for t in types:
        entries = cat.get(t["id"], [])
        for k, entry in enumerate(entries or [None]):
            top = y + 30 + row * row_h
            row += 1
            body.append('<path d="M0 %d L%d %d" stroke="%s" stroke-width="1"/>'
                        % (top, w, top, LINE))
            if k == 0:      # the vessel and the name belong to the type, not to each axis
                body.append('<g transform="translate(24,%d) scale(0.42)">%s</g>'
                            % (top + 4, inline_vessel(t["id"])))
                body.append(_text(52, top + 29, t["label"], 15, TEXT, SERIF,
                                  anchor="start", weight="700"))
                body.append(_text(148, top + 29, t.get("label_en", ""), 11, WATER, MONO,
                                  anchor="start"))
            if entry:
                body.append(_text(250, top + 29, entry[0], 13, TEXT, FONT, anchor="start"))
                body.append(_text(850, top + 29, entry[1], 12, SOFT, MONO, anchor="start"))
                continue
            body.append(_text(250, top + 29,
                              "no axis -- what the other five do not explain" if en else
                              "軸を持たない ―― 他の5系統が説明しない残り", 13, LEAF, FONT,
                              anchor="start"))
            body.append(_text(850, top + 29, "you read it" if en else "読むのは人", 12, LEAF,
                              MONO, anchor="start"))

    note = ("The first version scored all five against one shared outcome. Every type landed "
            "within a few points of every other, because that measures one thing five times."
            if en else
            "最初の実装は5系統に共通の結果変数を当てていた。全部が数ポイント差で並んだ——"
            "それは1つの量を5回測っているだけだから。")
    ny = y + 30 + row_h * rows + 26
    for j, line in enumerate(_wrap(note, 104 if en else 54)):
        body.append(_text(24, ny + j * 20, line, 12, FAINT, FONT, anchor="start"))
    h = max(h, ny + 24 * (len(_wrap(note, 104 if en else 54))) + 10)
    return _svg(w, h, "\n".join(body),
                "each aptitude measured against its own outcome, with its own denominator")


# ---------------------------------------------------------------- social preview

def social_preview(types, repo_name, tagline, w=1280, h=640):
    """1280x640 is what GitHub wants. Everything is opaque; nothing is loaded from outside."""
    body = ['<rect x="40" y="40" width="%d" height="%d" fill="%s" stroke="%s"/>'
            % (w - 80, h - 80, SURFACE, LINE)]
    body.append(_text(w // 2, 132, repo_name, 20, WATER, MONO, spacing="2.5"))
    body.append(_text(w // 2, 200, "Measure the operator,", 46, TEXT, SERIF, weight="700"))
    body.append(_text(w // 2, 252, "not the model", 46, TEXT, SERIF, weight="700"))
    for j, line in enumerate(_wrap(tagline, 64)[:2]):
        body.append(_text(w // 2, 300 + j * 26, line, 16, SOFT))

    n = len(types) or 1
    col = 860 / n
    for i, t in enumerate(types):
        cx = (w - 860) / 2 + col * i + col / 2
        body.append('<g transform="translate(%.1f,360) scale(1.5)">%s</g>'
                    % (cx - 45, inline_vessel(t["id"])))
        body.append(_text(cx, 512, t["label"], 17, TEXT, SERIF, weight="700"))
        body.append(_text(cx, 532, t.get("label_en", ""), 11, FAINT, MONO))
    body.append(_text(w // 2, 578, "six aptitudes, after the Water Divination in HUNTER x HUNTER",
                      13, FAINT))
    return _svg(w, h, "\n".join(body), "%s — measure the operator, not the model" % repo_name)


# ---------------------------------------------------------------- write

def load_types(lang, cfg=None):
    """The six, as the pattern files currently define them. Nothing about them is hardcoded."""
    cfg = cfg or corpus.load_config()
    order = (["patterns/%s.json" % lang]
             + [p for p in cfg["patterns"] if not p.endswith("/%s.json" % lang)])
    pats = signals.load_patterns(order)
    return [{"id": tid,
             "label": signals.type_meta(pats, tid, "label", tid),
             "label_en": signals.type_meta(pats, tid, "label_en", ""),
             "reaction": signals.type_meta(pats, tid, "reaction", "")}
            for tid in signals.type_order(pats)]


def tagline_for(lang):
    return ("Read your own messages back to you and name which of six aptitudes "
            "your instructions actually show" if lang == "en" else
            "自分の発話を読み返し、指示が実際に示している6系統のどれかを名指しする")


def build(out_dir, lang, cfg=None):
    types = load_types(lang, cfg)
    suffix = "" if lang == "en" else ".%s" % lang
    tagline = tagline_for(lang)
    files = {
        "six-vessels%s.svg" % suffix: six_vessels(types),
        "six-axes%s.svg" % suffix: six_axes(types, lang=lang),
        "gate%s.svg" % suffix: gate(lang=lang),
        "social-preview%s.svg" % suffix: social_preview(types, "agent-water-divination", tagline),
    }
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for name, svg in files.items():
        path = os.path.join(out_dir, name)
        # LF on every platform: CI regenerates these and compares against the committed copies,
        # and a line-ending difference would read as "the diagram is out of date".
        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(svg)
        written.append(path)
    return written


# ---------------------------------------------------------------- the bitmap card
# GitHub's social preview slot takes PNG or JPG, never SVG, so one bitmap has to exist. Rendering
# the SVG would mean a rasterizer; drawing the card directly needs only Pillow, and Pillow is
# optional -- `assets/social-preview.png` is committed, so nobody has to install anything to use
# this repo. The SVG stays the source of truth for the diagram; the PNG is the card, and simpler
# on purpose (no shimmer, no sediment -- detail that vanishes at thumbnail size anyway).

CARD_FONTS = [
    "C:/Windows/Fonts/YuGothM.ttc", "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/segoeui.ttf",
    "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def _font(size):
    from PIL import ImageFont
    for path in CARD_FONTS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def render_card(types, png_path, repo_name, tagline, w=1280, h=640):
    """Draw the social preview directly. Returns the path, or None if Pillow is not installed."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    img = Image.new("RGB", (w, h), INK)
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, w - 41, h - 41], fill=SURFACE, outline=LINE)

    def centred(y, text, size, fill):
        f = _font(size)
        d.text((w // 2, y), text, font=f, fill=fill, anchor="ma")

    centred(104, repo_name, 22, WATER)
    centred(160, "Measure the operator,", 46, TEXT)
    centred(212, "not the model", 46, TEXT)
    for j, line in enumerate(_wrap(tagline, 62)[:2]):
        centred(288 + j * 28, line, 17, SOFT)

    n = len(types) or 1
    col = 880 / n
    for i, t in enumerate(types):
        cx = (w - 880) / 2 + col * i + col / 2
        top, bot, half = 372, 470, 27
        # the glass: a tapered outline, water filling the lower two thirds
        d.polygon([(cx - 18, 412), (cx + 18, 412), (cx + 14, bot), (cx - 14, bot)], fill=FILL)
        d.line([(cx - half, top), (cx - 14, bot), (cx + 14, bot), (cx + half, top)],
               fill=GLASS, width=2, joint="curve")
        if t["id"] == "sousa":                       # the leaf, the reaction it is named for
            d.ellipse([cx - 13, 406, cx + 13, 418], fill=LEAF)
        d.text((cx, 500), t["label"], font=_font(20), fill=TEXT, anchor="ma")
        d.text((cx, 528), t.get("label_en", ""), font=_font(13), fill=FAINT, anchor="ma")

    centred(576, "six aptitudes, after the Water Divination in HUNTER x HUNTER", 14, FAINT)
    img.save(png_path)
    return png_path


# ---------------------------------------------------------------- self-test

def _png_size(path):
    """Read a PNG's dimensions from its IHDR, so the check needs no image library either."""
    import struct
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def _self_test():
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(("PASS  " if cond else "FAIL  ") + label + ("  " + detail if detail else ""))

    with tempfile.TemporaryDirectory() as tmp:
        written = build(tmp, "en")
        check("four assets are written", len(written) == 4, str([os.path.basename(p)
                                                                 for p in written]))
        blobs = {os.path.basename(p): io.open(p, encoding="utf-8").read() for p in written}

        for name, svg in blobs.items():
            bare = svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
            check("%s references nothing external" % name,
                  "http://" not in bare and "https://" not in bare)
            check("%s paints an opaque background" % name, svg.count('<rect width=') >= 1)
            check("%s keeps no CSS classes a renderer could strip" % name, "class=" not in svg)

        vessels = blobs["six-vessels.svg"]
        check("every type from the pattern files is drawn",
              all(k in vessels for k in ("Enhancer", "Emitter", "Transmuter",
                                         "Conjurer", "Manipulator", "Specialist")))
        check("the vessel geometry is the report's, not a copy",
              report.GLASS_BODY.split('d="')[1][:20] in vessels)
        check("the social preview is the size GitHub asks for",
              'width="1280" height="640"' in blobs["social-preview.svg"])
        check("the gate diagram states the refusal",
              "NO VERDICT" in blobs["gate.svg"])
        axes_svg = blobs["six-axes.svg"]
        check("the axes diagram is drawn from the catalogue the code counts from",
              all(label in axes_svg for _a, _t, label, _u, _d in signals.axis_catalogue()))
        check("the axes diagram names each axis's own denominator",
              all(unit in axes_svg for _a, _t, _l, unit, _d in signals.axis_catalogue()))
        check("a type owning two axes gets a row for each",
              len(signals.axes_of("sousa")) == 2
              and all(signals.AXES[a][1] in axes_svg for a in signals.axes_of("sousa")))
        check("the type with no axis is shown as the leftover, not as a blank row",
              "do not explain" in axes_svg)
        # a diagram that drops the tail of its own sentence is the failure this guards
        check("the refusal sentence is drawn whole, not truncated",
              "the verdict goes too" in blobs["gate.svg"])
        for name, svg in blobs.items():
            height = int(re.search(r'viewBox="0 0 \d+ (\d+)"', svg).group(1))
            lowest = max(float(y) for y in re.findall(r'<text x="[^"]+" y="([\d.]+)"', svg))
            check("%s draws nothing below its own canvas" % name, lowest < height,
                  "lowest text y=%.0f canvas=%d" % (lowest, height))
        check("the source of the six types is credited",
              "HUNTER" in blobs["social-preview.svg"])

        ja = build(tmp, "ja")
        jab = io.open([p for p in ja if "six-vessels.ja" in p][0], encoding="utf-8").read()
        check("a second language writes its own files, wording and all",
              "強化系" in jab and "水の量が増える" in jab)

        # the point of generating rather than drawing: rename a type, the picture follows
        import json
        forked = os.path.join(tmp, "patterns")
        os.makedirs(forked)
        src = os.path.join(corpus.REPO_ROOT, "patterns", "en.json")
        data = json.load(io.open(src, encoding="utf-8"))
        data["types"]["kyouka"]["label_en"] = "Ballast"
        data["types"]["kyouka"]["reaction"] = "the glass gets heavier"
        with io.open(os.path.join(forked, "en.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)
        saved = corpus.REPO_ROOT
        try:
            corpus.REPO_ROOT = tmp
            out2 = os.path.join(tmp, "forked-assets")
            build(out2, "en", cfg=dict(corpus.DEFAULTS, patterns=["patterns/en.json"]))
            forked_svg = io.open(os.path.join(out2, "six-vessels.svg"), encoding="utf-8").read()
        finally:
            corpus.REPO_ROOT = saved
        # long reactions are wrapped across lines, so match a word rather than the whole string
        check("renaming a type in the pattern file changes the diagram",
              "Ballast" in forked_svg and "heavier" in forked_svg
              and "Enhancer" not in forked_svg)

        check("text from the pattern files is escaped",
              "&amp;" in six_vessels([{"id": "x", "label": "A & B", "label_en": "",
                                       "reaction": ""}]))

        # The bitmap card is optional: Pillow is not a dependency of this repo, and the PNG it
        # makes is committed. Where Pillow is missing the feature must decline, not crash.
        png = os.path.join(tmp, "card.png")
        made = render_card(load_types("en"), png, "agent-water-divination", tagline_for("en"))
        try:
            import PIL  # noqa: F401
            have_pillow = True
        except ImportError:
            have_pillow = False
        if have_pillow:
            check("the card renders at the size GitHub asks for", made and _png_size(png)
                  == (1280, 640), str(_png_size(png)) if made else "not written")
            check("the card is a real image, not an empty file",
                  os.path.getsize(png) > 5000, "%d bytes" % os.path.getsize(png))
        else:
            check("without Pillow the card declines instead of crashing", made is None)

    print("\n%s" % ("ALL PASS" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="generate the repo's diagrams from patterns/*.json")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--lang", default="en", help="which pattern file supplies the wording")
    ap.add_argument("--out", default="assets")
    ap.add_argument("--png", action="store_true",
                    help="also rasterize the social preview, if a headless browser is installed")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    out_dir = corpus.resolve(args.out)
    written = build(out_dir, args.lang)
    print("[nen-assets] alive: version=%s lang=%s wrote=%d"
          % (ASSETS_VERSION, args.lang, len(written)))
    for p in written:
        print("  %s  %d bytes" % (p, os.path.getsize(p)))

    if args.png:
        svg = next(p for p in written if "social-preview" in p)
        png = re.sub(r"\.svg$", ".png", svg)
        made = render_card(load_types(args.lang), png, "agent-water-divination",
                           tagline_for(args.lang))
        if made:
            print("  %s  %d bytes" % (made, os.path.getsize(made)))
        else:
            print("  --png needs Pillow (pip install pillow). The committed PNG is already in")
            print("  assets/, so this is only needed if you changed the types or the wording.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
