# -*- coding: utf-8 -*-
"""nen_report — render a divination result as one self-contained HTML page.

No network, no CDN, no build step: system fonts and inline SVG only, so the file still reads
correctly on a machine that is offline or behind a proxy. Everything from the transcript is
HTML-escaped -- the input is arbitrary text the operator typed, including angle brackets.

The page renders both states of a divination and never confuses them:

  provisional  measured, not yet confirmed. The open questions are printed as the page's
               main content, because at that stage they *are* the finding.
  confirmed    the interview happened; the verdict, the answers that unlocked it, and the
               quotes it rests on are shown together.

Self-test: python tools/nen_report.py --self-test
"""
import argparse
import html
import io
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPORT_VERSION = "1"

# Which reaction the water shows, per the original test. Unknown ids get a still glass.
GLASS = {
    "kyouka": '<path class="w" d="M13 18 L47 18 L42 74 L18 74 Z"/>',
    "houshutsu": '<path class="w" d="M14 30 L46 30 L42 74 L18 74 Z" opacity=".55"/>',
    "henka": ('<path class="w" d="M14 30 L46 30 L42 74 L18 74 Z"/>'
              '<path class="sh" d="M17 40 q4 -4 8 0 t8 0 t8 0"/>'
              '<path class="sh" d="M18 52 q4 -4 8 0 t8 0 t7 0"/>'),
    "gugenka": ('<path class="w" d="M14 30 L46 30 L42 74 L18 74 Z"/>'
                '<circle class="sp" cx="26" cy="45" r="1.4"/>'
                '<circle class="sp" cx="34" cy="58" r="1.1"/>'),
    "sousa": ('<path class="w" d="M14 30 L46 30 L42 74 L18 74 Z"/>'
              '<g class="spin"><ellipse class="lf" cx="30" cy="30" rx="8" ry="3.2"/></g>'),
    # the leaf withers and breaks up -- in the original this is the one reaction that is not a
    # change in the water at all, which is why it reads as its own category rather than a degree
    "tokushitsu": ('<path class="w" d="M14 30 L46 30 L42 74 L18 74 Z"/>'
                   '<ellipse class="sp" cx="29" cy="30" rx="7" ry="2.4"'
                   ' transform="rotate(-18 29 30)"/>'
                   '<circle class="sp" cx="36" cy="44" r="1.3" opacity=".85"/>'
                   '<circle class="sp" cx="24" cy="57" r="1.6" opacity=".7"/>'),
}
GLASS_BODY = '<path class="g" d="M12 8 L18 74 L42 74 L48 8"/>'

