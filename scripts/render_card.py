#!/usr/bin/env python3
"""
Renders the neofetch-style profile card as two SVGs (dark.svg / light.svg)
using REAL, LIVE stats pulled from the GitHub API.

Usage:
    GITHUB_TOKEN=xxx python3 render_card.py   

Output: ../profile/dark.svg and ../profile/light.svg
"""
import calendar
import html
import os
import sys
import urllib.request
from datetime import date
import json

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "profile")

# ────────────────────────────── EDIT THIS ──────────────────────────────
USERNAME     = os.environ.get("GITHUB_USERNAME", "bielupc")
USER, HOST   = "biel", "altimira"          # renders as  biel@altimira
DOB          = date(2004, 5, 27)


def uptime_from_dob(dob):
    """Returns 'X years, Y months, Z days' since dob."""
    today = date.today()
    years = today.year - dob.year
    months = today.month - dob.month
    days = today.day - dob.day

    if days < 0:
        months -= 1
        prev_month = today.month - 1 if today.month > 1 else 12
        prev_year = today.year if today.month > 1 else today.year - 1
        days += calendar.monthrange(prev_year, prev_month)[1]

    if months < 0:
        years -= 1
        months += 12

    return f"{years} years, {months} months, {days} days"


STATIC_FIELDS = [
    ("field", "OS",                     "Linux, Android 15"),
    ("field", "Uptime",                 uptime_from_dob(DOB)),
    ("field", "Host",                   "Universitat Politècnica de Catalunya"),
    ("field", "Kernel",                 "AI Engineer"),
    ("field", "IDE",                    "Neovim, VS Code"),
    ("gap",),
    ("field", "Programming.Languages",  "Python, JavaScript, C++, SQL"),
    ("field", "Programming.Tools",     "Git, Docker, Azure, LangChain"),
    ("field", "Real.Languages",         "Catalan, Spanish, English"),
    ("gap",),
    ("field", "Hobbies.Software",       "Machine Learning, Web Dev"),
    ("field", "Hobbies.Life",       "Motorbikes, Coffee"),
    ("gap",),
    ("section", "Contact"),
    ("field", "Email.Personal",         "tarteraltimirabiel@gmail.com"),
    ("field", "GitHub",                 USERNAME),
    ("field", "LinkedIn",               "Biel Altimira"),
]
# ──────────────────────────── END EDIT THIS ────────────────────────────

ART_FILE = os.path.join(HERE, "ascii-art.txt")
FONT_FAMILY = "'Cascadia Code','Fira Code',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"


