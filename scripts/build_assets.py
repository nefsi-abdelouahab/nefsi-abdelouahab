"""Generate the animated SVG assets in ../assets for the profile README.

Usage (from the repository root, Python 3.9+, standard library only):

    python scripts/build_assets.py

Edit the data tables below (SKILLS, PROJECTS, FOCUS, BUTTONS) and run the script again; it rewrites
every file in assets/. Then run `python scripts/validate.py` before committing.

Icons: a name in a SKILLS "icons" list is a skillicons.dev id (https://skillicons.dev); prefix it
with "si:" to use a Simple Icons slug (https://simpleicons.org) drawn in the same tile style. Icons
are downloaded on first use and cached in scripts/.cache/ (git-ignored), so a new skill needs no
manual download. A skill with no icon in either set belongs in "chips".

Every asset is self-contained (no scripts, no external fonts, no external images) so it renders when
embedded through <img>. Animations are CSS-only and switch off under prefers-reduced-motion; the
static (no-animation) state of every element is its final, fully visible state.
"""
import html
import pathlib
import re
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
CACHE = ROOT / "scripts" / ".cache" / "icons"
SIMPLE_ICONS_VERSION = "16.38.0"  # pinned so a rebuild draws the same paths
OUT.mkdir(exist_ok=True)

# Palette: the live portfolio (nefsi-abdelouahab.vercel.app, app/globals.css).
P = {
    "navy": "#050816",      # --color-primary
    "s1": "#100D25",        # --color-black-100 (card surface)
    "s2": "#151030",        # --color-tertiary (card surface, lighter)
    "term": "#0B0920",      # terminal body, between navy and s1
    "border": "#362566",    # violet at 30 % over s1
    "violet": "#915EFF",    # the portfolio accent
    "violet_l": "#B794FF",
    "cyan": "#56CCF2",      # blue-text-gradient end
    "blue": "#2F80ED",      # blue-text-gradient start
    "teal": "#00CEA8",      # green-pink-gradient start
    "pink": "#BF61FF",      # green-pink-gradient end
    "text": "#F3F3F3",      # --color-white-100
    "muted": "#AAA6C3",     # --color-secondary
    "chip_text": "#D9D3FF",
    "body": "#CFCBE6",
}

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

CSS_BASE = """
.sans{font-family:%(sans)s}
.mono{font-family:%(mono)s}
.rise{animation:rise .7s cubic-bezier(.22,1,.36,1) both}
.fadein{animation:fadein .6s ease-out both}
.float{animation:float 5s ease-in-out infinite}
.drift{animation:drift 11s ease-in-out infinite alternate}
@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
@keyframes fadein{from{opacity:0}to{opacity:1}}
@keyframes float{0%%,100%%{transform:translateY(0)}50%%{transform:translateY(-2px)}}
@keyframes drift{from{transform:translate(0,0)}to{transform:translate(-26px,16px)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
""" % {"sans": SANS, "mono": MONO}

ICON_CREDIT = "<!-- Tech icons: skillicons.dev (tandpfun/skill-icons, MIT License) and Simple Icons (CC0). -->\n"


def esc(s):
    return html.escape(s, quote=True)


def doc(w, h, title, desc, css, body, comment=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-labelledby="title desc">\n'
        f"{comment}"
        f'<title id="title">{esc(title)}</title>\n'
        f'<desc id="desc">{esc(desc)}</desc>\n'
        f"<style>{CSS_BASE}{css}</style>\n"
        f"{body}\n</svg>\n"
    )


def write(name, content):
    (OUT / name).write_text(content, encoding="utf-8", newline="\n")
    print(f"  wrote assets/{name}  ({len(content.encode('utf-8')):,} bytes)")


def wrap(text, max_chars):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        lines.append(cur)
    if len(lines) == 2:
        # Balance two-line wraps so a single word is never left alone on the second line.
        best = min(range(1, len(words)),
                   key=lambda i: max(len(" ".join(words[:i])), len(" ".join(words[i:]))))
        lines = [" ".join(words[:best]), " ".join(words[best:])]
    return lines


def card_frame(w, h, rx=16, glow=P["violet"], glow_xy=None):
    gx, gy = glow_xy or (w - 30, 10)
    return f"""<defs>
  <linearGradient id="nf-bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{P['s2']}"/><stop offset="1" stop-color="{P['s1']}"/>
  </linearGradient>
  <radialGradient id="nf-glow">
    <stop offset="0" stop-color="{glow}" stop-opacity=".26"/><stop offset="1" stop-color="{glow}" stop-opacity="0"/>
  </radialGradient>
  <clipPath id="nf-card"><rect width="{w}" height="{h}" rx="{rx}"/></clipPath>
</defs>
<g clip-path="url(#nf-card)">
  <rect width="{w}" height="{h}" fill="url(#nf-bg)"/>
  <circle class="drift" cx="{gx}" cy="{gy}" r="130" fill="url(#nf-glow)"/>
</g>
<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="{rx - .5}" fill="none" stroke="{P['border']}"/>"""


# ── Icons ──────────────────────────────────────────────────────────────────────────────────────────
SI_COLORS = {
    "expo": "#FFFFFF",
    "jira": "#2684FF",
    "clickup": "#7B68EE",
    "kaggle": "#20BEFF",
    "langchain": "#FFFFFF",
    "neon": "#00E599",
}


