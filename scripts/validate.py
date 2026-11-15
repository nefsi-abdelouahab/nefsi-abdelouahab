"""Check the profile README, the SVGs in assets/ and the profile-images workflow.

Usage (from the repository root, Python 3.9+):

    python scripts/validate.py            # everything, including a request to every remote image
    python scripts/validate.py --offline  # skip the network checks

The workflow check needs PyYAML (`pip install pyyaml`) and is skipped without it. Exits 1 on any
problem. Images on the "output" branch are reported as "wait", not as failures, because they only
exist after the workflow has run once.
"""
import argparse
import html.parser
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

REPO = pathlib.Path(__file__).resolve().parent.parent
problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL", msg)


def check_svgs():
    """Every SVG is well-formed XML and renders inside <img>: no script, no external resource."""
    print("SVG assets")
    for svg in sorted((REPO / "assets").glob("*.svg")):
        text = svg.read_text(encoding="utf-8")
        try:
            ET.fromstring(text)
        except ET.ParseError as e:
            bad(f"{svg.name}: not well-formed XML: {e}")
            continue
        for pat, why in [(r"<script", "a script"), (r"<foreignObject", "foreignObject"), (r"@import", "@import"),
                         (r"@font-face", "a web font"), (r"(?:href|src)=\"(?:https?:)?//", "an external reference"),
                         (r"url\((?!#)", "an external url()"), (r"<image", "a raster image")]:
            if re.search(pat, text):
                bad(f"{svg.name}: contains {why}, which does not load inside <img>")
        ids = re.findall(r'\bid="([^"]+)"', text)
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            bad(f"{svg.name}: duplicate ids {dupes}")
        if "prefers-reduced-motion" not in text:
            bad(f"{svg.name}: no prefers-reduced-motion fallback")
        print(f"  ok   {svg.name}")


