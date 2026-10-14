---
name: oss-contrib
description: Take one open-source GitHub issue (URL as argument) from reproduction to a review-ready minimal fix on a local fork branch, then STOP for the human to review, test, and push. Use when the user runs /oss-contrib <issue-url> or asks to work an upstream issue in an inference or ML-infrastructure repo. Never pushes, never opens PRs, never comments on GitHub.
---

# oss-contrib: one issue, smallest correct diff

Argument: an issue URL. Work in `<workdir>/oss/<repo-name>/` (clone the user's
fork if it exists, else clone upstream and tell the user to fork).

## Hard rules (do not soften)

1. **Reproduce before touching code.** Write the smallest runnable repro
   (a 5-15 line script or a single failing test). If you cannot reproduce in
   about 20 minutes, stop, record `repro_failed` in the tracker with what you
   tried, and move to the next issue. No repro, no PR.
2. **Minimal diff.** Fix the cause, not the symptom. Do not reformat, rename,
   refactor, add type hints, fix nearby typos, or "improve" anything the issue
   did not ask for. Prefer the fix with fewer changed lines when two are
   equally correct. Budget: 40 changed lines, 3 files, 1 commit. Exceeding it
   needs a one-line justification in the PR body.
3. **Match the house style** of the surrounding code exactly (quotes, naming,
   error style). Run the repo's own formatter and linter only on the lines you
   changed, never repo-wide.
4. **Tests.** Add or extend ONE test that fails before and passes after, in
   the repo's existing test layout. Run the narrowest relevant test target.
5. **Commit message:** kebab-case, 2-4 words, imperative, no body:
   `fix-zero-arg-tool-call`, `guard-empty-mask`, `use-ceil-div`. Use the
   repo's conventional-commit format instead where it requires one. Add only
   the trailers the repo's policy asks for (`Signed-off-by`, `Assisted-by`).
   The commit author is the human, never the agent.
6. **Follow the repo's CONTRIBUTING.md and PR template**, including any
   AI-assistance disclosure requirement. Surface that requirement to the user
   verbatim in the handoff; the user decides how to fill in the PR form.
7. **Never push. Never open the PR. Never comment on the issue.** The human
   does every outward-facing step after reading the diff.

## Steps

1. `gh issue view <url> --comments`: read fully. Check for linked or open PRs
   (`gh pr list --search "<issue number>"`); if one exists, stop and say so.
2. Set up: fork check, clone, create branch `fix/<issue-number>-<kebab>` from
   the upstream default branch. Install per the repo docs into a venv; do not
   modify the environment globally.
3. Repro: write `repro_<n>.py` (or the failing test) at the repo root, run it,
   paste the failing output into the handoff. This file is NOT committed.
4. Locate the cause with the narrowest search. Read the surrounding code and
   `git blame` before editing.
5. Fix. Re-run the repro (passes) and the narrowest test target (passes).
6. Add or extend one test. Run it red, then green.
7. **Adversarial pass before committing.** For every piece of shared state the
   diff touches (a map, a reservation, a status entry), write down in the
   handoff: who creates it, every path that removes it, and what happens on
   each failure path and with two concurrent callers. Any transition with no
   owner or no cleanup is a bug the reviewer will find. Prefer removing a
   mechanism over adding one; a new mechanism must have exactly one owner and
   one cleanup path. If a local review tool is available (for example the
   CodeRabbit CLI), run it on the committed diff and resolve every finding.
   **Whole-diff pass, every line** (`git diff <base>..HEAD`, read it all, never
   from memory). For each hunk ask, in order: does this need to exist at all;
   does the stdlib, the platform, or an existing dependency already do it; can
   it be one line; is anything here unrelated to the issue or the review
   findings. Then for the whole change: can a reorder remove a failure path
   instead of adding a cleanup for it; can two branches collapse into one.
   Apply every cut, re-run tests, and report the production-vs-test line
   split in the handoff. Commit (rule 5). Run `check_diff.py` and fix anything
   it flags. **Repeat the whole-diff pass after every review round**, including
   after final approval, before the last push.
8. Write the PR body to `PR_BODY.md` at the repo root (not committed). As
   short as the repo's rules allow, and no shorter. First read the repo's PR
   template, CONTRIBUTING.md and AGENTS.md and list what they require. Include
   exactly those items plus the four facts a reviewer needs:
   ```
   Fixes #<n>
   cause (1-2 sentences)
   change (1-2 sentences)
   test: name, fails before / passes after
   ```
   Plain, factual, no adjectives. Follow the repo's disclosure policy for
   tooling. Anything the human has not yet done (a hardware run) goes in as a
   visible PLACEHOLDER, never as a claim.
9. Append a `drafted` row to `prtracker.csv`
   (`date,repo,issue_url,,branch,drafted,<diff lines>,<one-line note>`).
10. Handoff message: the diff, the repro output before and after, the test
    command and result, the repo's AI-disclosure clause if any, and the exact
    commands to push and open the PR. Then stop.

## Quality bar

A maintainer should be able to review the PR in under two minutes: obvious
cause, obvious fix, a test that proves it, nothing else in the diff.