def load_icon(source, name):
    """Return an icon's SVG source, downloading it into scripts/.cache/ on first use."""
    path = CACHE / source / f"{name}.svg"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    url = (f"https://skillicons.dev/icons?i={name}&theme=dark" if source == "skillicons"
           else f"https://cdn.jsdelivr.net/npm/simple-icons@{SIMPLE_ICONS_VERSION}/icons/{name}.svg")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "profile-asset-builder"})
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{source} has no icon named {name!r} (HTTP {e.code}): move it to chips") from e
    except (urllib.error.URLError, TimeoutError) as e:
        reason = getattr(e, "reason", e)
        raise SystemExit(f"could not download the {source} icon {name!r} ({reason}); check the connection "
                         f"and run again. Icons already in {CACHE} are reused.") from e
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return text


def skillicon_inner(name):
    s = load_icon("skillicons", name)
    m = re.search(r'<g transform="translate\(0, 0\)">\s*<svg[^>]*>(.*?)</svg>\s*</g>', s, re.S)
    if not m:
        # skillicons.dev answers an unknown id with an empty 256-byte SVG rather than an error.
        (CACHE / "skillicons" / f"{name}.svg").unlink(missing_ok=True)
        raise SystemExit(f"skillicons.dev has no icon named {name!r}: try 'si:<slug>' or move it to chips")
    return m.group(1).strip()


def simpleicon_inner(name):
    s = load_icon("simple-icons", name)
    d = re.search(r'<path d="([^"]+)"', s).group(1)
    # Same tile as skillicons.dev (256 px, rx 60, #242938) so both sources read as one set.
    return (
        '<rect width="256" height="256" rx="60" fill="#242938"/>'
        f'<path transform="translate(52 52) scale(6.3333)" fill="{SI_COLORS.get(name, "#FFFFFF")}" d="{d}"/>'
    )


def icon(name, x, y, size, pop_delay, float_phase):
    inner = simpleicon_inner(name[3:]) if name.startswith("si:") else skillicon_inner(name)
    return (
        f'<g transform="translate({x:g} {y:g})"><g class="rise" style="animation-delay:{pop_delay:.2f}s">'
        f'<g class="float" style="animation-delay:-{float_phase:.2f}s">'
        f'<svg width="{size}" height="{size}" viewBox="0 0 256 256" fill="none">{inner}</svg>'
        f"</g></g></g>"
    )


# ── Chips ──────────────────────────────────────────────────────────────────────────────────────────
def chip_w(label, fs):
    return len(label) * fs * 0.6 + 22  # monospace: 0.6 em per character, 11 px padding each side


def flow(labels, x0, y0, maxw, fs, gap=7, rowgap=8, h=24):
    rows, cur, curw = [], [], 0.0
    for lab in labels:
        w = chip_w(lab, fs)
        if cur and curw + gap + w > maxw:
            rows.append(cur)
            cur, curw = [], 0.0
        curw = w if not cur else curw + gap + w
        cur.append((lab, w))
    if cur:
        rows.append(cur)
    placed, y = [], y0
    for r in rows:
        x = x0
        for lab, w in r:
            placed.append((x, y, lab, w))
            x += w + gap
        y += h + rowgap
    return placed, (y - rowgap if rows else y0)


def chip(x, y, label, w, delay, fs=11.5, h=24, color=P["violet"], text=P["chip_text"]):
    return (
        f'<g class="fadein" style="animation-delay:{delay:.2f}s">'
        f'<rect x="{x:.1f}" y="{y:g}" width="{w:.1f}" height="{h}" rx="{h / 2:g}" fill="{color}" '
        f'fill-opacity=".12" stroke="{color}" stroke-opacity=".4"/>'
        f'<text x="{x + w / 2:.1f}" y="{y + h / 2 + fs * 0.36:.1f}" text-anchor="middle" class="mono" '
        f'font-size="{fs}" fill="{text}">{esc(label)}</text></g>'
    )


def accent_bar(x, y, w, c1, c2):
    return f"""<defs>
  <linearGradient id="nf-accent" x1="0" x2="1"><stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient>
  <clipPath id="nf-bar"><rect x="{x}" y="{y}" width="{w}" height="3" rx="1.5"/></clipPath>
</defs>
<rect class="fadein" style="animation-delay:.2s" x="{x}" y="{y}" width="{w}" height="3" rx="1.5" fill="url(#nf-accent)"/>
<g clip-path="url(#nf-bar)"><rect class="sheen" x="{x - 18}" y="{y - 1}" width="14" height="5" fill="#FFFFFF" opacity=".75"/></g>"""


# ── Skill cards ────────────────────────────────────────────────────────────────────────────────────
SKILLS = [
    {
        "slug": "languages", "idx": "01", "title": "Languages",
        "groups": [{"icons": ["js", "ts", "py", "java"], "chips": ["SQL"]}],
        "alt": "Languages: JavaScript, TypeScript, Python, Java, SQL",
    },
    {
        "slug": "frontend", "idx": "02", "title": "Frontend",
        "groups": [{"icons": ["react", "nextjs", "si:expo", "tailwind", "html", "css"],
                    "chips": ["React Native", "NativeWind"]}],
        "alt": "Frontend: React, Next.js, React Native, Expo, Tailwind CSS, NativeWind, HTML5, CSS3",
    },
    {
        "slug": "backend", "idx": "03", "title": "Backend",
        "groups": [
            {"icons": ["nodejs", "express"], "chips": ["RESTful APIs"]},
            {"label": "Familiar", "icons": ["laravel", "php"]},
        ],
        "alt": "Backend: Node.js, Express.js, RESTful APIs; familiar with Laravel and PHP",
    },
    {
        "slug": "databases", "idx": "04", "title": "Databases & Cloud",
        "groups": [
            {"label": "Databases", "icons": ["postgres", "mysql", "mongodb", "sqlite", "redis"]},
            {"label": "ORM & cloud", "icons": ["prisma", "supabase", "si:neon"]},
        ],
        "alt": "Databases and cloud: PostgreSQL, MySQL, MongoDB, SQLite, Redis, Prisma, Supabase, Neon",
    },
    {
        "slug": "ai-data", "idx": "05", "title": "AI & Data",
        # Simple Icons only ships Kaggle's wordmark, unreadable at tile size, so Kaggle is a chip.
        "groups": [{"icons": ["si:langchain"],
                    "chips": ["Machine Learning", "Natural Language Processing", "LLMs", "Data Analysis", "Kaggle"]}],
        "network": True,
        "alt": "AI and data: Machine Learning, Natural Language Processing, LLMs, LangChain, Data Analysis, Kaggle",
    },
    {
        "slug": "tools", "idx": "06", "title": "Tools & Practices",
        "groups": [
            {"icons": ["git", "github", "si:jira", "si:clickup", "figma", "linux"],
             "chips": ["API Integration", "Testing", "Debugging", "Agile Scrum",
                       "Specification-Driven Development"]},
            {"label": "AI-assisted development",
             "chips": ["Claude Code", "OpenSpec", "Prompt-Driven Development"]},
        ],
        "alt": ("Tools and practices: Git, GitHub, Jira, ClickUp, Figma, Linux, API Integration, Testing, "
                "Debugging, Agile Scrum, Specification-Driven Development. AI-assisted development: "
                "Claude Code, OpenSpec, Prompt-Driven Development"),
    },
]
SKILL_PAIRS = [("languages", "frontend"), ("backend", "databases"), ("ai-data", "tools")]