CSS = """
:root{--ground:#e6ebeb;--surface:#f4f7f6;--surface2:#dde5e5;--line:#c2cfcf;--text:#16211f;
--soft:#4d5f5c;--faint:#7b8a87;--water:#14707c;--fill:#7fc3c9;--leaf:#5f8a33;--rust:#a44a34;
--sand:#a4967a;--glass:#6f8a8a}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--ground:#0b1315;
--surface:#101b1d;--surface2:#16262a;--line:#26383c;--text:#e3ecea;--soft:#9db0ad;--faint:#6e8380;
--water:#4fc2cc;--fill:#1d5a63;--leaf:#9ac25f;--rust:#d9765c;--sand:#b7a888;--glass:#4b6469}}
:root[data-theme="dark"]{--ground:#0b1315;--surface:#101b1d;--surface2:#16262a;--line:#26383c;
--text:#e3ecea;--soft:#9db0ad;--faint:#6e8380;--water:#4fc2cc;--fill:#1d5a63;--leaf:#9ac25f;
--rust:#d9765c;--sand:#b7a888;--glass:#4b6469}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--text);line-height:1.8;
font-family:system-ui,"Hiragino Sans","Yu Gothic UI",Meiryo,sans-serif;font-size:16px}
.wrap{max-width:47rem;margin:0 auto;padding:3.5rem 1.4rem 5rem;display:flex;flex-direction:column;
gap:3.5rem}
h1,h2,h3{margin:0;text-wrap:balance;font-family:Georgia,"Hiragino Mincho ProN","Yu Mincho",serif}
h1{font-size:clamp(2rem,6vw,2.9rem);line-height:1.25}
h1 .sub{display:block;font-size:.36em;color:var(--water);margin-top:.6rem;letter-spacing:.08em;
font-family:system-ui,sans-serif}
h2{font-size:1.35rem;margin-bottom:.3rem}
.eyebrow{font-family:ui-monospace,"Cascadia Mono",Consolas,monospace;font-size:.7rem;
letter-spacing:.16em;text-transform:uppercase;color:var(--faint);margin:0}
.note{color:var(--soft);font-size:.9rem;margin:0 0 1.5rem}
.lede{color:var(--soft);max-width:34rem;margin:0}
.verdict-line{margin:0;font-family:Georgia,"Hiragino Mincho ProN","Yu Mincho",serif;
font-size:clamp(1.3rem,3.6vw,1.9rem);line-height:1.4}
.verdict-line b{color:var(--water);display:block;font-size:1.5em;margin-top:.2rem}
.because{margin:.5rem 0 0;font-family:ui-monospace,monospace;font-size:.78rem;color:var(--faint)}
.crown{display:flex;gap:1.6rem;align-items:center;flex-wrap:wrap;background:var(--surface);
border:1px solid var(--line);padding:1.6rem 1.8rem}
.crown .big{width:8.5rem;flex:0 0 auto}
.crown .big svg{width:100%;height:auto}
.crown .say{flex:1 1 18rem;min-width:15rem;display:flex;flex-direction:column;gap:.5rem}
.crown .say h3{font-size:1.5rem}
.crown .say p{margin:0;color:var(--soft);font-size:.93rem;line-height:1.8}
.radar{width:100%;max-width:23rem;height:auto}
.radar .ring{fill:none;stroke:var(--line);stroke-width:1}
.radar .spoke{stroke:var(--line);stroke-width:1}
.radar .shape{fill:var(--water);fill-opacity:.22;stroke:var(--water);stroke-width:2;
stroke-linejoin:round}
.radar .dot{fill:var(--water)}
.radar .dot.lit{fill:var(--leaf);r:5}
.radar .rl{font-family:Georgia,"Hiragino Mincho ProN","Yu Mincho",serif;font-size:13px;
fill:var(--text)}
.radar .rl.lit{fill:var(--leaf);font-weight:700}
.radar .rv{font-family:ui-monospace,monospace;font-size:10px;fill:var(--faint)}
.shapewrap{display:flex;gap:1.5rem;align-items:center;flex-wrap:wrap}
.shapewrap .side{flex:1 1 15rem;min-width:14rem;color:var(--soft);font-size:.9rem}
.strengths{display:flex;flex-direction:column;gap:1px;background:var(--line);
border:1px solid var(--line)}
.st{background:var(--surface);padding:1.1rem 1.3rem;display:flex;gap:1.2rem;align-items:baseline}
.st .n{font-family:ui-monospace,monospace;font-size:1.6rem;color:var(--water);
font-variant-numeric:tabular-nums;min-width:4.2rem}
.st h3{font-size:1.15rem;margin:0}
.st h3 small{font-family:ui-monospace,monospace;font-size:.62rem;color:var(--faint);
margin-left:.5rem}
.st p{margin:.35rem 0 0;color:var(--soft);font-size:.9rem;line-height:1.75}
.mine{margin:0;font-size:1rem;line-height:1.85;color:var(--text)}
.card .def{margin:0;font-size:.78rem;color:var(--faint)}
.verdict-line span{display:block;font-family:ui-monospace,monospace;font-size:.72rem;
color:var(--faint);margin-top:.35rem;letter-spacing:.02em}
.state{display:inline-block;font-family:ui-monospace,monospace;font-size:.66rem;letter-spacing:.14em;
padding:.15rem .55rem;border:1px solid var(--line);color:var(--soft)}
.state.confirmed{border-color:var(--water);color:var(--water)}
.state.provisional{border-color:var(--sand);color:var(--sand)}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(8rem,1fr));gap:1px;
background:var(--line);border:1px solid var(--line);margin:0}
.fact{background:var(--surface);padding:.8rem 1rem}
.fact dt{font-family:ui-monospace,monospace;font-size:.64rem;letter-spacing:.1em;color:var(--faint);
text-transform:uppercase}
.fact dd{margin:.1rem 0 0;font-family:ui-monospace,monospace;font-size:1.1rem;
font-variant-numeric:tabular-nums}
.fact dd small{font-family:inherit;font-size:.7rem;color:var(--faint);margin-left:.3rem}
.glasses{display:grid;grid-template-columns:repeat(6,1fr);gap:.5rem;padding:1.6rem 1rem 1.1rem;
background:var(--surface);border:1px solid var(--line);overflow-x:auto}
@media(max-width:40rem){.glasses{grid-template-columns:repeat(3,1fr);row-gap:1.4rem}}
.vessel{display:flex;flex-direction:column;align-items:center;gap:.45rem;text-align:center}
.vessel svg{width:100%;max-width:4.3rem;height:auto}
.vessel .nm{font-family:Georgia,"Hiragino Mincho ProN","Yu Mincho",serif;font-size:.9rem;
font-weight:700}
.vessel .rx{font-size:.66rem;color:var(--faint);line-height:1.5}
.vessel.main .nm{color:var(--water)}
.vessel.main::after{content:attr(data-tag);font-family:ui-monospace,monospace;font-size:.56rem;
letter-spacing:.08em;color:var(--ground);background:var(--water);padding:.1rem .38rem}
.g{fill:none;stroke:var(--glass);stroke-width:1.6;stroke-linejoin:round}
.w{fill:var(--fill)}.lf{fill:var(--leaf)}.sp{fill:var(--sand)}
.sh{fill:none;stroke:var(--surface);stroke-width:1.2}
.spin{transform-origin:30px 34px;animation:spin 9s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.spin{animation:none}}
.cards{display:flex;flex-direction:column;gap:1.15rem}
.card{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--line);
padding:1.4rem 1.5rem;display:flex;flex-direction:column;gap:.9rem}
.card.main{border-left-color:var(--water)}
.card.thin{border-left-color:var(--rust)}
.card.unresolved{border-left-color:var(--sand)}
.card-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:.4rem .9rem}
.card-head h3{font-size:1.25rem}
.card-head .en{font-size:.78rem;color:var(--faint);font-family:ui-monospace,monospace}
.def{margin:-.5rem 0 0;font-size:.85rem;color:var(--faint)}
.bars{display:flex;flex-direction:column;gap:.35rem}
.bar{display:grid;grid-template-columns:9rem 1fr 5rem;align-items:center;gap:.7rem;font-size:.77rem}
@media(max-width:34rem){.bar{grid-template-columns:6.5rem 1fr 4.2rem}}
.bar .k{font-family:ui-monospace,monospace;font-size:.69rem;color:var(--soft);overflow:hidden;
text-overflow:ellipsis;white-space:nowrap}
.bar .t{height:.48rem;background:var(--surface2);position:relative}
.bar .f{position:absolute;inset:0 auto 0 0;background:var(--water)}
.bar .f.zero{width:2px;background:var(--rust)}
.bar .v{font-family:ui-monospace,monospace;font-variant-numeric:tabular-nums;text-align:right;
font-size:.73rem}
blockquote{margin:0;padding:.85rem 1rem;background:var(--surface2);border-left:2px solid var(--leaf);
font-size:.92rem;line-height:1.75}
blockquote cite{display:block;margin-top:.45rem;font-style:normal;font-family:ui-monospace,monospace;
font-size:.65rem;color:var(--faint)}
.read{margin:0;font-size:.89rem;color:var(--soft)}
.axis{background:var(--surface2);padding:.8rem 1rem;display:flex;flex-direction:column;gap:.2rem}
.axis .tag{font-family:ui-monospace,monospace;font-size:.6rem;letter-spacing:.14em;
color:var(--water)}
.axis-n{margin:0;font-family:ui-monospace,monospace;font-size:1.3rem;
font-variant-numeric:tabular-nums;color:var(--text)}
.axis-n span{font-family:inherit;font-size:.74rem;color:var(--faint)}
.axis-n.thin{font-size:.95rem;color:var(--faint)}
.finds{display:flex;flex-direction:column;gap:1rem}
.find{background:var(--surface);border:1px solid var(--leaf);padding:1.2rem 1.3rem;
display:flex;flex-direction:column;gap:.55rem;position:relative}
.find h3{font-size:1.1rem}
.find .count{position:absolute;top:1.1rem;right:1.3rem;font-family:ui-monospace,monospace;
font-size:.72rem;color:var(--leaf)}
table{border-collapse:collapse;width:100%;background:var(--surface);font-size:.85rem}
.scroll{overflow-x:auto;border:1px solid var(--line)}
th,td{padding:.65rem .85rem;text-align:left;border-bottom:1px solid var(--line)}
th{font-family:ui-monospace,monospace;font-size:.63rem;letter-spacing:.1em;text-transform:uppercase;
color:var(--faint);font-weight:400}
td.num{font-family:ui-monospace,monospace;font-variant-numeric:tabular-nums;white-space:nowrap}
tr:last-child td{border-bottom:none}
.qs{display:flex;flex-direction:column;gap:1px;background:var(--line);border:1px solid var(--line)}
.q{background:var(--surface);padding:1rem 1.2rem;display:flex;flex-direction:column;gap:.3rem}
.q .tag{font-family:ui-monospace,monospace;font-size:.62rem;letter-spacing:.1em;color:var(--faint)}
.q.block .tag{color:var(--rust)}
.q .ask{font-size:.95rem}
.q .why,.q .ans{font-size:.83rem;color:var(--soft);margin:0}
.q .ans{border-left:2px solid var(--water);padding-left:.7rem}
footer{border-top:1px solid var(--line);padding-top:1.3rem;font-size:.76rem;color:var(--faint);
display:flex;flex-direction:column;gap:.35rem}
code{font-family:ui-monospace,"Cascadia Mono",Consolas,monospace;font-size:.95em;color:var(--soft)}
"""

