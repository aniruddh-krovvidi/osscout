# osscout: a daily open-source contribution loop for inference and ML-infra repos

A small set of scripts and one Claude Code skill that turn "contribute upstream"
into a repeatable morning routine. The agent finds, triages, reproduces, and
drafts. A human reads the diff, runs the tests, and pushes. That split is the
whole design: a contribution is only worth making if you can defend every line
of it to a maintainer.

```
scout_issues.py     rank recent open issues across ~30 repos; drop anything with an
                    open PR or a claim in the comments; print each repo's AI policy
skills/oss-contrib  the /oss-contrib skill: repro first, smallest fix, one test,
                    adversarial pass, then STOP for human review (never pushes)
check_diff.py       the gate: one commit, kebab or conventional subject, <= 40 lines,
                    <= 3 files, no reformatting, no lockfile edits, no debug prints
prtracker.csv       your funnel (gitignored); `scout_issues.py --funnel` reports
                    merge rate, merged-by-repo, and median diff size
```

## The loop

```
morning   python3 scout_issues.py              -> today.md (top ~12 tractable issues)
          pick one you actually understand
          /oss-contrib <issue url>             -> fork branch + PR_BODY.md, then stops
          read the diff. run the test yourself. if you can't explain the fix, don't ship it.
          push + gh pr create                  (you, by hand)
weekly    python3 scout_issues.py --funnel
```

Merged is the metric; opened is not. If the merge rate drops, the diffs are too
big or the issues too speculative: pick smaller ones, not more of them.

## What the scout scores

Labels (good-first-issue, help-wanted, bug up; RFC, feature, roadmap down),
whether the body has a traceback or repro, no assignee, few comments, recency.
It then spends two GitHub API calls per candidate to drop issues that already
have an open PR or a "/claim", "I'll take this" comment, because popular bugs
are swarmed within hours and a draft against a claimed issue is wasted work.
It also prints the AI-contribution clause from each shortlisted repo's
CONTRIBUTING.md, because those policies differ and you are responsible for
following them.

## What the gate enforces

Each rule in `check_diff.py` is something maintainers reject PRs for:
exactly one commit; a kebab-case 2-4 word subject or the repo's conventional
format; at most 40 changed lines and 3 files unless the PR body justifies more;
no whitespace-only or reformat-heavy hunks; no dependency or lockfile edits in a
bug fix; no debug prints, TODOs, or breakpoints left behind.

## The skill

`skills/oss-contrib/SKILL.md` is a Claude Code skill. Copy it to
`~/.claude/skills/oss-contrib/` and run `/oss-contrib <issue url>`. Its hard
rules: reproduce before editing (no repro, no PR); minimal diff; one red-to-green
test; an adversarial pass over every piece of shared state the diff touches;
follow the repo's CONTRIBUTING, PR template, and disclosure policy; never push,
never open the PR, never comment.

## Requirements

`gh` logged in, Python 3.10+, and a fork of each repo you want to contribute to.
The scout only reads from GitHub. The fixing step is intentionally not automated
past the draft.