def network_glyph(x0, y0, w, h):
    """A decorative animated neural network: five layers, signals travelling left to right."""
    cols = [x0 + w * f for f in (0.03, 0.27, 0.51, 0.75, 0.97)]
    layers = [[0.2, 0.5, 0.8], [0.08, 0.36, 0.64, 0.92], [0.08, 0.36, 0.64, 0.92], [0.2, 0.5, 0.8], [0.5]]
    nodes = [[(cx, y0 + h * fy) for fy in layer] for cx, layer in zip(cols, layers)]
    out = ['<g class="fadein" style="animation-delay:.5s">']
    k = 0
    for li in range(len(nodes) - 1):
        for a in nodes[li]:
            for b in nodes[li + 1]:
                out.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                           f'stroke="{P["violet"]}" stroke-opacity=".28" stroke-width="1"/>')
                out.append(f'<line class="signal" style="animation-delay:{li * 0.55 + (k % 4) * 0.21:.2f}s" '
                           f'x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" stroke="{P["cyan"]}" '
                           f'stroke-width="1.4" stroke-linecap="round" pathLength="100" stroke-dasharray="14 186"/>')
                k += 1
    for li, layer in enumerate(nodes):
        for j, (cx, cy) in enumerate(layer):
            out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.6" fill="{P["s1"]}" stroke="{P["violet_l"]}" stroke-width="1.4"/>')
            out.append(f'<circle class="blink-soft" style="animation-delay:{li * 0.7 + j * 0.2:.2f}s" cx="{cx:.1f}" cy="{cy:.1f}" r="1.6" fill="{P["cyan"]}"/>')
    out.append("</g>")
    return "\n".join(out)


def skill_body(c):
    W, PAD = 400, 22
    parts = [
        f'<g class="rise" style="animation-delay:.05s">'
        f'<text x="{PAD}" y="{PAD + 17}" class="sans" font-size="18" font-weight="700" fill="{P["text"]}">{esc(c["title"])}</text>'
        f'<text x="{W - PAD}" y="{PAD + 15}" text-anchor="end" class="mono" font-size="11" letter-spacing="1.5" fill="{P["violet_l"]}">{c["idx"]}</text>'
        f"</g>",
        accent_bar(PAD, PAD + 28, 40, P["violet"], P["cyan"]),
    ]
    y = PAD + 46
    delay = 0.25
    size = 38
    maxw = W - 2 * PAD
    for gi, g in enumerate(c["groups"]):
        if gi:
            y += 16
        if g.get("label"):
            parts.append(f'<text class="mono fadein" style="animation-delay:{delay:.2f}s" x="{PAD}" y="{y + 9}" '
                         f'font-size="10" letter-spacing="1.4" fill="{P["muted"]}">{esc(g["label"].upper())}</text>')
            y += 18
        icons = g.get("icons", [])
        if icons:
            gap = min(10, (maxw - len(icons) * size) / max(1, len(icons) - 1))
            for i, name in enumerate(icons):
                parts.append(icon(name, PAD + i * (size + gap), y, size, delay, i * 0.45))
                delay += 0.07
            y += size
            if g.get("chips"):
                y += 12
        if g.get("chips"):
            placed, bottom = flow(g["chips"], PAD, y, maxw, 11.5)
            for x, cy, lab, w in placed:
                parts.append(chip(x, cy, lab, w, delay))
                delay += 0.06
            y = bottom
    return "\n".join(parts), y + PAD


SKILL_CSS = """
.sheen{animation:sheen 4.5s ease-in-out 1s infinite}
@keyframes sheen{0%{transform:translateX(0)}55%,100%{transform:translateX(76px)}}
.signal{stroke-dashoffset:100;animation:signal 2.8s linear infinite}
@keyframes signal{from{stroke-dashoffset:100}to{stroke-dashoffset:-100}}
.blink-soft{animation:soft 2.8s ease-in-out infinite}
@keyframes soft{0%,100%{opacity:.35}50%{opacity:1}}
"""


