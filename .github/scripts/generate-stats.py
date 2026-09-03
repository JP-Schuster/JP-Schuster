#!/usr/bin/env python3
import json
import os
import subprocess
from collections import defaultdict
from datetime import datetime, timezone

USERNAME = os.environ.get("GITHUB_USERNAME", "JP-Schuster")
TOKEN = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")
ASSETS_DIR = os.environ.get("STATS_ASSETS_DIR", "assets")

LANG_COLORS = {
    "TypeScript": "#3178C6",
    "JavaScript": "#F1E05A",
    "Python": "#3572A5",
    "Go": "#00ADD8",
    "HTML": "#E34C26",
    "CSS": "#563D7C",
    "Shell": "#89E051",
    "Dockerfile": "#384D54",
    "Java": "#B07219",
}

RANK_ORDER = ["C", "B", "A", "AA", "AAA", "S", "SS", "SSS"]
RANK_COLORS = {
    "C": "#6e7681",
    "B": "#8b949e",
    "A": "#58a6ff",
    "AA": "#79c0ff",
    "AAA": "#a5d6ff",
    "S": "#3fb950",
    "SS": "#d29922",
    "SSS": "#f85149",
}

TROPHY_RULES = {
    "Commits": [10, 50, 100, 150, 200, 300, 500, 1000],
    "Pull Requests": [1, 5, 10, 20, 30, 50, 80, 120],
    "Lines Changed": [1000, 10000, 50000, 100000, 500000, 1000000, 5000000, 10000000],
    "Repositories": [2, 4, 6, 8, 10, 12, 16, 20],
    "Languages": [2, 3, 4, 5, 6, 7, 9, 12],
}


def gh(*args):
    env = os.environ.copy()
    if TOKEN:
        env["GH_TOKEN"] = TOKEN
    return subprocess.check_output(["gh", *args], text=True, env=env)


def graphql(query):
    return json.loads(gh("api", "graphql", "-f", f"query={query}"))


def contributor_stats(owner, repo):
    try:
        raw = gh("api", f"repos/{owner}/{repo}/stats/contributors")
        return json.loads(raw) if raw.strip() else []
    except subprocess.CalledProcessError:
        return []


def discover_repos_and_languages():
    data = graphql(
        """query {
          user(login: "%s") {
            repositoriesContributedTo(first: 100, includeUserRepositories: true, contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, PULL_REQUEST_REVIEW]) {
              nodes { nameWithOwner languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } } }
            }
            repositories(first: 100, ownerAffiliations: OWNER) {
              nodes { nameWithOwner languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } } }
            }
          }
        }"""
        % USERNAME
    )
    user = data["data"]["user"]
    repos = {}
    languages = defaultdict(lambda: {"size": 0, "color": "#8B949E"})
    for block in ("repositoriesContributedTo", "repositories"):
        for node in user[block]["nodes"]:
            repos[node["nameWithOwner"]] = True
            for edge in node["languages"]["edges"]:
                name = edge["node"]["name"]
                languages[name]["size"] += edge["size"]
                languages[name]["color"] = edge["node"]["color"] or LANG_COLORS.get(name, "#8B949E")
    ranked = sorted(languages.items(), key=lambda item: item[1]["size"], reverse=True)
    return sorted(repos), ranked


def aggregate(repos):
    totals = {"commits": 0, "additions": 0, "deletions": 0, "by_year": {}}
    active_repos = 0

    for repo in repos:
        owner, name = repo.split("/", 1)
        repo_commits = 0

        for author in contributor_stats(owner, name):
            login = (author.get("author") or {}).get("login")
            if login != USERNAME:
                continue
            for week in author.get("weeks", []):
                ts = week.get("w", 0)
                year = datetime.fromtimestamp(ts, tz=timezone.utc).year if ts else "unknown"
                commits = week.get("c", 0)
                additions = week.get("a", 0)
                deletions = week.get("d", 0)
                repo_commits += commits
                totals["commits"] += commits
                totals["additions"] += additions
                totals["deletions"] += deletions
                bucket = totals["by_year"].setdefault(str(year), {"commits": 0, "additions": 0, "deletions": 0})
                bucket["commits"] += commits
                bucket["additions"] += additions
                bucket["deletions"] += deletions
            break

        if repo_commits > 0:
            active_repos += 1

    totals["active_repos"] = active_repos
    return totals