E = html.escape

RADAR_R = 108        # outer ring
RADAR_PAD = 74       # room for the labels outside it


def _radar(rows, named=None):
    """Six spokes, one shape. No sample-size gate touches this: a profile always has a shape,
    and the shape is the thing a divination is for."""
    if not rows:
        return ""
    import math
    n = len(rows)
    cx = cy = RADAR_R + RADAR_PAD
    size = 2 * (RADAR_R + RADAR_PAD)

    def point(i, frac):
        a = -math.pi / 2 + 2 * math.pi * i / n
        return (cx + RADAR_R * frac * math.cos(a), cy + RADAR_R * frac * math.sin(a))

    out = ['<svg viewBox="0 0 %d %d" class="radar" role="img" aria-label="%s">'
           % (size, size, E("六系統のかたち"))]
    for ring in (0.25, 0.5, 0.75, 1.0):
        pts = " ".join("%.1f,%.1f" % point(i, ring) for i in range(n))
        out.append('<polygon points="%s" class="ring"/>' % pts)
    for i in range(n):
        x, y = point(i, 1.0)
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="spoke"/>'
                   % (cx, cy, x, y))
    shape = " ".join("%.1f,%.1f" % point(i, max(r["scaled"], 0) / 100.0)
                     for i, r in enumerate(rows))
    out.append('<polygon points="%s" class="shape"/>' % shape)
    for i, r in enumerate(rows):
        x, y = point(i, max(r["scaled"], 0) / 100.0)
        out.append('<circle cx="%.1f" cy="%.1f" r="3.5" class="dot%s"/>'
                   % (x, y, " lit" if r["type"] == named else ""))
        lx, ly = point(i, 1.30)
        anchor = "middle" if abs(lx - cx) < 6 else ("start" if lx > cx else "end")
        out.append('<text x="%.1f" y="%.1f" text-anchor="%s" class="rl%s">%s</text>'
                   % (lx, ly, anchor, " lit" if r["type"] == named else "", E(r["label"])))
        out.append('<text x="%.1f" y="%.1f" text-anchor="%s" class="rv">%s</text>'
                   % (lx, ly + 15, anchor,
                      E("—" if r["dark"] else "%s%%" % r["pct"])))
    out.append("</svg>")
    return "".join(out)


def _bar(name, s, scale):
    if s.get("pct") is None:
        return ""
    width = 0 if not s["n"] else max(2.0, min(100.0, 100.0 * s["pct"] / scale))
    cls = "f zero" if s["n"] == 0 else "f"
    style = "" if s["n"] == 0 else ' style="width:%.0f%%"' % width
    return ('<div class="bar"><span class="k">%s</span><span class="t">'
            '<span class="%s"%s></span></span><span class="v">%s%% (%d)</span></div>'
            % (E(name), cls, style, s["pct"], s["n"]))