def build_skills():
    bodies = {c["slug"]: skill_body(c) for c in SKILLS}
    heights = {}
    for a, b in SKILL_PAIRS:
        h = max(bodies[a][1], bodies[b][1])
        heights[a] = heights[b] = int(round(h))
    for c in SKILLS:
        body, natural = bodies[c["slug"]]
        h = heights[c["slug"]]
        if c.get("network"):
            # The card is shorter than its pair partner; the illustration fills that space on purpose.
            top, bottom = natural - 22 + 20, h - 22 - 4
            if bottom - top >= 36:
                body += "\n" + network_glyph(22 + 8, top, 400 - 2 * 22 - 16, bottom - top)
        svg = doc(400, h, f"{c['title']} skills", c["alt"], SKILL_CSS,
                  card_frame(400, h) + "\n" + body, ICON_CREDIT)
        write(f"skills-{c['slug']}.svg", svg)
    return {c["slug"]: c["alt"] for c in SKILLS}


# ── Project cards ──────────────────────────────────────────────────────────────────────────────────
PROJECTS = [
    {
        "slug": "presencia", "mono": "P", "title": "Presencia", "subtitle": "Attendance Management System",
        "desc": "An attendance management platform designed around real institutional workflows.",
        "bullets": ["QR-based and manual attendance tracking.", "Real-time attendance monitoring.",
                    "Absence justification workflows.",
                    "Role-based access control and administrative reporting."],
        "stack": ["Next.js", "Django", "Flutter"], "c1": P["violet"], "c2": P["cyan"],
    },
    {
        "slug": "khdamli", "mono": "K", "title": "Khdamli", "subtitle": "Home Services Mobile Application",
        "desc": "A mobile platform connecting customers with skilled service providers in Algeria.",
        "bullets": ["Service listings and provider discovery.", "Job requests and user workflows.",
                    "Developed as part of a six-member ESI-SBA student team."],
        "stack": ["React Native", "TypeScript", "Expo", "NativeWind"], "c1": P["teal"], "c2": P["cyan"],
    },
    {
        "slug": "roeya", "mono": "R", "title": "Roeya", "subtitle": "Media Platform",
        "desc": "A digital media platform focused on news and multimedia content.",
        "bullets": ["Web application development.", "Frontend and backend functionality.",
                    "Content management, search, and filtering."],
        "stack": ["Next.js", "Express.js", "PostgreSQL"], "c1": P["blue"], "c2": P["cyan"],
    },
    {
        "slug": "logistics", "mono": None, "title": "Logistics Management System", "subtitle": None,
        "desc": ("Contributing as a Full-Stack Developer within a development team to a confidential "
                 "business logistics system."),
        "bullets": ["Web and mobile application development.",
                    "Backend and database-driven business workflows.",
                    "Approval, assignment, and commission management.",
                    "Business logic analysis and improvement."],
        "note": "Additional project details are confidential.",
        "stack": ["React", "TypeScript", "React Native", "Laravel"], "c1": P["pink"], "c2": P["violet"],
        "confidential": True,
    },
]
PROJECT_PAIRS = [("presencia", "khdamli"), ("roeya", "logistics")]

LOCK = ('<path d="M7 11V8a5 5 0 0 1 10 0v3" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round"/>'
        '<rect x="5" y="11" width="14" height="10" rx="2.5" fill="none" stroke="{c}" stroke-width="2"/>'
        '<circle cx="12" cy="16" r="1.5" fill="{c}"/>')


def project_body(p):
    W, PAD = 400, 22
    parts = []
    # Monogram tile
    tile = (f'<rect x="{PAD}" y="24" width="42" height="42" rx="12" fill="{p["c1"]}" fill-opacity=".16" '
            f'stroke="{p["c1"]}" stroke-opacity=".55"/>')
    if p["mono"]:
        tile += (f'<text x="{PAD + 21}" y="51.5" text-anchor="middle" class="sans" font-size="19" '
                 f'font-weight="700" fill="{P["text"]}">{p["mono"]}</text>')
    else:
        tile += f'<g transform="translate({PAD + 9} 33)">{LOCK.format(c=P["text"])}</g>'
    title_x = PAD + 56
    ty = 42
    head = [tile, f'<text x="{title_x}" y="{ty}" class="sans" font-size="18" font-weight="700" fill="{P["text"]}">{esc(p["title"])}</text>']
    if p.get("subtitle"):
        head.append(f'<text x="{title_x}" y="{ty + 19}" class="sans" font-size="12.5" fill="{P["muted"]}">{esc(p["subtitle"])}</text>')
    parts.append(f'<g class="rise" style="animation-delay:.05s">{"".join(head)}</g>')

    # Affordance: an arrow in the corner for linkable cards; a pill on the subtitle line for the
    # confidential one (its long title needs the full width of the header row).
    if p.get("confidential"):
        label = "CONFIDENTIAL"
        pw = len(label) * 9.5 * 0.6 + 30
        px, py = title_x, ty + 8
        parts.append(
            f'<g class="fadein" style="animation-delay:.35s">'
            f'<rect x="{px:.1f}" y="{py}" width="{pw:.1f}" height="20" rx="10" fill="{P["pink"]}" fill-opacity=".14" stroke="{P["pink"]}" stroke-opacity=".5"/>'
            f'<g transform="translate({px + 9:.1f} {py + 4}) scale(.5)">{LOCK.format(c=P["chip_text"])}</g>'
            f'<text x="{px + 23:.1f}" y="{py + 13.6}" class="mono" font-size="9.5" letter-spacing=".6" fill="{P["chip_text"]}">{label}</text></g>'
        )
    else:
        parts.append(
            f'<g class="fadein" style="animation-delay:.35s" transform="translate({W - PAD - 16} 26)">'
            f'<path d="M3 13 13 3M5 3h8v8" fill="none" stroke="{P["muted"]}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></g>'
        )

    # Description
    y = 96
    desc_lines = wrap(p["desc"], 50)
    d = [f'<text x="{PAD}" y="{y + i * 19}" class="sans" font-size="13" fill="{P["text"]}" fill-opacity=".92">{esc(line)}</text>'
         for i, line in enumerate(desc_lines)]
    parts.append(f'<g class="rise" style="animation-delay:.15s">{"".join(d)}</g>')
    y += (len(desc_lines) - 1) * 19 + 26

    # Bullets
    delay = 0.3
    for b in p["bullets"]:
        lines = wrap(b.rstrip("."), 50)
        g = [f'<path d="M{PAD + 1} {y - 8} l4 4 -4 4" fill="none" stroke="{p["c2"]}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>']
        for i, line in enumerate(lines):
            g.append(f'<text x="{PAD + 14}" y="{y + i * 18}" class="sans" font-size="12.5" fill="{P["body"]}">{esc(line)}</text>')
        parts.append(f'<g class="rise" style="animation-delay:{delay:.2f}s">{"".join(g)}</g>')
        delay += 0.08
        y += len(lines) * 18 + 4
    if p.get("note"):
        y += 4
        parts.append(f'<text class="sans fadein" style="animation-delay:{delay:.2f}s" x="{PAD}" y="{y}" font-size="11.5" '
                     f'font-style="italic" fill="{P["muted"]}">{esc(p["note"])}</text>')
        y += 14
    return parts, y, delay


