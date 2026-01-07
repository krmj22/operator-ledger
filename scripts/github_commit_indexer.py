#!/usr/bin/env python3
"""
Fetch commits from all personal GitHub repos using GitHub API.
Store in ledger/commit_index.yaml with structure:

repos:
  - name: operator
    commits:
      - sha: abc123
        message: "feat: add skill validation"
        author: user@example.com
        date: 2025-12-01
        files_changed: 3
        additions: 100
        deletions: 20
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import json

import yaml

try:
    import requests
except ImportError:
    print("Error: requests library required. Install with: pip install requests")
    sys.exit(1)


def get_github_token():
    """
    Get GitHub authentication token.

    Priority:
    1. GITHUB_TOKEN environment variable
    2. gh CLI config (gh auth token)

    Returns:
        str: GitHub token
    Raises:
        RuntimeError: If no token found
    """
    # Try environment variable first
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token

    # Try gh CLI
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
        )
        token = result.stdout.strip()
        if token:
            return token
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    raise RuntimeError(
        "No GitHub token found. Set GITHUB_TOKEN env var or authenticate with 'gh auth login'"
    )


def list_personal_repos():
    """
    Fetch all personal repositories for authenticated user.

    Returns:
        list: List of repo dictionaries with 'name' and 'url' keys
    """
    token = get_github_token()
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    repos = []
    page = 1
    per_page = 100

    while True:
        url = f"https://api.github.com/user/repos?per_page={per_page}&page={page}&type=owner"
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        page_repos = response.json()
        if not page_repos:
            break

        for repo in page_repos:
            repos.append({
                "name": repo["name"],
                "url": repo["html_url"],
                "full_name": repo["full_name"],
            })

        page += 1

    return repos


def fetch_commit_details(repo, sha, headers):
    """
    Fetch detailed commit info including files.

    Args:
        repo (dict): Repository dict with 'full_name' key
        sha (str): Commit SHA
        headers (dict): Request headers with auth

    Returns:
        list: List of file paths in the commit
    """
    url = f"https://api.github.com/repos/{repo['full_name']}/commits/{sha}"
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        files_data = data.get("files", [])
        return [f["filename"] for f in files_data]
    except Exception:
        # If fetch fails, return empty list
        return []


def fetch_commits(repo, since_date=None, fetch_files=True):
    """
    Fetch commits from a repository.

    Args:
        repo (dict): Repository dict with 'full_name' key
        since_date (str): ISO date string (YYYY-MM-DD) to fetch commits after
        fetch_files (bool): Whether to fetch file lists (requires extra API calls)

    Returns:
        list: List of commit dictionaries with metadata
    """
    token = get_github_token()
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    commits = []
    page = 1
    per_page = 100

    # Build URL with since parameter if provided
    base_url = f"https://api.github.com/repos/{repo['full_name']}/commits"
    params = {"per_page": per_page}

    if since_date:
        # Convert YYYY-MM-DD to ISO 8601 format required by GitHub API
        params["since"] = f"{since_date}T00:00:00Z"

    while True:
        params["page"] = page
        response = requests.get(base_url, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        page_commits = response.json()
        if not page_commits:
            break

        for commit_data in page_commits:
            commit = commit_data["commit"]
            stats = commit_data.get("stats", {})
            sha = commit_data["sha"]

            # Fetch file list if requested (requires individual commit API call)
            files = []
            if fetch_files:
                files = fetch_commit_details(repo, sha, headers)

            commits.append({
                "sha": sha,
                "message": commit["message"],
                "author": commit["author"]["email"],
                "date": commit["author"]["date"],
                "files": files,
                "files_changed": len(files) if fetch_files else stats.get("total", 0),
                "additions": stats.get("additions", 0),
                "deletions": stats.get("deletions", 0),
            })

        # Check if there are more pages
        if len(page_commits) < per_page:
            break

        page += 1

    return commits


def index_commits(output_path=None, since_date=None):
    """
    Fetch commits from all personal repos and write to YAML index.

    Args:
        output_path (str): Path to output YAML file (default: ledger/commit_index.yaml)
        since_date (str): ISO date string (YYYY-MM-DD) to fetch commits after
    """
    if output_path is None:
        # Default to ledger/commit_index.yaml
        script_dir = Path(__file__).parent
        ledger_dir = script_dir.parent
        output_path = ledger_dir / "commit_index.yaml"
    else:
        output_path = Path(output_path)

    # Load existing index if it exists (for incremental updates)
    existing_data = {}
    if output_path.exists():
        with open(output_path) as f:
            existing_data = yaml.safe_load(f) or {}

    print(f"Fetching personal repositories...")
    repos = list_personal_repos()
    print(f"Found {len(repos)} repositories")

    index_data = {
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "repos": [],
    }

    for repo in repos:
        print(f"Fetching commits from {repo['name']}...")
        new_commits = fetch_commits(repo, since_date=since_date)

        # Merge with existing commits for this repo
        existing_repo = None
        if existing_data.get("repos"):
            existing_repo = next(
                (r for r in existing_data["repos"] if r["name"] == repo["name"]),
                None
            )

        if existing_repo:
            # Merge commits, deduplicate by SHA
            existing_shas = {c["sha"] for c in existing_repo["commits"]}
            merged_commits = existing_repo["commits"].copy()

            for commit in new_commits:
                if commit["sha"] not in existing_shas:
                    merged_commits.append(commit)

            commits = merged_commits
            print(f"  Found {len(new_commits)} new commits, {len(commits)} total")
        else:
            # New repo, use all commits
            commits = new_commits
            print(f"  Found {len(commits)} commits")

        index_data["repos"].append({
            "name": repo["name"],
            "url": repo["url"],
            "commits": commits,
        })

    # Write to YAML
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.dump(index_data, f, default_flow_style=False, sort_keys=False)

    total_commits = sum(len(r["commits"]) for r in index_data["repos"])
    print(f"\nIndexing complete!")
    print(f"Total commits indexed: {total_commits}")
    print(f"Output: {output_path}")


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Index commits from personal GitHub repositories"
    )
    parser.add_argument(
        "--since",
        type=str,
        help="Fetch commits since this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path (default: ledger/commit_index.yaml)",
    )

    args = parser.parse_args()

    try:
        index_commits(output_path=args.output, since_date=args.since)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
