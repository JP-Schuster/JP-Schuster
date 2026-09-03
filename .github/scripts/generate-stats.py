#!/usr/bin/env python3
import json
import os
import subprocess
from datetime import datetime, timezone

USERNAME = os.environ.get("GITHUB_USERNAME", "JP-Schuster")
TOKEN = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")
ASSETS_DIR = os.environ.get("STATS_ASSETS_DIR", "assets")


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


def discover_repos():
    data = graphql(
        'query { user(login: "%s") { repositoriesContributedTo(first: 100, includeUserRepositories: true, contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, PULL_REQUEST_REVIEW]) { nodes { nameWithOwner } } repositories(first: 100, ownerAffiliations: OWNER) { nodes { nameWithOwner } } } }'
        % USERNAME
    )
    user = data["data"]["user"]
    repos = set()
    for block in ("repositoriesContributedTo", "repositories"):
        for node in user[block]["nodes"]:
            repos.add(node["nameWithOwner"])
    return sorted(repos)


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
                year = datetime.fromtimestamp(ts, tz=timezone.utc).year if ts else "unknown"
                commits = week.get("c", 0)
                additions = week.get("a", 0)
                deletions = week.get("d", 0)
                totals["commits"] += commits
                totals["additions"] += additions
                totals["deletions"] += deletions
                bucket = totals["by_year"].setdefault(str(year), {"commits": 0, "additions": 0, "deletions": 0})
                bucket["commits"] += commits
                bucket["additions"] += additions
                bucket["deletions"] += deletions
                if ts:
                    key = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
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


def compute_streaks(weeks):
    if not weeks:
        return 0, 0, 0

    ordered = sorted(weeks.items())
    total = sum(weeks.values())
    longest = 0
    current_run = 0
    for _, count in ordered:
        if count > 0:
            current_run += 1
            longest = max(longest, current_run)
        else:
            current_run = 0

    current = 0
    for _, count in reversed(ordered):
        if count > 0:
            current += 1
        else:
            break

    return current, longest, total


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

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="520" height="200" viewBox="0 0 520 200" role="img" aria-label="GitHub stats for {USERNAME}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#1a1b27"/>
      <stop offset="100%" stop-color="#24283b"/>
    </linearGradient>
  </defs>
  <rect width="520" height="200" rx="10" fill="url(#bg)"/>
  <text x="24" y="34" fill="#7aa2f7" font-family="Segoe UI, Ubuntu, sans-serif" font-size="18" font-weight="700">{USERNAME} GitHub Stats</text>
  <text x="24" y="56" fill="#a9b1d6" font-family="Segoe UI, Ubuntu, sans-serif" font-size="12">All-time · pessoal + organizations</text>

  <text x="24" y="92" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Total Commits</text>
  <text x="24" y="118" fill="#9ece6a" font-family="Segoe UI, Ubuntu, sans-serif" font-size="24" font-weight="700">{commits:,}</text>

  <text x="170" y="92" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Total PRs</text>
  <text x="170" y="118" fill="#bb9af7" font-family="Segoe UI, Ubuntu, sans-serif" font-size="24" font-weight="700">{prs:,}</text>

  <text x="290" y="92" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Issues</text>
  <text x="290" y="118" fill="#f7768e" font-family="Segoe UI, Ubuntu, sans-serif" font-size="24" font-weight="700">{issues:,}</text>

  <text x="390" y="92" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Repos</text>
  <text x="390" y="118" fill="#e0af68" font-family="Segoe UI, Ubuntu, sans-serif" font-size="24" font-weight="700">{repo_count:,}</text>

  <text x="24" y="156" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Linhas adicionadas</text>
  <text x="24" y="182" fill="#9ece6a" font-family="Segoe UI, Ubuntu, sans-serif" font-size="20" font-weight="700">+{fmt(additions)}</text>

  <text x="260" y="156" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Linhas removidas</text>
  <text x="260" y="182" fill="#f7768e" font-family="Segoe UI, Ubuntu, sans-serif" font-size="20" font-weight="700">-{fmt(deletions)}</text>