def build_projects():
    W, PAD = 400, 22
    built = {p["slug"]: project_body(p) for p in PROJECTS}
    # y is the next free baseline; the last line's descenders end ~18 px above it. Chips start 2 px
    # below y (a 20 px gap), then 24 px of chip and the bottom padding.
    need = {s: b[1] + 2 + 24 + PAD for s, b in built.items()}
    heights = {}
    for a, b in PROJECT_PAIRS:
        heights[a] = heights[b] = int(round(max(need[a], need[b])))
    alts = {}
    for p in PROJECTS:
        parts, _, delay = built[p["slug"]]
        h = heights[p["slug"]]
        chips_y = h - PAD - 24
        placed, _ = flow(p["stack"], PAD, chips_y, W - 2 * PAD, 11)
        chips = [chip(x, cy, lab, w, delay + 0.1 + i * 0.05, fs=11, color=p["c2"]) for i, (x, cy, lab, w) in enumerate(placed)]
        strip = f"""<defs>
  <linearGradient id="nf-strip" x1="0" x2="1"><stop offset="0" stop-color="{p['c1']}"/><stop offset="1" stop-color="{p['c2']}"/></linearGradient>
  <linearGradient id="nf-sheen" x1="0" x2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity="0"/><stop offset=".5" stop-color="#FFFFFF" stop-opacity=".85"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>
</defs>
<g clip-path="url(#nf-card)">
  <rect width="{W}" height="3" fill="url(#nf-strip)"/>
  <rect class="strip-sheen" x="-90" y="0" width="90" height="3" fill="url(#nf-sheen)"/>
</g>"""
        heading = f"{p['title']} — {p['subtitle']}." if p.get("subtitle") else f"{p['title']} (confidential)."
        desc_text = f"{heading} {p['desc']} " + " ".join(p["bullets"])
        if p.get("note"):
            desc_text += " " + p["note"]
        desc_text += " Stack: " + ", ".join(p["stack"]) + "."
        css = """
.strip-sheen{animation:strip 6s ease-in-out 1.2s infinite}
@keyframes strip{0%{transform:translateX(0)}45%,100%{transform:translateX(490px)}}
"""
        body = card_frame(W, h, glow=p["c1"], glow_xy=(W - 20, h - 10)) + "\n" + strip + "\n" + "\n".join(parts) + "\n" + "\n".join(chips)
        write(f"project-{p['slug']}.svg", doc(W, h, p["title"], desc_text, css, body))
        alts[p["slug"]] = desc_text
    return alts


