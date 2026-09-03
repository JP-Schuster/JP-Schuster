#!/usr/bin/env python3
import json
import os
import subprocess
from calendar import month_abbr
from collections import defaultdict
from datetime import datetime, timedelta, timezone

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
    "C": "#555555",
    "C++": "#F34B7D",
    "Rust": "#DEA584",
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
    totals = {"commits": 0, "additions": 0, "deletions": 0, "by_year": {}, "weeks": {}}
    for repo in repos:
        owner, name = repo.split("/", 1)
        for author in contributor_stats(owner, name):
            login = (author.get("author") or {}).get("login")
            if login != USERNAME:
                continue
            for week in author.get("weeks", []):
                ts = week.get("w", 0)
                if not ts:
                    continue
                week_date = datetime.fromtimestamp(ts, tz=timezone.utc).date()
                year = str(week_date.year)
                commits = week.get("c", 0)
                additions = week.get("a", 0)
                deletions = week.get("d", 0)
                totals["commits"] += commits
                totals["additions"] += additions
                totals["deletions"] += deletions
                bucket = totals["by_year"].setdefault(year, {"commits": 0, "additions": 0, "deletions": 0})
                bucket["commits"] += commits
                bucket["additions"] += additions
                bucket["deletions"] += deletions
                key = week_date.isoformat()
                totals["weeks"][key] = totals["weeks"].get(key, 0) + commits
            break
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


def week_series(weeks, count=32):
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    series = []
    for i in range(count - 1, -1, -1):
        start = monday - timedelta(weeks=i)
        series.append((start, weeks.get(start.isoformat(), 0)))
    return series


def build_activity_svg(weeks, by_year):
    series = week_series(weeks, 32)
    max_count = max((count for _, count in series), default=1) or 1
    width, height = 800, 195
    left, right, top, bottom = 36, 24, 58, 38
    chart_w = width - left - right
    chart_h = height - top - bottom
    gap = 4
    bar_w = max(8, (chart_w / len(series)) - gap)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
        f'<rect width="{width}" height="{height}" rx="10" fill="#1a1b27"/>',
        '<text x="24" y="28" fill="#7aa2f7" font-family="Segoe UI, Ubuntu, sans-serif" font-size="16" font-weight="700">Activity Graph</text>',
        '<text x="24" y="46" fill="#565f89" font-family="Segoe UI, Ubuntu, sans-serif" font-size="11">commits por semana · pessoal + organizations</text>',
    ]

    last_month = None
    for idx, (start, count) in enumerate(series):
        x = left + idx * (bar_w + gap)
        bar_h = 4 if count == 0 else max(6, round(chart_h * count / max_count))
        y = top + chart_h - bar_h
        color = "#3b4261" if count == 0 else "#7aa2f7"
        if count >= max_count * 0.66:
            color = "#9ece6a"
        elif count >= max_count * 0.33:
            color = "#7aa2f7"
        elif count > 0:
            color = "#3d59a1"
        parts.append(f'<rect x="{x:.1f}" y="{y}" width="{bar_w:.1f}" height="{bar_h}" rx="2" fill="{color}"/>')
        month = start.month
        if month != last_month:
            parts.append(
                f'<text x="{x:.1f}" y="{height - 14}" fill="#565f89" font-family="Segoe UI, Ubuntu, sans-serif" font-size="11">{month_abbr[month]}</text>'
            )
            last_month = month

    legend_x = 520
    for year, stats in sorted(by_year.items()):
        parts.append(
            f'<text x="{legend_x}" y="28" fill="#a9b1d6" font-family="Segoe UI, Ubuntu, sans-serif" font-size="12">{year}: {stats["commits"]} commits</text>'
        )
        legend_x += 140

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    repos, ranked = discover_repos_and_languages()
    totals = aggregate(repos)
    calendar = calendar_stats()

    write(f"{ASSETS_DIR}/github-stats.svg", build_stats_svg(totals, calendar, len(repos)))
    write(f"{ASSETS_DIR}/github-langs.svg", build_langs_svg(ranked))
    write(f"{ASSETS_DIR}/github-activity.svg", build_activity_svg(totals["weeks"], totals["by_year"]))

    print(
        json.dumps(
            {
                "repos": len(repos),
                "commits": totals["commits"],
                "additions": totals["additions"],
                "deletions": totals["deletions"],
                "prs": calendar["totalPullRequestContributions"],
                "issues": calendar["totalIssueContributions"],
                "languages": [(name, info["size"]) for name, info in ranked[:8]],
                "by_year": totals["by_year"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