# ───────────────────────── live GitHub stats ─────────────────────────
def fetch_live_stats(username):
    """Pulls real counts from the GitHub REST/GraphQL API.
    Falls back to None values (rendered as '—') if no token / request fails,
    so local previews still work without credentials."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("warning: GITHUB_TOKEN not set, stats will show as '—'", file=sys.stderr)
        return {"repos": None, "commits": None, "contributed": None,
                "additions": None, "deletions": None}

    headers = {"Authorization": f"bearer {token}",
               "User-Agent": username,
               "Content-Type": "application/json"}

    def gql(query):
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=json.dumps({"query": query}).encode(),
            headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())

    def rest(path):
        req = urllib.request.Request(f"https://api.github.com{path}", headers=headers)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())

    stats = {"repos": None, "commits": None, "contributed": None,
             "additions": None, "deletions": None}

    # ── Repos: try GraphQL (public + private), fall back to REST public count ──
    try:
        data = gql(f'''
        {{
          user(login: "{username}") {{
            repositories(ownerAffiliations: [OWNER]) {{
              totalCount
            }}
          }}
        }}''')
        stats["repos"] = data["data"]["user"]["repositories"]["totalCount"]
    except Exception as e:
        print(f"warning: GraphQL repo count failed ({e}), trying REST fallback", file=sys.stderr)
        try:
            u = rest(f"/users/{username}")
            stats["repos"] = u.get("public_repos")
        except Exception as e2:
            print(f"warning: REST repo count fallback also failed: {e2}", file=sys.stderr)

    # ── Commits: GitHub search API (counts all commits by author) ──
    # contributionsCollection often returns 0 when git email ≠ GitHub email.
    # The search/commits endpoint is more reliable for raw commit counts.
    try:
        req = urllib.request.Request(
            f"https://api.github.com/search/commits?q=author:{username}",
            headers={"Authorization": f"bearer {token}",
                     "User-Agent": username,
                     "Accept": "application/vnd.github.cloak-preview+json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
            stats["commits"] = data.get("total_count")
    except Exception as e:
        print(f"warning: commit search failed: {e}", file=sys.stderr)

    # ── Additions / deletions via REST stats/contributors ──
    try:
        repo_data = gql(f'''
        {{
          user(login: "{username}") {{
            repositories(first: 50, ownerAffiliations: [OWNER], orderBy: {{field: PUSHED_AT, direction: DESC}}) {{
              nodes {{
                owner {{ login }}
                name
              }}
            }}
          }}
        }}''')
        repos = repo_data["data"]["user"]["repositories"]["nodes"]
        additions = 0
        deletions = 0
        got_data = False
        for repo in repos:
            full_name = f"{repo['owner']['login']}/{repo['name']}"
            try:
                req = urllib.request.Request(
                    f"https://api.github.com/repos/{full_name}/stats/contributors",
                    headers=headers)
                with urllib.request.urlopen(req, timeout=20) as r:
                    if r.status == 202:
                        import time
                        time.sleep(1)
                        with urllib.request.urlopen(req, timeout=20) as r2:
                            contrib = json.loads(r2.read())
                    else:
                        contrib = json.loads(r.read())
                if isinstance(contrib, list):
                    got_data = True
                    for c in contrib:
                        if c.get("author", {}).get("login", "").lower() == username.lower():
                            for week in c.get("weeks", []):
                                additions += week.get("a", 0)
                                deletions += week.get("d", 0)
            except Exception:
                continue
        if got_data:
            stats["additions"] = additions
            stats["deletions"] = deletions
    except Exception as e:
        print(f"warning: additions/deletions fetch failed: {e}", file=sys.stderr)

    return stats


def fmt(n):
    return "—" if n is None else f"{n:,}"


# ───────────────────────── ASCII art loading ─────────────────────────
def load_art():
    with open(ART_FILE, encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f.read().split("\n")]
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()
    nonblank = [l for l in lines if l.strip()]
    indent = min(len(l) - len(l.lstrip(" ")) for l in nonblank)
    lines = [l[indent:] if len(l) >= indent else "" for l in lines]
    return [l.rstrip() for l in lines]


# ───────────────────────── build the card model ─────────────────────────
def build_rows(stats):
    fields = list(STATIC_FIELDS)

    loc = stats["additions"] + stats["deletions"] \
        if stats["additions"] is not None and stats["deletions"] is not None else None

    # GitHub stats rendered as single-column rows (keeps the panel narrow,
    # so the whole card scales up larger when GitHub shrinks it to fit)
    if stats["additions"] is None or stats["deletions"] is None:
        ar_extra = [("—", "val")]
    else:
        ar_extra = [(fmt(stats["additions"]), "green"), ("++ / ", "dim"),
                    (fmt(stats["deletions"]), "red"), ("--", "dim")]
    gh_fields = [
        ("Repos", fmt(stats["repos"]), []),
        ("Commits", fmt(stats["commits"]), []),
        ("LOC", fmt(loc), []),
        ("Added/Removed", "", ar_extra),
    ]

    # Determine panel width from the longest single-column row
    panel_w = len(USER) + 1 + len(HOST) + 7
    for it in fields:
        if it[0] == "field":
            panel_w = max(panel_w, 2 + len(it[1]) + 1 + 1 + 2 + 1 + len(it[2]))
        elif it[0] == "section":
            panel_w = max(panel_w, len(it[1]) + 4)
    for lab, val, extra in gh_fields:
        extra_len = sum(len(t) for t, _ in extra)
        panel_w = max(panel_w, 2 + len(lab) + 1 + 1 + 2 + 1 + len(val) + extra_len)
    panel_w += 1

    # Build header + static rows
    rows = [[(USER, "head"), ("@", "dim"), (HOST, "head"),
             (" " + "─" * (panel_w - len(USER) - len(HOST) - 2), "dim")]]
    for it in fields:
        if it[0] == "gap":
            rows.append([])
        elif it[0] == "section":
            t = it[1]
            rows.append([("- ", "dim"), (t, "sect"),
                         (" " + "─" * (panel_w - len(t) - 3), "dim")])
        elif it[0] == "field":
            _, lab, val = it
            dots = max(2, panel_w - 5 - len(lab) - len(val))
            rows.append([(". ", "dim"), (lab + ":", "label"),
                         (" " + "." * dots + " ", "dim"), (val, "val")])

    # ─── GitHub Stats ───
    rows.append([])
    rows.append([("- ", "dim"), ("GitHub Stats", "sect"),
                 (" " + "─" * (panel_w - len("GitHub Stats") - 3), "dim")])

    for lab, val, extra in gh_fields:
        extra_len = sum(len(t) for t, _ in extra)
        dots = max(2, panel_w - 5 - len(lab) - len(val) - extra_len)
        segs = [(". ", "dim"), (lab + ":", "label"),
                (" " + "." * dots + " ", "dim")]
        if val:
            segs.append((val, "val"))
        segs.extend(extra)
        rows.append(segs)

    return rows, panel_w


def build_card():
    stats = fetch_live_stats(USERNAME)
    rows, panel_w = build_rows(stats)

    art_lines = load_art()
    art_w = max(len(l) for l in art_lines)
    art = [(l.ljust(art_w), "fg") for l in art_lines]

    gap_cols = 3
    return art, rows, art_w, panel_w, gap_cols


# ───────────────────────── SVG rendering ─────────────────────────
PALETTES = {
    "dark": {
        "bg": "#1d2021", "fg": "#ebdbb2", "dim": "#928374", "head": "#fabd2f",
        "label": "#83a598", "sect": "#fe8019", "val": "#ebdbb2",
        "green": "#b8bb26", "red": "#fb4934",
    },
    "light": {
        "bg": "#ffffff", "fg": "#24292e", "dim": "#586069", "head": "#b57614",
        "label": "#076678", "sect": "#af3a03", "val": "#24292e",
        "green": "#2ea043", "red": "#cf222e",
    },
}
BOLD_ROLES = {"bold", "head", "sect"}
CHAR_W, LINE_H, FONT_SIZE, PAD = 44, 84, 72, 48


def esc(s):
    return html.escape(s, quote=False)


def render_svg(art, rows, art_w, panel_w, gap_cols, theme):
    pal = PALETTES[theme]

    content_cols = max(sum(len(t) for t, _ in row) for row in rows) if rows else 0
    content_h = len(rows) * LINE_H
    height = PAD * 2 + content_h

    # Scale the whole art block uniformly to fit the content height:
    # no aspect-ratio distortion, it looks exactly as it does in ascii-art.txt
    art_h = len(art) * LINE_H
    art_scale = min(1.0, content_h / art_h) if art_h > 0 else 1.0
    art_disp_w = art_w * CHAR_W * art_scale
    art_y = PAD + (content_h - art_h * art_scale) / 2

    content_x = PAD + art_disp_w + gap_cols * CHAR_W
    width = content_x + content_cols * CHAR_W + PAD

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
           f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="{FONT_FAMILY}">',
           f'<rect width="100%" height="100%" fill="{pal["bg"]}" rx="10"/>']

    # Uniformly scaled ASCII art
    out.append(f'<g transform="translate({PAD:.1f},{art_y:.1f}) scale({art_scale:.6f})">')
    for i, (text, role) in enumerate(art):
        if text:
            weight = "bold" if role in BOLD_ROLES else "normal"
            col = pal["fg"] if role == "bold" else pal.get(role, pal["fg"])
            out.append(
                f'<text x="0" y="{i * LINE_H + FONT_SIZE:.1f}" fill="{col}" '
                f'font-size="{FONT_SIZE}" font-weight="{weight}" '
                f'xml:space="preserve">{esc(text)}</text>'
            )
    out.append('</g>')

    # Content rows
    for i, row in enumerate(rows):
        x = content_x
        y = PAD + i * LINE_H + FONT_SIZE
        for text, role in row:
            if text:
                weight = "bold" if role in BOLD_ROLES else "normal"
                col = pal["fg"] if role == "bold" else pal.get(role, pal["fg"])
                out.append(
                    f'<text x="{x:.1f}" y="{y:.1f}" fill="{col}" '
                    f'font-size="{FONT_SIZE}" font-weight="{weight}" '
                    f'xml:space="preserve">{esc(text)}</text>'
                )
            x += len(text) * CHAR_W
    out.append("</svg>")
    return "\n".join(out)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    art, rows, art_w, panel_w, gap = build_card()
    for theme in ("dark", "light"):
        svg = render_svg(art, rows, art_w, panel_w, gap, theme)
        path = os.path.join(OUT_DIR, f"{theme}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()