# ── About terminal ─────────────────────────────────────────────────────────────────────────────────
def build_terminal():
    W, FS, LH, PADX = 600, 13, 23, 22
    CW = FS * 0.6
    BAR = 34
    body_top = BAR + 24
    prompt_chars = len("nefsi@esi-sba:~$ ")
    cmd_x = PADX + prompt_chars * CW

    def base(i):
        return body_top + 10 + i * LH

    bullets = [
        "Second-year AI Engineering student at ESI-SBA",
        "Full-stack developer — web & mobile applications",
        "Exploring Machine Learning, NLP, LLMs & AI agent development",
        "Learning to build AI-powered apps with LangChain & modern AI tools",
        "Collaborative development within Agile Scrum teams",
        "Interested in AI research, experimentation & continuous learning",
        "Exploring Data Science via hands-on projects & Kaggle",
    ]
    n_lines = 3 + len(bullets) + 1
    H = int(base(n_lines - 1) + 24)

    def prompt(i):
        # textLength pins the prompt to exactly 16 monospace cells, so the typed command and the cursor
        # land on the same x whatever monospace font the viewer's system substitutes.
        return (f'<text x="{PADX}" y="{base(i):g}" class="mono" font-size="{FS}" textLength="{16 * CW:.1f}" lengthAdjust="spacing">'
                f'<tspan fill="{P["cyan"]}">nefsi@esi-sba</tspan><tspan fill="{P["muted"]}">:</tspan>'
                f'<tspan fill="{P["violet_l"]}">~</tspan><tspan fill="{P["muted"]}">$</tspan></text>')

    css = []
    parts = []
    t = 0.35
    typing = []

    def command(i, cmd, start, cps=0.075, prompt_at=None):
        n = len(cmd)
        dur = n * cps
        width = n * CW
        k = len(typing)
        typing.append((k, width, n, start, dur))
        y = base(i)
        # A later prompt only appears once the previous command has printed its output.
        shown = prompt(i) if prompt_at is None else f'<g class="fadein" style="animation-delay:{prompt_at:.2f}s">{prompt(i)}</g>'
        return (
            shown
            + f'<text x="{cmd_x:.1f}" y="{y:g}" class="mono" font-size="{FS}" fill="{P["text"]}" textLength="{width:.1f}" lengthAdjust="spacing">{esc(cmd)}</text>'
            + f'<rect class="cover{k}" x="{cmd_x - 0.5:.1f}" y="{y - FS - 2:g}" width="{width + 2:.1f}" height="{LH:g}" fill="{P["term"]}"/>'
            + f'<rect class="tcur tcur{k}" x="{cmd_x:.1f}" y="{y - FS + 1:g}" width="{CW:.1f}" height="{FS + 3:g}" fill="{P["cyan"]}" fill-opacity=".85"/>'
        ), start + dur

    c1, t = command(0, "whoami", t)
    parts.append(c1)
    t += 0.2
    y1 = base(1)
    parts.append(
        f'<g class="rise" style="animation-delay:{t:.2f}s"><text x="{PADX}" y="{y1:g}" class="mono" font-size="{FS}">'
        f'<tspan fill="{P["text"]}" font-weight="700">Nefsi Abdelouahab</tspan><tspan fill="{P["muted"]}"> · </tspan>'
        f'<tspan fill="{P["cyan"]}">Timimoun, Algeria</tspan></text></g>'
    )
    t += 0.35
    c2, t = command(2, "cat about.md", t, prompt_at=t - 0.25)
    parts.append(c2)
    t += 0.2
    for j, b in enumerate(bullets):
        y = base(3 + j)
        parts.append(
            f'<g class="rise" style="animation-delay:{t:.2f}s"><text x="{PADX}" y="{y:g}" class="mono" font-size="{FS}">'
            f'<tspan fill="{P["violet"]}">›</tspan><tspan fill="{P["body"]}"> {esc(b)}</tspan></text></g>'
        )
        t += 0.16
    t += 0.15
    last = n_lines - 1
    parts.append(
        f'<g class="fadein" style="animation-delay:{t:.2f}s">{prompt(last)}'
        f'<rect class="blink" x="{cmd_x:.1f}" y="{base(last) - FS + 1:g}" width="{CW:.1f}" height="{FS + 3:g}" fill="{P["cyan"]}"/></g>'
    )
    for k, width, n, start, dur in typing:
        css.append(
            f".cover{k}{{transform:translateX({width + 0.5:.1f}px);animation:type{k} {dur:.2f}s steps({n},end) {start:.2f}s both}}"
            f"@keyframes type{k}{{from{{transform:translateX(0)}}to{{transform:translateX({width + 0.5:.1f}px)}}}}"
            f".tcur{k}{{animation:on {dur + 0.35:.2f}s linear {max(0, start - 0.2):.2f}s,cur{k} {dur:.2f}s steps({n},end) {start:.2f}s both}}"
            f"@keyframes cur{k}{{from{{transform:translateX(0)}}to{{transform:translateX({width:.1f}px)}}}}"
        )
    css.append(".tcur{opacity:0}@keyframes on{from,to{opacity:1}}")
    css.append(".blink{animation:blink 1.1s step-end infinite}@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}")

    frame = f"""<defs>
  <clipPath id="nf-win"><rect width="{W}" height="{H}" rx="14"/></clipPath>
  <linearGradient id="nf-bar-bg" x1="0" x2="1"><stop offset="0" stop-color="{P['s2']}"/><stop offset="1" stop-color="#1B1440"/></linearGradient>
  <radialGradient id="nf-glow"><stop offset="0" stop-color="{P['violet']}" stop-opacity=".18"/><stop offset="1" stop-color="{P['violet']}" stop-opacity="0"/></radialGradient>
</defs>
<g clip-path="url(#nf-win)">
  <rect width="{W}" height="{H}" fill="{P['term']}"/>
  <circle class="drift" cx="{W - 60}" cy="{H - 20}" r="170" fill="url(#nf-glow)"/>
  <rect width="{W}" height="{BAR}" fill="url(#nf-bar-bg)"/>
  <rect y="{BAR}" width="{W}" height="1" fill="{P['border']}"/>
</g>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="13.5" fill="none" stroke="{P['border']}"/>
<circle cx="20" cy="17" r="5.5" fill="#FF5F57"/><circle cx="38" cy="17" r="5.5" fill="#FEBC2E"/><circle cx="56" cy="17" r="5.5" fill="#28C840"/>
<text x="{W / 2:g}" y="21" text-anchor="middle" class="mono" font-size="11.5" fill="{P['muted']}">nefsi@esi-sba: ~ — about.md</text>"""
    # The typing covers are solid term-colour rects, so the drifting glow is kept in the bottom-right
    # corner, well away from the two command lines it would otherwise show through.
    desc = ("Animated terminal. whoami prints: Nefsi Abdelouahab, Timimoun, Algeria. cat about.md prints: "
            + "; ".join(bullets) + ".")
    write("about-terminal.svg", doc(W, H, "About me — terminal", desc, "".join(css), frame + "\n" + "\n".join(parts)))
    return desc


# ── Current focus roadmap ──────────────────────────────────────────────────────────────────────────
FOCUS = [
    ("ML & Data Science", "Deepening my understanding of Machine Learning and Data Science."),
    ("LLMs, RAG & AI Agents", "Exploring LLMs, RAG, and AI Agent architectures."),
    ("AI-Powered Applications", "Building practical AI-powered applications."),
    ("Software Architecture", "Improving software architecture and full-stack engineering skills."),
    ("AI/ML Projects & Research", "Participating in AI/ML projects and research opportunities."),
]


