# Demo 3 Stage 0 Baseline Evidence

**Recorded:** 2026-08-03
**Demo 3 branch:** `demo3-approved-content-staging`
**Frozen Demo 2 commit:** `382635bd16d83f754fc3b57c52a4b51465df48a3`

## Recovery evidence

The unexplained pre-Demo 3 `app/main.py` rollback was preserved before the Demo 2
worktree was restored. It is recoverable from the local-only branch
`backup/pre-demo3-main-rollback-20260803` at commit `a4167d0`. The branch was not
pushed and is not part of Demo 3 history.

Departmental inputs that appeared as untracked files during verification were moved,
without content inspection, into a mode-`700` local quarantine directory outside the
Git worktree. They were not staged or committed.

## Release verification

The clean Demo 2 branch resolved to the expected commit before tagging. Observed
checks were:

```text
make format-check
56 files already formatted

make lint
All checks passed

make typecheck
Success: no issues found in 56 source files

make test
95 passed

OpenAPI version
0.2.0

python -m evaluations.run
60 of 60 cases passed; critical hallucinations: 0

docker compose config
configuration valid
```

The Docker client was installed inside the standard Docker Desktop application but
was not available through the shell's original `PATH`; running the same Compose
command with that binary directory on `PATH` succeeded.

## Immutable tag targets

Both release references are annotated tags:

```text
v0.2.0-demo2 -> 382635bd16d83f754fc3b57c52a4b51465df48a3
v0.1.0-demo1 -> 32b7b0e96260b1d7aa85cbbb5f1ad6bc19e4769b
```

`demo3-approved-content-staging` was created from `v0.2.0-demo2`. Neither release tag
was moved or recreated after creation.

## Repository instructions

`AGENTS.md` and the existing repository documentation were read. `rules.md` and
`skills.md` were not present; no empty substitutes were invented.
