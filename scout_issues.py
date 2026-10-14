#!/usr/bin/env python3
"""osscout: find tractable open-source issues in ML-inference / infra repos and
rank them by how likely a minimal, reviewable fix is. Never touches GitHub
beyond reads. Uses `gh` (authenticated) for the API.

    python3 scout_issues.py             # today's shortlist -> today.md + stdout
    python3 scout_issues.py --repo sgl-project/sglang --limit 15
    python3 scout_issues.py --funnel    # PR funnel from prtracker.csv
"""
import csv, json, os, re, subprocess, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
TRACKER = os.path.join(HERE, "prtracker.csv")
TODAY = os.path.join(HERE, "today.md")

REPOS = [
    "vllm-project/vllm", "sgl-project/sglang", "smg-project/smg", "sgl-project/genai-bench",
    "NVIDIA/TensorRT-LLM", "triton-lang/triton", "ggml-org/llama.cpp", "flashinfer-ai/flashinfer",
    "vllm-project/llm-compressor", "kvcache-ai/ktransformers", "huggingface/transformers",
    # Active repos that merge outside contributions; edit freely.
    "Luce-Org/lucebox", "NVlabs/cuda-oxide", "NVlabs/cutile-rs", "FlashML-org/FreeToken",
    "mudler/LocalAI", "experientiallabs/experiential", "warpfront/hipfire",
    "Avarok-Cybersecurity/atlas", "syv-ai/HyperQwen",
    "NVIDIA/Model-Optimizer", "ai-dynamo/dynamo", "pytorch/ao", "ml-explore/mlx-lm",
    "huggingface/tokenizers", "huggingface/candle", "Dao-AILab/flash-attention",
    "LMCache/LMCache",
]

GOOD_LABELS = {"good first issue": 6, "help wanted": 4, "bug": 3, "documentation": 2, "docs": 2,
               "easy": 4, "beginner": 4, "low priority": 1, "usability": 1}
BAD_LABELS = {"feature": -4, "rfc": -8, "discussion": -6, "question": -5, "roadmap": -10,
              "wontfix": -10, "needs-triage": 0, "stale": -6, "duplicate": -10, "performance": -1}
TITLE_GOOD = [("typo", 5), ("docs", 3), ("doc ", 3), ("readme", 3), ("error message", 4), ("crash", 2),
              ("assert", 2), ("traceback", 3), ("flaky", 3), ("test", 2), ("missing", 2), ("wrong", 2),
              ("off by one", 5), ("incorrect", 2), ("regression", 2), ("cli", 2), ("flag", 2), ("arg", 2)]
TITLE_BAD = [("support", -3), ("feature request", -6), ("add support", -5), ("new model", -6),
             ("kernel", -2), ("multi-node", -3), ("distributed", -2), ("nccl", -3), ("cuda graph", -3),
             ("rfc", -8), ("proposal", -6), ("tracking", -8), ("umbrella", -8), ("roadmap", -10)]


def gh(args):
    out = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(out.stderr.strip()[:200])
    return out.stdout


def issues(repo, limit=100):
    q = (f"repos/{repo}/issues?state=open&sort=created&direction=desc&per_page={limit}")
    return [i for i in json.loads(gh(["api", q])) if "pull_request" not in i]


def score(i):
    s = 0
    labels = [l["name"].lower() for l in i.get("labels", [])]
    for l in labels:
        s += GOOD_LABELS.get(l, 0) + BAD_LABELS.get(l, 0)
    t = (i["title"] or "").lower()
    for k, w in TITLE_GOOD + TITLE_BAD:
        if k in t:
            s += w
    body = (i.get("body") or "").lower()
    if "traceback" in body or "```" in body:
        s += 3                                     # has a repro or stack trace
    if "expected behavior" in body or "steps to reproduce" in body:
        s += 2
    if len(body) < 150:
        s -= 2                                     # too thin to reproduce
    if i.get("assignee") or i.get("assignees"):
        s -= 8                                     # someone owns it
    c = i.get("comments", 0)
    s += 2 if c == 0 else (1 if c <= 2 else (-1 if c <= 6 else -4))
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(i["created_at"].replace("Z", "+00:00"))).days
    s += 2 if age <= 7 else (0 if age <= 30 else -2)
    return s


CLAIMED = re.compile(r"/claim\b|can i take|i can (send|submit)|i('d| would) like to (solve|take|fix)|i'?ll take|working on (a|the) (fix|pr)", re.I)