</svg>
"""


def build_streak_svg(current, longest, total):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="420" height="165" viewBox="0 0 420 165" role="img" aria-label="GitHub streak for {USERNAME}">
  <rect width="420" height="165" rx="10" fill="#1a1b27"/>
  <text x="24" y="30" fill="#7aa2f7" font-family="Segoe UI, Ubuntu, sans-serif" font-size="16" font-weight="700">Contribution Streak</text>
  <text x="24" y="52" fill="#565f89" font-family="Segoe UI, Ubuntu, sans-serif" font-size="11">Semanas ativas · pessoal + organizations</text>

  <text x="40" y="110" fill="#a9b1d6" font-family="Segoe UI, Ubuntu, sans-serif" font-size="12">Current</text>
  <text x="40" y="138" fill="#9ece6a" font-family="Segoe UI, Ubuntu, sans-serif" font-size="28" font-weight="700">{current}w</text>

  <text x="170" y="110" fill="#a9b1d6" font-family="Segoe UI, Ubuntu, sans-serif" font-size="12">Longest</text>
  <text x="170" y="138" fill="#bb9af7" font-family="Segoe UI, Ubuntu, sans-serif" font-size="28" font-weight="700">{longest}w</text>

  <text x="300" y="110" fill="#a9b1d6" font-family="Segoe UI, Ubuntu, sans-serif" font-size="12">Commits</text>
  <text x="300" y="138" fill="#7dcfff" font-family="Segoe UI, Ubuntu, sans-serif" font-size="28" font-weight="700">{total}</text>
</svg>
"""


def build_activity_svg(weeks, by_year):
    cols = 26
    cell = 11
    gap = 2
    width = 24 + cols * (cell + gap)
    height = 150
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Activity graph for {USERNAME}">',
        f'<rect width="{width}" height="{height}" rx="10" fill="#1a1b27"/>',
        f'<text x="24" y="24" fill="#7aa2f7" font-family="Segoe UI, Ubuntu, sans-serif" font-size="16" font-weight="700">Activity Graph</text>',
        f'<text x="24" y="40" fill="#565f89" font-family="Segoe UI, Ubuntu, sans-serif" font-size="11">Commits por semana · pessoal + organizations</text>',
    ]

    ordered = sorted(weeks.items())[-cols * 7 :]
    max_count = max((count for _, count in ordered), default=1)
    for idx, (_, count) in enumerate(ordered):
        col = idx // 7
        row = idx % 7
        x = 24 + col * (cell + gap)
        y = 48 + row * (cell + gap)
        if count == 0:
            color = "#1f2335"
        elif count < max_count * 0.33:
            color = "#40695B"
        elif count < max_count * 0.66:
            color = "#549568"
        else:
            color = "#9ece6a"
        elements.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{color}"/>')

    y_text = height - 12
    x_text = 24
    for year, stats in sorted(by_year.items()):
        label = f"{year}: {stats['commits']} commits"
        elements.append(
            f'<text x="{x_text}" y="{y_text}" fill="#a9b1d6" font-family="Segoe UI, Ubuntu, sans-serif" font-size="11">{label}</text>'
        )
        x_text += 130

    elements.append("</svg>")
    return "\n".join(elements)


def main():
    repos = discover_repos()
    totals = aggregate(repos)
    calendar = calendar_stats()
    current, longest, total = compute_streaks(totals["weeks"])

    write(f"{ASSETS_DIR}/github-stats.svg", build_stats_svg(totals, calendar, len(repos)))
    write(f"{ASSETS_DIR}/github-streak.svg", build_streak_svg(current, longest, total))
    write(f"{ASSETS_DIR}/github-activity.svg", build_activity_svg(totals["weeks"], totals["by_year"]))

    print(
        json.dumps(
            {
                "repos": len(repos),
                "totals": totals,
                "calendar": {
                    "prs": calendar["totalPullRequestContributions"],
                    "issues": calendar["totalIssueContributions"],
                    "streak": {"current_weeks": current, "longest_weeks": longest, "commits": total},
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