def calendar_stats():
    try:
        prs = json.loads(gh("api", f"search/issues?q=author:{USERNAME}+type:pr&per_page=1"))
        pr_count = prs.get("total_count", 0)
    except subprocess.CalledProcessError:
        pr_count = 0
    try:
        issues = json.loads(gh("api", f"search/issues?q=author:{USERNAME}+type:issue&per_page=1"))
        issue_count = issues.get("total_count", 0)
    except subprocess.CalledProcessError:
        issue_count = 0
    return {
        "totalPullRequestContributions": pr_count,
        "totalIssueContributions": issue_count,
    }


def fmt(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def rank_for(value, thresholds):
    rank = "C"
    for idx, threshold in enumerate(thresholds):
        if value >= threshold:
            rank = RANK_ORDER[idx]
    return rank


def build_trophy_data(totals, calendar, language_count):
    lines_changed = totals["additions"] + totals["deletions"]
    metrics = {
        "Commits": totals["commits"],
        "Pull Requests": calendar["totalPullRequestContributions"],
        "Lines Changed": lines_changed,
        "Repositories": totals["active_repos"],
        "Languages": language_count,
    }
    trophies = []
    for title, value in metrics.items():
        thresholds = TROPHY_RULES[title]
        rank = rank_for(value, thresholds)
        max_threshold = thresholds[-1]
        progress = min(100, round(value / max_threshold * 100)) if max_threshold else 0
        trophies.append(
            {
                "title": title,
                "value": value,
                "display": fmt(value) if title == "Lines Changed" else f"{value:,}",
                "rank": rank,
                "progress": progress,
                "color": RANK_COLORS[rank],
            }
        )
    return trophies


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def build_stats_svg(totals, calendar, repo_count):
    commits = totals["commits"]
    additions = totals["additions"]
    deletions = totals["deletions"]
    prs = calendar["totalPullRequestContributions"]
    issues = calendar["totalIssueContributions"]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="495" height="195" viewBox="0 0 495 195" role="img">
  <rect width="495" height="195" rx="10" fill="#1a1b27"/>
  <text x="24" y="32" fill="#7aa2f7" font-family="Segoe UI, Ubuntu, sans-serif" font-size="16" font-weight="700">{USERNAME}'s GitHub Stats</text>
  <text x="24" y="52" fill="#565f89" font-family="Segoe UI, Ubuntu, sans-serif" font-size="11">pessoal + organizations</text>

  <text x="24" y="90" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Total Commits</text>
  <text x="24" y="116" fill="#9ece6a" font-family="Segoe UI, Ubuntu, sans-serif" font-size="24" font-weight="700">{commits:,}</text>

  <text x="170" y="90" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Total PRs</text>
  <text x="170" y="116" fill="#bb9af7" font-family="Segoe UI, Ubuntu, sans-serif" font-size="24" font-weight="700">{prs:,}</text>

  <text x="290" y="90" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Issues</text>
  <text x="290" y="116" fill="#f7768e" font-family="Segoe UI, Ubuntu, sans-serif" font-size="24" font-weight="700">{issues:,}</text>

  <text x="390" y="90" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Repos</text>
  <text x="390" y="116" fill="#e0af68" font-family="Segoe UI, Ubuntu, sans-serif" font-size="24" font-weight="700">{repo_count:,}</text>

  <text x="24" y="154" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Linhas adicionadas</text>
  <text x="24" y="178" fill="#9ece6a" font-family="Segoe UI, Ubuntu, sans-serif" font-size="20" font-weight="700">+{fmt(additions)}</text>

  <text x="270" y="154" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Linhas removidas</text>
  <text x="270" y="178" fill="#f7768e" font-family="Segoe UI, Ubuntu, sans-serif" font-size="20" font-weight="700">-{fmt(deletions)}</text>
</svg>
"""


def build_langs_svg(ranked):
    top = ranked[:6]
    total_size = sum(item[1]["size"] for item in top) or 1
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="195" viewBox="0 0 300 195" role="img">',
        '<rect width="300" height="195" rx="10" fill="#1a1b27"/>',
        '<text x="20" y="32" fill="#7aa2f7" font-family="Segoe UI, Ubuntu, sans-serif" font-size="16" font-weight="700">Most Used Languages</text>',
        '<text x="20" y="52" fill="#565f89" font-family="Segoe UI, Ubuntu, sans-serif" font-size="11">pessoal + organizations</text>',
    ]

    x = 20
    for name, info in top:
        width = max(8, round(260 * info["size"] / total_size))
        color = info["color"] or LANG_COLORS.get(name, "#8B949E")
        parts.append(f'<rect x="{x}" y="66" width="{width}" height="10" fill="{color}"/>')
        x += width

    y = 96
    for name, info in top:
        pct = info["size"] / total_size * 100
        color = info["color"] or LANG_COLORS.get(name, "#8B949E")
        parts.append(f'<circle cx="26" cy="{y - 4}" r="5" fill="{color}"/>')
        parts.append(
            f'<text x="40" y="{y}" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">{name}</text>'
        )
        parts.append(
            f'<text x="248" y="{y}" fill="#a9b1d6" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13" text-anchor="end">{pct:.1f}%</text>'
        )
        y += 16

    parts.append("</svg>")
    return "\n".join(parts)


def build_trophies_svg(trophies):
    width, height = 800, 195
    card_w, gap = 145, 12
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
        f'<rect width="{width}" height="{height}" rx="10" fill="#1a1b27"/>',
        '<text x="24" y="28" fill="#7aa2f7" font-family="Segoe UI, Ubuntu, sans-serif" font-size="16" font-weight="700">GitHub Trophies</text>',
        '<text x="24" y="46" fill="#565f89" font-family="Segoe UI, Ubuntu, sans-serif" font-size="11">ranking SSS · SS · S · AAA · AA · A · B · C</text>',
    ]

    x = 24
    y = 58
    for trophy in trophies:
        color = trophy["color"]
        parts.append(f'<rect x="{x}" y="{y}" width="{card_w}" height="118" rx="8" fill="#24283b" stroke="#3b4261"/>')
        parts.append(
            f'<text x="{x + 12}" y="{y + 22}" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="12">{trophy["title"]}</text>'
        )
        parts.append(
            f'<text x="{x + card_w - 12}" y="{y + 58}" fill="{color}" font-family="Segoe UI, Ubuntu, sans-serif" font-size="28" font-weight="700" text-anchor="end">{trophy["rank"]}</text>'
        )
        parts.append(
            f'<text x="{x + 12}" y="{y + 58}" fill="#a9b1d6" font-family="Segoe UI, Ubuntu, sans-serif" font-size="14">{trophy["display"]}</text>'
        )
        parts.append(f'<rect x="{x + 12}" y="{y + 72}" width="{card_w - 24}" height="8" rx="4" fill="#1a1b27"/>')
        bar_w = max(8, round((card_w - 24) * trophy["progress"] / 100))
        parts.append(f'<rect x="{x + 12}" y="{y + 72}" width="{bar_w}" height="8" rx="4" fill="{color}"/>')
        parts.append(
            f'<text x="{x + 12}" y="{y + 98}" fill="#565f89" font-family="Segoe UI, Ubuntu, sans-serif" font-size="10">progresso {trophy["progress"]}%</text>'
        )
        x += card_w + gap

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    repos, ranked = discover_repos_and_languages()
    totals = aggregate(repos)
    calendar = calendar_stats()
    trophies = build_trophy_data(totals, calendar, len(ranked))

    write(f"{ASSETS_DIR}/github-stats.svg", build_stats_svg(totals, calendar, len(repos)))
    write(f"{ASSETS_DIR}/github-langs.svg", build_langs_svg(ranked))
    write(f"{ASSETS_DIR}/github-trophies.svg", build_trophies_svg(trophies))

    print(json.dumps({"commits": totals["commits"], "trophies": trophies}, indent=2))


if __name__ == "__main__":
    main()