def render(data):
    """data = measurement + optional `verdict` block. Returns one complete HTML document."""
    verdict = data.get("verdict") or {}
    confirmed = bool(verdict.get("confirmed"))
    roles = verdict.get("roles") or {}
    reads = verdict.get("reads") or {}
    main_id = verdict.get("main")
    title = verdict.get("title") or "Water Divination"

    w = data.get("window", {})
    auth = data["authorship"]
    scale = max([s["pct"] or 0 for t in data["types"] for s in (t["signals"] or {}).values()]
                + [1.0])

    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width,initial-scale=1">',
           "<title>%s</title><style>%s</style></head><body><div class='wrap'>" % (E(title), CSS)]

    out.append("<header style='display:flex;flex-direction:column;gap:1.1rem'>")
    out.append("<p class='eyebrow'>Water Divination &nbsp;/&nbsp; %s &rarr; %s</p>"
               % (E(w.get("from", "?")), E(w.get("to", "?"))))
    out.append("<h1>%s<span class='sub'>%s</span></h1>"
               % (E(title), E(verdict.get("subtitle")
                              or "Measuring the person directing the AI, not the AI")))
    # The page leads with a name, the way the reading does. A page whose first statement is
    # "interview not complete" is a form, and nobody reads their own divination as a form.
    axes = (data.get("effects") or {}).get("axes") or {}
    label_of = {t["id"]: t["label"] for t in data["types"]}
    en_of = {t["id"]: t["label_en"] for t in data["types"]}
    # axes is keyed by axis id and a type may own several; older results omit the type field,
    # in which case the key is the type
    typed = [(a.get("type", k), a) for k, a in axes.items()]
    reacted = sorted([(t, a) for t, a in typed if a.get("direction") == "for"],
                     key=lambda p: -(p[1].get("lift") or 0))
    lead = next((a for t, a in typed if t == main_id), None) if confirmed \
        else (reacted[0][1] if reacted else None)
    named = main_id if confirmed else (reacted[0][0] if reacted else None)

    # The reading always names something. Confidence and basis carry the rigour; a page that
    # refuses to say anything about the person is not a reading, whatever its statistics.
    rd = data.get("reading") or {}
    if not named and rd.get("type"):
        named, lead = rd["type"], None
    if named:
        out.append("<p class='verdict-line'>%s<b>%s</b></p>"
                   % ("あなたは " if confirmed else "水はこう動いた — ",
                      E("%s / %s" % (label_of.get(named, named), en_of.get(named, "")))))
        because = (("%s, %s%% against %s%%" % (lead["label"], lead["pct"], lead["base_pct"]))
                   if lead and lead.get("base_pct") is not None else rd.get("because", ""))
        if because:
            out.append("<p class='because'>%s</p>" % E(because))
    conf = {"firm": "はっきり出た", "provisional": "出ているが、まだ薄い",
            "tentative": "かすかに動いた"}.get(rd.get("confidence"), "")
    basis = {"axis": "効果で測れた", "quotes": "あなた自身の言葉から"}.get(rd.get("basis"), "")
    out.append("<p><span class='state %s'>%s</span></p>"
               % ("confirmed" if confirmed else "provisional",
                  "CONFIRMED" if confirmed
                  else E("%s — %s" % (conf, basis)) if conf else "not settled"))
    if verdict.get("summary"):
        out.append("<p class='lede'>%s</p>" % E(verdict["summary"]))
    out.append("<dl class='facts'>")
    for label, value, sub in (
            ("your messages", data["own"], "of %d read" % data["scanned"]),
            ("sessions", data["sessions"], ""),
            ("pastes excluded", auth["paste_suspect"]["n"],
             "%s%%" % auth["paste_suspect"]["pct"]),
            ("median length", data["length"]["median"], "chars")):
        out.append("<div class='fact'><dt>%s</dt><dd>%s<small>%s</small></dd></div>"
                   % (E(label), E(str(value)), E(sub)))
    out.append("</dl></header>")

    # -- the named type, drawn large, in words meant for this reader ----------
    if named:
        t_big = next((t for t in data["types"] if t["id"] == named), None) or {}
        portrait = (verdict.get("portrait")
                    or "%s あなたの水は、そこで動いた。" % t_big.get("gloss", ""))
        out.append("<section><div class='crown'>")
        out.append("<div class='big'><svg viewBox='0 0 60 80' role='img' aria-label='%s'>"
                   "%s%s</svg></div>"
                   % (E("%s: %s" % (t_big.get("label_en", ""), t_big.get("reaction", ""))),
                      GLASS.get(named, ""), GLASS_BODY))
        out.append("<div class='say'><h3>%s</h3><p>%s</p><p style='color:var(--faint);"
                   "font-size:.8rem'>%s</p></div>"
                   % (E("%s / %s" % (t_big.get("label", named), t_big.get("label_en", ""))),
                      E(portrait), E("器の反応: %s" % t_big.get("reaction", ""))))
        out.append("</div></section>")

    # -- the strengths, said plainly, before anything qualifies them ----------
    # Ranked by how far the language stands out, not by raw share: "you write this way six times
    # as densely as the model does" is the sentence that makes a profile land.
    prof_sorted = sorted([r for r in (data.get("profile") or []) if not r["dark"]],
                         key=lambda r: (-(r.get("ratio") or 0), -r["pct"]))
    ref = data.get("reference") or {}
    if prof_sorted:
        out.append("<section><h2>突出しているもの</h2>"
                   "<p class='note'>比較対象は<b>%s</b>（%s文字）。1000文字あたりの密度で、"
                   "文章の長さの差を消してある。<b>他の人との比較ではない</b>——"
                   "この道具は他人のコーパスを持っていないので、そこは測れない。</p>"
                   "<div class='strengths'>"
                   % (E(ref.get("_what", "—")), E("{:,}".format(ref.get("_chars", 0)))))
        for r in prof_sorted[:3]:
            t_r = next((t for t in data["types"] if t["id"] == r["type"]), {})
            line = reads.get(r["type"]) or t_r.get("gloss", "")
            big = ("×%.1f" % r["ratio"]) if r.get("ratio") else ("%s%%" % r["pct"])
            sub = ("あなた %s / 相手 %s（1000字あたり）" % (r.get("per_1k"), r.get("ref_per_1k"))
                   if r.get("ratio") else "発話の %s%%" % r["pct"])
            out.append("<div class='st'><span class='n'>%s</span>"
                       "<div><h3>%s <small>%s</small></h3><p>%s</p>"
                       "<p style='color:var(--faint);font-size:.75rem'>%s</p></div></div>"
                       % (E(big), E(r["label"]), E(r["label_en"]), E(line), E(sub)))
        out.append("</div></section>")

    # -- the shape of the six, free of the sample-size machinery --------------
    prof = data.get("profile")
    if prof:
        out.append("<section><h2>六つのかたち</h2><p class='note'>あなたの発話のうち、"
                   "その系統の印を帯びていた割合。<b>効いたかどうかではなく、どこに寄っているか</b>"
                   "——性格の形であって、成績ではない。特質系は認定された回だけ点灯する。</p>"
                   "<div class='shapewrap'>%s<div class='side'>%s</div></div></section>"
                   % (_radar(prof, named),
                      E("最も高い系統を100として他を並べてある。低い系統は弱点ではなく、"
                        "この期間その手をあまり使わなかったということ。"
                        "なお広い語彙を持つ系統は高く出る——各パターンがどれだけ普通の文章に"
                        "当たるかは tools/nen_signals.py --audit-patterns で測れる。")))

    # -- why it came out that way, in the operator's own words ----------------
    # This is what the article did and what the statistics layer had quietly replaced: three
    # things you actually wrote, and one line each on what they show.
    if named:
        t_named = next((t for t in data["types"] if t["id"] == named), None)
        picked, seen = [], set()
        for name, qs in ((t_named or {}).get("quotes") or {}).items():
            for q in qs:
                key = q["text"][:40]
                if key in seen:
                    continue
                seen.add(key)
                picked.append((name, q))
                break
        if picked:
            out.append("<section><h2>あなたの言葉から</h2>"
                       "<p class='note'>%s。原本で前後を読んで確かめたものだけを載せている。</p>"
                       "<div class='finds'>" % E((t_named or {}).get("gloss", "")))
            for name, q in picked[:3]:
                out.append("<article class='find'><h3>%s</h3>"
                           "<blockquote>%s<cite>%s</cite></blockquote></article>"
                           % (E(name), E(q["text"]), E(q["ts"])))
            out.append("</div></section>")

    nm = data.get("next_move")
    if nm:
        out.append("<section><h2>明日ひとつ</h2><div class='qs'><div class='q'>"
                   "<span class='tag'>NEXT</span><p class='ask'>%s</p></div></div></section>"
                   % E(nm["do"]))

    # -- the six vessels ------------------------------------------------------
    out.append("<section><h2>The six vessels</h2><p class='note'>In the original test, which of "
               "six ways the water changes tells you the type. Each glass here shows the reaction "
               "its type is named for.</p><div class='glasses'>")
    for t in data["types"]:
        is_main = confirmed and t["id"] == main_id
        out.append("<div class='vessel%s'%s>" % (" main" if is_main else "",
                                                 " data-tag='MAIN'" if is_main else ""))
        out.append("<svg viewBox='0 0 60 80' role='img' aria-label='%s: %s'>%s%s</svg>"
                   % (E(t["label_en"]), E(t["reaction"]),
                      GLASS.get(t["id"], ""), GLASS_BODY))
        out.append("<span class='nm'>%s</span><span class='rx'>%s</span></div>"
                   % (E(t["label"]), E(t["reaction"])))
    out.append("</div></section>")

    # -- per type -------------------------------------------------------------
    # Strongest first. A reading that walks the canonical order buries what the person came for
    # under four types they barely used.
    order = {r["type"]: i for i, r in enumerate(
        sorted(data.get("profile") or [], key=lambda r: -r["pct"]))}
    if order:
        data = dict(data, types=sorted(data["types"],
                                       key=lambda t: order.get(t["id"], 99)))
    out.append("<section><h2>系統ごと — あなたの場合</h2><p class='note'>Percentages are over your own "
               "messages only. Every quote is a candidate until it has been read in its original "
               "context.</p><div class='cards'>")
    for t in data["types"]:
        role = roles.get(t["id"], "")
        cls = ("main" if role == "main" else "thin" if role == "thin"
               else "unresolved" if not confirmed else "")
        out.append("<article class='card %s'><div class='card-head'><h3>%s</h3>"
                   "<span class='en'>%s</span>%s</div>"
                   % (cls, E(t["label"]), E(t["label_en"]),
                      "<span class='state'>%s</span>" % E(role) if role else ""))
        # The person's own reading of this type comes first and large; the shipped definition is
        # a fallback, and is marked as one so nobody mistakes a definition for a reading.
        mine = reads.get(t["id"])
        if mine:
            out.append("<p class='mine'>%s</p>" % E(mine))
            out.append("<p class='def'>定義: %s</p>" % E(t["gloss"]))
        else:
            out.append("<p class='def'>%s</p>" % E(t["gloss"]))
        if t["signals"] is None:
            out.append("<p class='read'><b>No detector, by design.</b> %s</p>" % E(t["reason"]))
        else:
            out.append("<div class='bars'>")
            for name, s in t["signals"].items():
                out.append(_bar(name, s, scale))
            out.append("</div>")
            shown = set()
            for name, quotes in (t["quotes"] or {}).items():
                for q in quotes:
                    key = q["text"][:40]
                    if key in shown:
                        continue
                    shown.add(key)
                    out.append("<blockquote>%s<cite>%s &nbsp;/&nbsp; %s</cite></blockquote>"
                               % (E(q["text"]), E(q["ts"]), E(name)))
                    break
        # only the axes that reacted are drawn into a type's card; the rest are summarised once,
        # below, because a reading that itemises every reaction the glass did not have is a survey
        for ax in [a for k, a in (data.get("effects", {}).get("axes") or {}).items()
                   if a.get("type", k) == t["id"] and a.get("direction", "for") != "none"]:
            out.append("<div class='axis'>")
            out.append("<span class='tag'>%s</span>"
                       % ("WENT THE OTHER WAY" if ax.get("direction") == "against"
                          else "WHAT IT DID"))
            if ax["enough"]:
                out.append("<p class='axis-n'>%s%% &nbsp;<span>%d of %d %s</span></p>"
                           % (ax["pct"], ax["hits"], ax["n"], E(ax["unit"])))
            else:
                out.append("<p class='axis-n thin'>only %d %s &nbsp;<span>too few to rate</span></p>"
                           % (ax["n"], E(ax["unit"])))
            if ax.get("base_pct") is not None:
                lift = ("%+.1f pts" % ax["lift"]) if ax.get("lift") is not None else "—"
                out.append("<p class='why'>against <b>%s%%</b> for %s (%d) &nbsp;·&nbsp; %s%s</p>"
                           % (ax["base_pct"], E(ax["against"]), ax["base_n"], lift,
                              " &nbsp;<b>— too close to the baseline to mean anything</b>"
                              if ax.get("undiscriminating") else ""))
            elif ax.get("base_n") is not None:
                out.append("<p class='why'>no baseline: only %d %s to compare against</p>"
                           % (ax["base_n"], E(ax["against"])))
            out.append("<p class='why'>%s — %s</p>" % (E(ax["label"]), E(ax["detail"])))
            out.append("</div>")
        out.append("</article>")
    out.append("</div></section>")

    quiet = [(k, a) for k, a in (data.get("effects", {}).get("axes") or {}).items()
             if a.get("direction") == "none"]
    if quiet:
        names = sorted({next((t["label_en"] for t in data["types"]
                              if t["id"] == a.get("type", k)), a.get("type", k))
                        for k, a in quiet})
        out.append("<p class='note' style='margin:-2rem 0 0'>%d axis/axes did not show in this "
                   "window (%s) — too thin, or level with their own baseline. They are not "
                   "weaknesses and they are not homework; the glass simply did not react there. "
                   "Their numbers are in the result JSON.</p>"
                   % (len(quiet), E(", ".join(names))))

    # -- the rare ones --------------------------------------------------------
    eff = data.get("effects") or {}
    if "residual" in eff:
        res = eff["residual"]
        verdict_note = (verdict.get("specialist")
                        or "Not yet read — Specialist is decided by looking at these, not by a "
                           "number the tool produced.")
        out.append("<section><h2>足場 ③ — 五つで説明しきれなかったもの</h2>"
                   "<p class='note'>Specialist is the leftover, so nothing here is scored. Across "
                   "your <b>%d</b> substantive messages the five explain <b>%s%%</b> "
                   "(floor %s%%); %d of the rest were followed by the agent doing work. These are "
                   "the ones whose wording is least like the rest of your own corpus — a reading "
                   "order, not a claim that they are special.</p>"
                   % (res.get("substantive", 0), res.get("recall_pct"),
                      res.get("recall_floor"), res["residual_that_did_something"]))
        if not res.get("usable", True):
            out.append("<div class='qs'><div class='q block'><span class='tag'>NOT EVIDENCE"
                       "</span><p class='ask'>%s</p><p class='why'>Listed below as material to "
                       "read, not as grounds for recognising Specialist.</p></div></div>"
                       % E(res.get("why_unusable") or ""))
        out.append("<p class='read' style='margin:-.8rem 0 1.4rem'><b>%s</b></p>" % E(verdict_note))
        if res["candidates"]:
            out.append("<div class='finds'>")
            for c in res["candidates"]:
                marks = ", ".join(filter(None, [
                    "%d tool calls" % c["tool_calls"] if c["tool_calls"] else "",
                    "left a mechanism" if c["left_a_mechanism"] else "",
                    "agent verified" if c["agent_verified"] else ""]))
                out.append("<article class='find'><h3>%s</h3>"
                           "<span class='count'>%.2f</span>" % (E(c["ts"]), c["unusualness"]))
                out.append("<blockquote>%s<cite>%s</cite></blockquote>"
                           % (E(c["text"]), E(marks)))
                out.append("</article>")
            out.append("</div>")
        else:
            out.append("<div class='qs'><div class='q'><p class='ask'>Nothing left over that did "
                       "anything.</p><p class='why'>The five cover this window. That is an "
                       "ordinary outcome, not a gap.</p></div></div>")
        mr = eff.get("misreads") or {}
        if mr.get("per_100_agent_turns") is not None:
            trend = ""
            if mr.get("first_half") and mr.get("second_half"):
                trend = " — %s then %s per 100 across the window" % (
                    mr["first_half"]["per_100"], mr["second_half"]["per_100"])
            out.append("<p class='read' style='margin-top:1.2rem'>Across %d agent turns, the agent "
                       "admitted misreading you %d times (%s per 100)%s. %s</p>"
                       % (eff.get("assistant_turns", 0), mr["n"], mr["per_100_agent_turns"],
                          E(trend), E(mr.get("note", ""))))
        if eff.get("blind_sources"):
            out.append("<p class='read'>No agent side in: %s — nothing measurable there.</p>"
                       % E(", ".join(eff["blind_sources"])))
        out.append("</section>")

    # -- interview ------------------------------------------------------------
    qs = data.get("open_questions") or []
    answers = data.get("answers") or {}
    if qs:
        out.append("<section><h2>%s</h2><p class='note'>%s</p><div class='qs'>"
                   % ("What the interview settled" if confirmed
                      else "足場 ④ — これに答えると確定する",
                      "A regex cannot tell a missing ability from a missing opportunity, or your "
                      "own words from text you pasted. These were asked directly."))
        for q in qs:
            a = answers.get(q["id"])
            out.append("<div class='q%s'>" % (" block" if q.get("blocking") and not a else ""))
            out.append("<span class='tag'>%s%s</span>"
                       % (E(q["kind"].upper()), " · BLOCKING" if q.get("blocking") else ""))
            out.append("<p class='ask'>%s</p>" % E(q["ask"]))
            out.append("<p class='why'>%s%s</p>"
                       % (E(q["why"]),
                          " — watch for: " + E(q["observe"]) if q.get("observe") else ""))
            if a:
                note = a.get("note") or ""
                out.append("<p class='ans'><b>%s</b>%s</p>"
                           % (E(str(a.get("answer", ""))), " — " + E(note) if note else ""))
            out.append("</div>")
        out.append("</div></section>")

    # -- cross-cutting --------------------------------------------------------
    b = data["borrowed"]
    out.append("<section><h2>足場 ① — 横断の数値</h2><p class='note'>Each metric twice: over every "
               "message extracted, and over your own words only. The gap is pasted text.</p>"
               "<div class='scroll'><table><thead><tr><th>metric</th><th>all extracted</th>"
               "<th>your words only</th></tr></thead><tbody>")
    for key, label in (("correction_oneshot", "corrections that landed in one go"),
                       ("acceptance_in_request", "requests carrying a finish line"),
                       ("telegraphic", "short messages with no resolvable referent")):
        allv, ownv = b[key]["all"], b[key]["own"]
        out.append("<tr><td>%s</td><td class='num'>%s%% (%d/%d)</td>"
                   "<td class='num'>%s%% (%d/%d)</td></tr>"
                   % (E(label), allv["pct"], allv["n"], allv["denom"],
                      ownv["pct"], ownv["n"], ownv["denom"]))
    out.append("</tbody></table></div></section>")

    # -- limits ---------------------------------------------------------------
    out.append("<section><h2>足場 ② — このページを疑うための3点</h2><div class='qs'>")
    for head, body in (
        ("Zero is not absence",
         "A signal at zero can mean the vocabulary missed it. On the corpus this was built "
         "against, one type read 0 until the patterns were widened, then read 3. Widening them "
         "until they match quotes you already chose is fitting the instrument to the answer, so "
         "any remaining zero is printed as zero."),
        ("Pasted text still gets through",
         E(auth["limit"]) + " Being counted as yours is not proof that you wrote it."),
        ("The reader's own habits are in here",
         "Whoever chose these patterns decided what counts as evidence. If that was an agent "
         "that had just read your rules, it will tend to find the things your rules talk about."),
    ):
        out.append("<div class='q'><p class='ask'><b>%s</b></p><p class='why'>%s</p></div>"
                   % (E(head), body))
    out.append("</div></section>")

    out.append("<footer><div>Six types after the Water Divination in Yoshihiro Togashi's "
               "<i>HUNTER&nbsp;&times;&nbsp;HUNTER</i>, re-read as aptitudes of the person "
               "directing an AI.</div>")
    out.append("<div>signals v%s &nbsp;/&nbsp; report v%s &nbsp;/&nbsp; window %s &rarr; %s</div>"
               % (E(data.get("signals_version", "?")), REPORT_VERSION,
                  E(w.get("from", "?")), E(w.get("to", "?"))))
    out.append("</footer></div></body></html>")
    return "\n".join(out)


