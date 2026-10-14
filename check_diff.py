#!/usr/bin/env python3
"""check_diff: the discipline gate. Run inside a checked-out fork branch before
pushing. Fails loudly if the change is bigger or noisier than it must be.

    python3 /path/to/check_diff.py [base-ref]      # default: origin/main or origin/master

Rules (each one is a thing maintainers reject PRs for):
  - commit subject: kebab-case 2-4 words, or a conventional commit where the
    repo requires one; trailers only when the repo's policy asks for them
  - one commit on the branch
  - diff budget: <= 40 changed lines, <= 3 files (override with --max-lines/--max-files
    when the issue genuinely needs it, and say why in the PR)
  - no whitespace-only / reformat-only hunks, no unrelated files, no new deps,
    no changes to lockfiles, no debug prints left behind
"""
import re, subprocess, sys

GIT = "git"
MSG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+){1,3}$")
# repos that mandate Conventional Commits: <type>(<scope>): <summary>, no capital, no period
CONVENTIONAL_RE = re.compile(r"^(feat|fix|docs|style|refactor|perf|test|chore|ci)(\([a-z0-9_-]+\))?: [a-z].{2,70}[^.]$")


def git(*a):
    return subprocess.run([GIT, *a], capture_output=True, text=True).stdout


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    max_lines = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--max-lines=")), 40))
    max_files = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--max-files=")), 3))
    base = args[0] if args else ("origin/main" if git("rev-parse", "--verify", "-q", "origin/main").strip() else "origin/master")
    problems = []

    n_commits = git("rev-list", "--count", f"{base}..HEAD").strip()
    if n_commits != "1":
        problems.append(f"{n_commits} commits on branch; squash to exactly 1")
    subject = git("log", "-1", "--format=%s").strip()
    if not (MSG_RE.match(subject) or CONVENTIONAL_RE.match(subject)):
        problems.append(f"commit subject '{subject}' is neither kebab-case 2-4 words (fix-null-tool-args) "
                        "nor a conventional commit (fix(scope): short summary) where the repo requires one")

    stat = git("diff", "--numstat", f"{base}..HEAD").strip().splitlines()
    files = [l.split("\t")[2] for l in stat if l]
    added = sum(int(l.split("\t")[0]) for l in stat if l and l.split("\t")[0].isdigit())
    removed = sum(int(l.split("\t")[1]) for l in stat if l and l.split("\t")[1].isdigit())
    if added + removed > max_lines:
        problems.append(f"diff is {added}+/{removed}- = {added+removed} lines (> {max_lines}); shrink it or justify")
    if len(files) > max_files:
        problems.append(f"{len(files)} files touched (> {max_files}): {files}")
    for f in files:
        if re.search(r"(package-lock|yarn\.lock|poetry\.lock|uv\.lock|Cargo\.lock|requirements.*\.txt|setup\.py|package\.json)$", f):
            problems.append(f"touches dependency/lock file {f}; a bug fix should not")
        elif f.endswith("pyproject.toml"):
            hunk = git("diff", f"{base}..HEAD", "--", f)
            if re.search(r"^[+-].*(dependencies|requires|version\s*=)", hunk, re.M):
                problems.append("pyproject.toml diff touches dependencies/version; a bug fix should not")

    ws_only = git("diff", "--ignore-all-space", "--ignore-blank-lines", "--numstat", f"{base}..HEAD").strip()
    if stat and not ws_only:
        problems.append("diff is whitespace-only")
    elif stat:
        real = sum(int(x) for l in ws_only.splitlines() for x in l.split("\t")[:2] if x.isdigit())
        if real < (added + removed) * 0.6:
            problems.append(f"only {real} of {added+removed} changed lines are non-whitespace; drop the reformatting")

    patch = git("diff", f"{base}..HEAD")
    for pat, why in [(r"^\+.*\b(print\(|console\.log\(|dbg!\(|fmt\.Println\()", "debug print added"),
                     (r"^\+.*\b(TODO|FIXME|XXX)\b", "TODO left in diff"),
                     (r"^\+.*(import pdb|breakpoint\(\))", "debugger call added")]:
        if re.search(pat, patch, re.M):
            problems.append(why)

    print(f"branch vs {base}: {n_commits} commit, {len(files)} file(s), +{added}/-{removed}")
    print(f"subject: {subject}")
    if problems:
        print("\nBLOCKED:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("\nOK: minimal. Now: tests pass? repo lint pass? PR body has the repro? Then push and open the PR yourself.")


if __name__ == "__main__":
    main()