def build_roadmap():
    W, PAD = 500, 26
    node_x, idx_x, text_x = 42, 70, 96
    y = PAD + 14
    nodes, parts = [], []
    for i, (title, detail) in enumerate(FOCUS):
        lines = wrap(detail, 48)
        nodes.append(y)
        g = [
            f'<text x="{idx_x}" y="{y + 5}" class="mono" font-size="11.5" letter-spacing="1" fill="{P["cyan"]}">{i + 1:02d}</text>',
            f'<text x="{text_x}" y="{y + 5.5}" class="sans" font-size="15.5" font-weight="700" fill="{P["text"]}">{esc(title)}</text>',
        ]
        for j, line in enumerate(lines):
            g.append(f'<text x="{text_x}" y="{y + 27 + j * 18}" class="sans" font-size="13" fill="{P["muted"]}">{esc(line)}</text>')
        parts.append(f'<g class="rise" style="animation-delay:{0.35 + i * 0.16:.2f}s">{"".join(g)}</g>')
        y += 27 + (len(lines) - 1) * 18 + 34
    H = int(y - 34 + PAD + 6)
    y0, y1 = nodes[0], nodes[-1]
    travel = 6.0
    start = 1.4
    line = (
        f'<rect x="{node_x - 1}" y="{y0}" width="2" height="{y1 - y0}" rx="1" fill="{P["border"]}"/>'
        f'<rect class="grow" x="{node_x - 1}" y="{y0}" width="2" height="{y1 - y0}" rx="1" fill="url(#nf-line)"/>'
        f'<g class="travel"><circle cx="{node_x}" cy="{y0}" r="7" fill="{P["cyan"]}" fill-opacity=".22"/>'
        f'<circle cx="{node_x}" cy="{y0}" r="2.6" fill="{P["cyan"]}"/></g>'
    )
    node_svg = []
    css = [
        f".grow{{transform-box:fill-box;transform-origin:top;animation:grow 1.2s cubic-bezier(.22,1,.36,1) .25s both}}"
        f"@keyframes grow{{from{{transform:scaleY(0)}}to{{transform:scaleY(1)}}}}",
        f".travel{{opacity:0;animation:travel {travel}s linear {start}s infinite}}"
        f"@keyframes travel{{0%{{opacity:0;transform:translateY(0)}}6%{{opacity:1}}94%{{opacity:1}}"
        f"100%{{opacity:0;transform:translateY({y1 - y0}px)}}}}",
        ".ring{opacity:0;transform-box:fill-box;transform-origin:center}"
        f"@keyframes ring{{0%{{opacity:.7;transform:scale(1)}}22%{{opacity:0;transform:scale(2.3)}}100%{{opacity:0;transform:scale(2.3)}}}}",
    ]
    for i, ny in enumerate(nodes):
        f = (ny - y0) / (y1 - y0)
        node_svg.append(
            f'<g class="rise" style="animation-delay:{0.3 + i * 0.16:.2f}s">'
            f'<circle class="ring" style="animation:ring {travel}s ease-out {start + f * travel:.2f}s infinite" cx="{node_x}" cy="{ny}" r="7" fill="none" stroke="{P["cyan"]}" stroke-width="1.5"/>'
            f'<circle cx="{node_x}" cy="{ny}" r="7.5" fill="{P["s1"]}" stroke="{P["violet"]}" stroke-width="2"/>'
            f'<circle cx="{node_x}" cy="{ny}" r="3" fill="{P["cyan"]}"/></g>'
        )
    defs = (f'<defs><linearGradient id="nf-line" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{P["violet"]}"/><stop offset="1" stop-color="{P["cyan"]}"/></linearGradient></defs>')
    body = card_frame(W, H, glow_xy=(W - 40, 30)) + "\n" + defs + "\n" + line + "\n" + "\n".join(node_svg) + "\n" + "\n".join(parts)
    desc = "Current focus: " + " ".join(f"{i + 1}. {d}" for i, (_, d) in enumerate(FOCUS))
    write("focus-roadmap.svg", doc(W, H, "Current focus — roadmap", desc, "".join(css), body))
    return desc


# ── Connect buttons ────────────────────────────────────────────────────────────────────────────────
def github_path():
    s = load_icon("simple-icons", "github")
    return re.search(r'<path d="([^"]+)"', s).group(1)


GLYPHS = {
    "portfolio": ('<circle cx="12" cy="12" r="9" fill="none" stroke="{c}" stroke-width="1.7"/>'
                  '<ellipse cx="12" cy="12" rx="4" ry="9" fill="none" stroke="{c}" stroke-width="1.7"/>'
                  '<path d="M3.5 9h17M3.5 15h17" fill="none" stroke="{c}" stroke-width="1.7"/>'),
    "linkedin": ('<circle cx="6.6" cy="6.4" r="2" fill="{c}"/>'
                 '<rect x="4.8" y="9.4" width="3.6" height="10.6" rx=".6" fill="{c}"/>'
                 '<path d="M10.8 9.4h3.4v1.5c.6-1 1.8-1.8 3.5-1.8 2.7 0 3.8 1.7 3.8 4.6V20h-3.6v-5.6c0-1.4-.4-2.3-1.7-2.3-1.3 0-2 .9-2 2.3V20h-3.4z" fill="{c}"/>'),
    "github": '<path d="{gh}" fill="{c}"/>',
    "email": ('<rect x="3" y="5.5" width="18" height="13" rx="2.5" fill="none" stroke="{c}" stroke-width="1.7"/>'
              '<path d="m4 7.5 8 6 8-6" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'),
}
BUTTONS = [
    ("portfolio", "Portfolio", "Visit", "Portfolio — visit nefsi-abdelouahab.vercel.app"),
    ("linkedin", "LinkedIn", "Connect", "LinkedIn — connect with Nefsi Abdelouahab"),
    ("github", "GitHub", "Follow", "GitHub — follow nefsi-abdelouahab"),
    ("email", "Email", "Contact", "Email — contact nefsiabdelouahab@gmail.com"),
]


