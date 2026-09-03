#!/usr/bin/env python3
import json
import os
import subprocess
import sys

USERNAME = os.environ.get("GITHUB_USERNAME", "JP-Schuster")
TOKEN = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")
OUTPUT = os.environ.get("STATS_OUTPUT", "assets/github-stats.svg")


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
    totals = {"commits": 0, "additions": 0, "deletions": 0}
    for repo in repos:
        owner, name = repo.split("/", 1)
        for author in contributor_stats(owner, name):
            login = (author.get("author") or {}).get("login")
            if login != USERNAME:
                continue
            weeks = author.get("weeks", [])
            totals["commits"] += sum(w.get("c", 0) for w in weeks)
            totals["additions"] += sum(w.get("a", 0) for w in weeks)
            totals["deletions"] += sum(w.get("d", 0) for w in weeks)
            break
    return totals


def calendar_stats():
    data = graphql(
        'query { user(login: "%s") { contributionsCollection { totalCommitContributions totalPullRequestContributions totalIssueContributions totalRepositoryContributions contributionCalendar { totalContributions } } } }'
        % USERNAME
    )
    stats = data["data"]["user"]["contributionsCollection"]
    try:
        prs = json.loads(gh("api", f"search/issues?q=author:{USERNAME}+type:pr&per_page=1"))
        stats["totalPullRequestContributions"] = prs.get("total_count", stats["totalPullRequestContributions"])
    except subprocess.CalledProcessError:
        pass
    try:
        issues = json.loads(gh("api", f"search/issues?q=author:{USERNAME}+type:issue&per_page=1"))
        stats["totalIssueContributions"] = issues.get("total_count", stats["totalIssueContributions"])
    except subprocess.CalledProcessError:
        pass
    return stats


def fmt(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def build_svg(totals, calendar, repo_count):
    commits = totals["commits"]
    additions = totals["additions"]
    deletions = totals["deletions"]
    prs = calendar["totalPullRequestContributions"]
    issues = calendar["totalIssueContributions"]
    contributed = repo_count
    activity = calendar["contributionCalendar"]["totalContributions"]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="520" height="200" viewBox="0 0 520 200" role="img" aria-label="GitHub stats for {USERNAME}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#1a1b27"/>
      <stop offset="100%" stop-color="#24283b"/>
    </linearGradient>
  </defs>
  <rect width="520" height="200" rx="10" fill="url(#bg)"/>
  <text x="24" y="34" fill="#7aa2f7" font-family="Segoe UI, Ubuntu, sans-serif" font-size="18" font-weight="700">{USERNAME} GitHub Stats</text>
  <text x="24" y="56" fill="#a9b1d6" font-family="Segoe UI, Ubuntu, sans-serif" font-size="12">Inclui repos pessoais + organizations</text>

  <text x="24" y="92" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Total Commits</text>
  <text x="24" y="118" fill="#9ece6a" font-family="Segoe UI, Ubuntu, sans-serif" font-size="24" font-weight="700">{commits:,}</text>

  <text x="170" y="92" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Total PRs</text>
  <text x="170" y="118" fill="#bb9af7" font-family="Segoe UI, Ubuntu, sans-serif" font-size="24" font-weight="700">{prs:,}</text>

  <text x="290" y="92" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Issues</text>
  <text x="290" y="118" fill="#f7768e" font-family="Segoe UI, Ubuntu, sans-serif" font-size="24" font-weight="700">{issues:,}</text>

  <text x="390" y="92" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Repos</text>
  <text x="390" y="118" fill="#e0af68" font-family="Segoe UI, Ubuntu, sans-serif" font-size="24" font-weight="700">{contributed:,}</text>

  <text x="24" y="156" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Linhas adicionadas</text>
  <text x="24" y="182" fill="#9ece6a" font-family="Segoe UI, Ubuntu, sans-serif" font-size="20" font-weight="700">+{fmt(additions)}</text>

  <text x="260" y="156" fill="#c0caf5" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13">Linhas removidas</text>
  <text x="260" y="182" fill="#f7768e" font-family="Segoe UI, Ubuntu, sans-serif" font-size="20" font-weight="700">-{fmt(deletions)}</text>

  <text x="430" y="182" fill="#565f89" font-family="Segoe UI, Ubuntu, sans-serif" font-size="11">Atividade: {activity}</text>
</svg>
"""


def main():
    repos = discover_repos()
    totals = aggregate(repos)
    calendar = calendar_stats()
    svg = build_svg(totals, calendar, len(repos))
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(json.dumps({"repos": len(repos), "totals": totals, "calendar": calendar}, indent=2))


if __name__ == "__main__":
    main()