def claimed_by(repo, number, n_comments):
    """Login of the first commenter who claimed the issue, else None (0 comments: no API call)."""
    if not n_comments:
        return None
    import time
    time.sleep(2.1)
    try:
        comments = json.loads(gh(["api", f"repos/{repo}/issues/{number}/comments?per_page=30"]))
    except RuntimeError:
        return None
    return next((c["user"]["login"] for c in comments if CLAIMED.search(c.get("body") or "")), None)


def open_prs(repo, number):
    """Open PRs that reference this issue number (GitHub search; ~30 req/min, so sleep a little)."""
    import time
    time.sleep(2.1)
    try:
        q = f"search/issues?q=repo:{repo}+is:pr+is:open+{number}&per_page=5"
        return json.loads(gh(["api", q])).get("total_count", 0)
    except RuntimeError:
        return 0


def ai_policy(repo):
    """One-line note if the repo's CONTRIBUTING mentions AI-generated code."""
    for path in ("CONTRIBUTING.md", ".github/CONTRIBUTING.md", "docs/contributing.md", "CONTRIBUTING.rst"):
        try:
            txt = subprocess.run(["gh", "api", f"repos/{repo}/contents/{path}", "-H", "Accept: application/vnd.github.raw"],
                                 capture_output=True, text=True, timeout=20).stdout
        except Exception:
            continue
        if not txt:
            continue
        for pat in (r"AI[- ](generated|assisted|usage|written) ", r"use of AI|AI tools?\b", r"ChatGPT|Copilot|LLM[- ]generated|generated code"):
            hit = re.search(r"[^\n]*(" + pat + r")[^\n]*", txt, re.I)
            if hit:
                return "policy: " + hit.group(0).strip()[:160]
        return "no AI clause in CONTRIBUTING"
    return "no CONTRIBUTING found"


def main():
    if "--funnel" in sys.argv:
        return funnel()
    repos = REPOS
    if "--repo" in sys.argv:
        repos = [sys.argv[sys.argv.index("--repo") + 1]]
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 12
    seen = set()
    if os.path.exists(TRACKER):
        seen = {r["issue_url"] for r in csv.DictReader(open(TRACKER))}

    rows = []
    for repo in repos:
        try:
            for i in issues(repo):
                if i["html_url"] in seen:
                    continue
                rows.append((score(i), repo, i))
        except RuntimeError as e:
            print(f"! {repo}: {e}", file=sys.stderr)
    rows.sort(key=lambda r: -r[0])
    # Popular bugs get swarmed within hours: drop any candidate that already has an open PR.
    top = []
    for s, repo, i in rows[:limit * 3]:
        n = open_prs(repo, i["number"])
        if n:
            print(f"  skip {repo}#{i['number']}: {n} open PR(s) already", file=sys.stderr)
            continue
        who = claimed_by(repo, i["number"], i["comments"])
        if who:
            print(f"  skip {repo}#{i['number']}: claimed in comments by {who}", file=sys.stderr)
            continue
        top.append((s, repo, i))
        if len(top) == limit:
            break

    lines = [f"# osscout shortlist — {datetime.now():%Y-%m-%d}", ""]
    for s, repo, i in top:
        labels = ", ".join(l["name"] for l in i["labels"]) or "-"
        lines.append(f"- **[{s:+d}] {repo}#{i['number']}** {i['title'].strip()}  \n"
                     f"  {i['html_url']}  · labels: {labels} · comments: {i['comments']}")
    lines += ["", "## Repo AI-disclosure policies (read before opening a PR)", ""]
    for repo in sorted({r for _, r, _ in top}):
        lines.append(f"- {repo}: {ai_policy(repo)}")
    lines += ["", "Next: pick one and run `/oss-contrib <issue url>` (skills/oss-contrib). It reproduces first,",
              "then fixes with the smallest diff, then stops for you to review, test, and push."]
    open(TODAY, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


def funnel():
    if not os.path.exists(TRACKER):
        print("no prtracker.csv yet"); return
    rows = list(csv.DictReader(open(TRACKER)))
    stages = ["triaged", "repro_failed", "drafted", "opened", "changes_requested", "merged", "closed"]
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in stages}
    for s in stages:
        print(f"{s:<18}{counts[s]}")
    opened = counts["opened"] + counts["changes_requested"] + counts["merged"] + counts["closed"]
    if opened:
        print(f"\nmerge rate: {counts['merged']/opened:.0%} of {opened} opened")
    by_repo = {}
    for r in rows:
        if r["status"] == "merged":
            by_repo[r["repo"]] = by_repo.get(r["repo"], 0) + 1
    if by_repo:
        print("merged by repo:", by_repo)
    locs = [int(r["diff_lines"]) for r in rows if r.get("diff_lines", "").isdigit()]
    if locs:
        print(f"median diff size: {sorted(locs)[len(locs)//2]} lines")


if __name__ == "__main__":
    main()