def build_buttons():
    W, H = 164, 52
    gh = github_path()
    alts = {}
    for i, (slug, label, sub, alt) in enumerate(BUTTONS):
        glyph = GLYPHS[slug].format(c=P["cyan"], gh=gh)
        body = f"""<defs>
  <linearGradient id="nf-bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{P['s2']}"/><stop offset="1" stop-color="{P['s1']}"/></linearGradient>
  <linearGradient id="nf-shine" x1="0" x2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity="0"/><stop offset=".5" stop-color="#FFFFFF" stop-opacity=".16"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>
  <linearGradient id="nf-edge" x1="0" x2="1"><stop offset="0" stop-color="{P['violet']}"/><stop offset="1" stop-color="{P['cyan']}"/></linearGradient>
  <clipPath id="nf-btn"><rect width="{W}" height="{H}" rx="14"/></clipPath>
</defs>
<g clip-path="url(#nf-btn)">
  <rect width="{W}" height="{H}" fill="url(#nf-bg)"/>
  <g class="shine" style="animation-delay:{1 + i * 0.6:.1f}s"><rect x="-70" y="-10" width="46" height="{H + 20}" fill="url(#nf-shine)" transform="skewX(-20)"/></g>
</g>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="13.5" fill="none" stroke="url(#nf-edge)" stroke-opacity=".55"/>
<g class="rise" style="animation-delay:{0.1 + i * 0.08:.2f}s">
  <rect x="10" y="10" width="32" height="32" rx="9" fill="{P['violet']}" fill-opacity=".16" stroke="{P['violet']}" stroke-opacity=".45"/>
  <g transform="translate(16.5 16.5) scale(.79)">{glyph}</g>
  <text x="54" y="24.5" class="sans" font-size="14.5" font-weight="700" fill="{P['text']}">{label}</text>
  <text x="54" y="40" class="mono" font-size="10.5" letter-spacing=".8" fill="{P['muted']}">{sub.upper()}</text>
  <path d="M{W - 27} 31 {W - 19} 23M{W - 25.5} 23h6.5v6.5" fill="none" stroke="{P['muted']}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
</g>"""
        css = """
.shine{animation:shine 7s ease-in-out infinite}
@keyframes shine{0%{transform:translateX(0)}22%,100%{transform:translateX(290px)}}
"""
        write(f"btn-{slug}.svg", doc(W, H, label, alt, css, body))
        alts[slug] = alt
    return alts


# ── Divider ────────────────────────────────────────────────────────────────────────────────────────
def build_divider():
    W, H, cy = 800, 28, 14
    body = f"""<defs>
  <linearGradient id="nf-base" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{W}" y2="0">
    <stop offset="0" stop-color="{P['violet']}" stop-opacity="0"/>
    <stop offset=".2" stop-color="{P['violet']}" stop-opacity=".55"/>
    <stop offset=".5" stop-color="{P['cyan']}" stop-opacity=".75"/>
    <stop offset=".8" stop-color="{P['violet']}" stop-opacity=".55"/>
    <stop offset="1" stop-color="{P['violet']}" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="nf-spark" x1="0" x2="1">
    <stop offset="0" stop-color="{P['cyan']}" stop-opacity="0"/>
    <stop offset=".55" stop-color="{P['cyan']}"/>
    <stop offset="1" stop-color="{P['violet']}" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="nf-fade" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{W}" y2="0">
    <stop offset="0" stop-color="#000"/><stop offset=".18" stop-color="#FFF"/><stop offset=".82" stop-color="#FFF"/><stop offset="1" stop-color="#000"/>
  </linearGradient>
  <mask id="nf-mask" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}"><rect width="{W}" height="{H}" fill="url(#nf-fade)"/></mask>
</defs>
<rect x="0" y="{cy - .5}" width="{W / 2 - 22}" height="1" fill="url(#nf-base)"/>
<rect x="{W / 2 + 22}" y="{cy - .5}" width="{W / 2 - 22}" height="1" fill="url(#nf-base)"/>
<g mask="url(#nf-mask)"><rect class="spark" x="-140" y="{cy - 1}" width="140" height="2" rx="1" fill="url(#nf-spark)"/></g>
<circle cx="{W / 2 - 14}" cy="{cy}" r="1.6" fill="{P['violet']}"/>
<circle cx="{W / 2 + 14}" cy="{cy}" r="1.6" fill="{P['violet']}"/>
<circle class="pulse" cx="{W / 2}" cy="{cy}" r="5" fill="none" stroke="{P['cyan']}" stroke-width="1.2"/>
<rect x="{W / 2 - 3.5}" y="{cy - 3.5}" width="7" height="7" rx="1" fill="{P['violet']}" transform="rotate(45 {W / 2} {cy})"/>"""
    css = """
.spark{animation:spark 7s cubic-bezier(.45,0,.55,1) infinite}
@keyframes spark{0%{transform:translateX(0)}70%,100%{transform:translateX(940px)}}
.pulse{transform-box:fill-box;transform-origin:center;opacity:0;animation:pulse 3.5s ease-out infinite}
@keyframes pulse{0%{opacity:.8;transform:scale(.8)}60%,100%{opacity:0;transform:scale(2.2)}}
"""
    write("divider.svg", doc(W, H, "Section divider", "A thin violet-to-cyan line with a light travelling along it.", css, body))


if __name__ == "__main__":
    print(f"Writing to {OUT}")
    build_divider()
    build_terminal()
    build_skills()
    build_projects()
    build_roadmap()
    build_buttons()