class Scan(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.imgs, self.urls, self.tags = [], [], set()

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        a = dict(attrs)
        if "style" in a or "class" in a:
            bad(f"<{tag}> uses a style/class attribute, which GitHub strips")
        if tag == "img":
            self.imgs.append(a)
            self.urls.append(a.get("src", ""))
        if tag == "source":
            self.urls.append(a.get("srcset", ""))
            if not a.get("media", "").startswith("(prefers-color-scheme:"):
                bad(f"<source> without a prefers-color-scheme media query: {a}")
        if tag == "a":
            self.urls.append(a.get("href", ""))


def check_readme():
    """Only tags GitHub keeps, alt text on every image, well-formed URLs, local assets present."""
    print("README")
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    allowed = {"p", "div", "img", "a", "picture", "source", "h2", "b", "i", "sub", "br", "details", "summary"}
    banned = {"style", "script", "iframe", "svg", "link", "object", "embed", "form", "input", "button", "video"}
    s = Scan()
    s.feed(readme)
    for t in sorted(s.tags - allowed):
        bad(f"unexpected tag <{t}>")
    for t in sorted(s.tags & banned):
        bad(f"banned tag <{t}>")
    for img in s.imgs:
        if "alt" not in img:
            bad(f"<img> without alt: {img.get('src')}")
        elif img["alt"] == "" and not (img["src"].endswith("divider.svg") or "section=footer" in img["src"]):
            bad(f"empty alt on an image that carries meaning: {img['src']}")
    described = sum(1 for i in s.imgs if i.get("alt"))
    decorative = sum(1 for i in s.imgs if i.get("alt") == "")
    print(f"  {len(s.imgs)} <img>: {described} with descriptive alt, {decorative} decorative (alt=\"\")")

    for raw in s.urls:
        if raw.startswith("mailto:"):
            if not re.fullmatch(r"mailto:[^@\s]+@[^@\s]+\.[a-z]+", raw):
                bad(f"malformed mailto: {raw}")
            continue
        if raw.startswith("./"):
            if not (REPO / raw[2:]).is_file():
                bad(f"missing local asset {raw}")
            continue
        u = urllib.parse.urlsplit(raw)
        if u.scheme != "https" or not u.netloc:
            bad(f"not an absolute https URL: {raw}")
        if re.search(r"\s", raw):
            bad(f"whitespace in URL: {raw}")
    # A comma inside a srcset URL can be read as a candidate separator: encode it as %2C.
    for m in re.finditer(r'srcset="([^"]+)"', readme):
        if "," in m.group(1):
            bad(f"raw comma in srcset (encode it as %2C): {m.group(1)[:80]}")
    # A literal "&name;" inside an attribute is decoded as an HTML entity and corrupts the URL.
    for m in re.finditer(r'(?:src|srcset|href)="([^"]+)"', readme):
        for ent in re.findall(r"&([A-Za-z][A-Za-z0-9]*);", m.group(1)):
            bad(f"URL contains the entity-like sequence &{ent}; : {m.group(1)[:80]}")
    todos = re.findall(r"TODO\([a-z]+\)", readme)
    print(f"  TODO markers left: {todos or 'none'}")
    return s.urls


def check_remote(urls):
    """Every remote image answers 200 with an SVG."""
    print("Remote images")
    hosts = ("capsule-render", "readme-typing-svg", "shields.io", "streak-stats", "activity-graph",
             "raw.githubusercontent.com")
    seen = set()
    for raw in urls:
        if not raw.startswith("https://") or raw in seen or not any(h in raw for h in hosts):
            continue
        seen.add(raw)
        req = urllib.request.Request(raw, headers={"User-Agent": "Mozilla/5.0 (profile readme validator)"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                status, ctype = r.status, r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            status, ctype = e.code, e.headers.get("Content-Type", "")
        except Exception as e:  # noqa: BLE001  (timeouts, DNS: report them, never crash)
            status, ctype = 0, type(e).__name__
        parts = urllib.parse.urlsplit(raw)
        on_output_branch = parts.netloc == "raw.githubusercontent.com" and "/output/" in parts.path
        ok = status == 200 and "svg" in ctype
        tag = "ok  " if ok else ("wait" if on_output_branch else "FAIL")
        print(f"  {tag} {status} {ctype[:24]:24} {parts.netloc}{parts.path[:48]}")
        if not ok and not on_output_branch:
            bad(f"{status} {ctype} for {raw[:100]}")


def check_workflow():
    """The workflow parses and produces every file the README reads from the output branch."""
    print("Workflow")
    try:
        import yaml
    except ImportError:
        print("  skip PyYAML is not installed (pip install pyyaml)")
        return
    wf = yaml.safe_load((REPO / ".github/workflows/snake.yml").read_text(encoding="utf-8"))
    on = wf.get(True) or wf.get("on") or {}  # YAML 1.1 parses the bare key `on` as True
    steps = wf.get("jobs", {}).get("generate", {}).get("steps", [])

    def check(cond, msg):
        if not cond:
            bad(f"snake.yml: {msg}")

    check("workflow_dispatch" in on and "schedule" in on, "needs the schedule and workflow_dispatch triggers")
    check(wf.get("permissions", {}).get("contents") == "write", "needs permissions: contents: write")
    snk = [st for st in steps if st.get("uses", "").startswith("Platane/snk")]
    publish = [st for st in steps if st.get("uses", "").startswith("crazy-max/ghaction-github-pages")]
    check(len(snk) == 1, "needs exactly one Platane/snk step")
    check(len(publish) == 1 and publish[0]["with"].get("target_branch") == "output",
          "needs one publish step targeting the output branch")
    written = {(st.get("with") or {}).get("path") for st in steps}  # every card step that writes a file
    outs = snk[0]["with"].get("outputs", "").split() if snk else []
    written |= {o.split("?")[0] for o in outs}
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    for name in sorted(set(re.findall(r"/output/([\w.-]+\.svg)", readme))):
        check(f"dist/{name}" in written, f"the README reads output/{name} but the workflow never writes it")
    for o in outs:
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(o).query)
        if "color_dots" in q:
            check(len(q["color_dots"][0].split(",")) == 5, f"color_dots needs exactly 5 colours: {o}")
    print(f"  ok   parsed; writes {', '.join(sorted(w.removeprefix('dist/') for w in written if w))}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--offline", action="store_true", help="skip the requests to remote images")
    args = ap.parse_args()
    check_svgs()
    urls = check_readme()
    if args.offline:
        print("Remote images\n  skip --offline")
    else:
        check_remote(urls)
    check_workflow()
    print()
    print("RESULT:", "PASS" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