def _self_test():
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(("PASS  " if cond else "FAIL  ") + label + ("  " + detail if detail else ""))

    data = {
        "signals_version": "1",
        "window": {"from": "2026-08-01T10:00", "to": "2026-08-31T10:00"},
        "own": 40, "scanned": 44, "sessions": 5, "length": {"median": 30, "max": 900},
        "authorship": {"own": 40, "paste_suspect": {"n": 4, "denom": 44, "pct": 9.1},
                       "by_kind": {"structured": 3, "attributed": 1}, "samples": [],
                       "limit": "Plain pasted prose still gets through."},
        "types": [
            {"id": "sousa", "label": "操作系", "label_en": "Manipulator", "gloss": "steering",
             "reaction": "the leaf moves",
             "signals": {"rulemaking": {"n": 6, "denom": 40, "pct": 15.0}},
             "quotes": {"rulemaking": [{"ts": "2026-08-03T10:00", "session": "s",
                                        "source": "fixture", "chars": 30, "paste": None,
                                        "text": "from now on <b>always</b> & forever"}]}},
            {"id": "kyouka", "label": "強化系", "label_en": "Enhancer", "gloss": "holding",
             "reaction": "the water rises",
             "signals": {"constraint": {"n": 26, "denom": 40, "pct": 65.0}}, "quotes": {}},
            {"id": "tokushitsu", "label": "特質系", "label_en": "Specialist", "gloss": "combo",
             "reaction": "the leaf withers", "signals": None, "quotes": {},
             "reason": "no detector by design"},
        ],
        "borrowed": {
            "correction_oneshot": {"all": {"n": 7, "denom": 26, "pct": 26.9},
                                   "own": {"n": 6, "denom": 6, "pct": 100.0}},
            "acceptance_in_request": {"all": {"n": 1, "denom": 10, "pct": 10.0},
                                      "own": {"n": 1, "denom": 9, "pct": 11.1}},
            "telegraphic": {"all": {"n": 2, "denom": 44, "pct": 4.5},
                            "own": {"n": 2, "denom": 40, "pct": 5.0}}},
        "profile": [
            {"type": "sousa", "label": "操作系", "label_en": "Manipulator", "pct": 6.0,
             "hits": 24, "dark": False, "scaled": 100.0},
            {"type": "kyouka", "label": "強化系", "label_en": "Enhancer", "pct": 3.0,
             "hits": 12, "dark": False, "scaled": 50.0},
            {"type": "tokushitsu", "label": "特質系", "label_en": "Specialist", "pct": 0.0,
             "hits": None, "dark": True, "scaled": 0.0},
        ],
        "open_questions": [{"id": "probe_tokushitsu", "kind": "probe", "type": "tokushitsu",
                            "why": "not enough quotes", "ask": "Weave the three ideas into one.",
                            "observe": "does selection happen", "blocking": False}],
        "effects": {
            "assistant_turns": 400,
            "axes": {"sousa": {"label": "rules that became machinery", "unit": "rules declared",
                               "n": 12, "hits": 10, "pct": 83.3, "enough": True,
                               "detail": "Followed by a write into a rule file.",
                               "against": "your other requests", "base_n": 200,
                               "base_pct": 46.3, "lift": 37.0, "undiscriminating": False,
                               "showed": True, "direction": "for", "evidence": []},
                     "sousa_oneshot": {"label": "corrections that landed in one go",
                                       "unit": "corrections carrying a reason", "type": "sousa",
                                       "n": 8, "hits": 7, "pct": 87.5, "enough": True,
                                       "detail": "You said why.", "against": "bare corrections",
                                       "base_n": 4, "base_pct": 100.0, "lift": -12.5,
                                       "undiscriminating": False, "showed": True,
                                       "direction": "against", "evidence": []},
                     "kyouka": {"label": "sessions that held their constraint", "unit": "sessions",
                                "n": 20, "hits": 19, "pct": 95.0, "enough": True,
                                "detail": "No correction after it.",
                                "against": "sessions where you stated no constraint",
                                "base_n": 51, "base_pct": 93.0, "lift": 2.0,
                                "undiscriminating": True, "showed": False,
                                "direction": "none", "evidence": []}},
            "residual": {"messages_examined": 40, "explained_by_the_five": 30,
                         "explained_pct": 75.0, "residual_that_did_something": 4,
                         "substantive": 24, "recall_pct": 29.2, "recall_floor": 50.0,
                         "usable": False,
                         "why_unusable": "The five explain 29.2% of your substantive messages, "
                                         "below the 50.0% floor.",
                         "candidates": [{"ts": "2026-08-09T10:00",
                                         "text": "work the unspecified parts out from <what> I "
                                                 "already said",
                                         "unusualness": 5.71, "tool_calls": 26,
                                         "left_a_mechanism": True, "agent_verified": True}],
                         "note": "n", "how_to_read": "h"},
            "misreads": {"n": 3, "per_100_agent_turns": 0.75,
                         "first_half": {"n": 2, "per_100": 1.0},
                         "second_half": {"n": 1, "per_100": 0.5}, "note": "self-reported only."},
            "blind_sources": ["jsonl"],
        },
    }

    prov = render(data)
    check("the page leads with a name, not with a form",
          "水はこう動いた" in prov and "Manipulator" in prov and "PROVISIONAL" not in prov)
    check("the operator's own words carry the reason",
          "あなたの言葉から" in prov and "from now on" in prov)
    check("the named type is drawn large, with its reaction named",
          "class='crown'" in prov and "the leaf moves" in prov)
    check("a radar of the six is drawn, and it is not a scoreboard",
          "class=\"radar\"" in prov and "性格の形であって、成績ではない" in prov)
    check("the radar marks the named spoke and dims an unrecognised Specialist",
          'class="rl lit">操作系' in prov and ">—</text>" in prov)
    check("the radar needs no sample-size gate to have a shape",
          '<polygon points=' in prov and prov.count("class=\"ring\"") == 4)

    # The failure this replaced: a page that named nothing because no axis reached significance.
    # A glass that shows nothing is a broken divination, so a name is produced either way.
    silent = dict(data)
    silent["effects"] = dict(data["effects"],
                             axes={k: dict(a, direction="none", showed=False)
                                   for k, a in data["effects"]["axes"].items()})
    silent["reading"] = {"type": "sousa", "basis": "quotes", "confidence": "provisional",
                         "headline": "steering", "because": "2 verified quotes"}
    silent["next_move"] = {"do": "write finish lines on the requests that can carry one"}
    page = render(silent)
    check("a name still appears when no axis reached significance",
          "Manipulator" in page and "水はこう動いた" in page, "")
    check("the page says what the name rests on",
          "あなた自身の言葉から" in page and "2 verified quotes" in page)
    check("the reading ends with something to try, not with a number",
          "明日ひとつ" in page and "write finish lines" in page)
    check("open questions are rendered when unanswered", "Weave the three ideas" in prov)
    check("transcript text is escaped, not injected",
          "&lt;b&gt;always&lt;/b&gt; &amp; forever" in prov and "<b>always</b>" not in prov)
    check("no external resource is referenced",
          "http://" not in prov and "https://" not in prov)
    check("all three theme states define the palette",
          prov.count("--ground:") >= 3 and "prefers-color-scheme:dark" in prov)
    check("body paints its own background", "body{margin:0;background:var(--ground)" in prov)
    check("the type with no detector says so", "No detector, by design" in prov)
    check("the source of the six types is credited",
          "HUNTER" in prov and "Togashi" in prov)
    check("each type carries its own effect axis, not a shared one",
          "WHAT IT DID" in prov and "rules that became machinery" in prov)
    check("an axis is shown against its comparison population",
          "46.3%" in prov and "your other requests" in prov and "+37.0 pts" in prov)
    check("a separation the other way is named as one, not folded in with the strengths",
          "WENT THE OTHER WAY" in prov and "corrections that landed in one go" in prov)
    check("an axis that did not show is left out of its type's card",
          "sessions that held their constraint" not in prov)
    check("the ones that did not show are summarised once, as not-weaknesses",
          "did not show in this window" in prov and "not homework" in prov)
    check("the residual is shown with what the agent did about it",
          "work the unspecified parts out from &lt;what&gt; I already said" in prov
          and "left a mechanism" in prov)
    check("the page says how much of you the five actually explain", "29.2%" in prov)
    check("a leftover below the recall floor is marked as not evidence",
          "NOT EVIDENCE" in prov and "below the 50.0% floor" in prov)
    check("Specialist is left to the reader rather than scored",
          "decided by looking at these, not by a number" in prov)
    check("a corpus with no agent side is named as unmeasurable, not as zero effect",
          "No agent side in: jsonl" in prov)
    check("a zero-hit signal renders without a bar width",
          'class="f zero"' in render(dict(data, types=[
              dict(data["types"][0], signals={"x": {"n": 0, "denom": 40, "pct": 0.0}},
                   quotes={})] + data["types"][1:])))

    data2 = dict(data)
    data2["verdict"] = {"confirmed": True, "main": "sousa", "title": "Water Divination",
                        "roles": {"sousa": "main"},
                        "reads": {"sousa": "あなたは断られた時にそれを機構へ移す人です",
                                  "kyouka": "制約は置くが、置いたあとは言い直していません"},
                        "summary": "Manipulator, on evidence."}
    data2["answers"] = {"probe_tokushitsu": {"answer": "pass", "note": "wove them"}}
    conf = render(data2)
    check("confirmed state is stated on the page", "CONFIRMED" in conf and "PROVISIONAL" not in conf)
    check("the main type is marked on its vessel", "data-tag='MAIN'" in conf)
    check("answers are shown beside their questions", "wove them" in conf)
    check("a type's own reading leads its card, with the shipped definition demoted",
          "class='mine'>あなたは断られた時" in conf and "定義: steering" in conf)
    check("the standouts are said plainly, before anything qualifies them",
          conf.index("突出しているもの") < conf.index("系統ごと"))
    check("the standout names its reference and refuses to imply other people",
          "他の人との比較ではない" in conf)
    check("a type with no reading of its own falls back to the definition, unmarked as a reading",
          "class='mine'" in conf and conf.count("class='mine'") == 2)

    print("\n%s" % ("ALL PASS" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="render a divination result as one HTML page")
    ap.add_argument("result", nargs="?", help="JSON produced by water_divination.py")
    ap.add_argument("--out", default="water-divination.html")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()
    if not args.result:
        ap.error("give a result JSON, or --self-test")

    with io.open(args.result, encoding="utf-8") as f:
        data = json.load(f)
    with io.open(args.out, "w", encoding="utf-8") as f:
        f.write(render(data))
    print("[nen-report] alive: wrote=%s bytes=%d" % (args.out, os.path.getsize(args.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
