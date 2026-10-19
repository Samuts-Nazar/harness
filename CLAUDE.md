# harness

## Rules for every session
- **Read `docs/decisions.md` before any work.** It is the source of truth for the design.
- Task briefs are in `tasks/` (`task1_code_study.md`, `task2_experiments.md`, `task3_core_skeleton.md`). Reports go to `reports/`, throwaway experiment code to `experiments/`.
- The OpenRouter API key is in `.env` as `OPENROUTER_API_KEY`. Load it with `python-dotenv` (`load_dotenv()`). **Never print, log, or commit it.** Show at most the first 8 characters if you must reference it.
- `data/` (witcher_books.txt, Ragnar.md) must **never be committed**, nor long excerpts from it. `.env` is also git-ignored.
- Respect the API budget stated in the task brief (task2: under 3 USD).

## Python environment (NixOS)
- Flake dev shell with Python 3, python-dotenv, httpx, pytest and uv: `nix develop` (or `nix develop --command <cmd>`).
- Run tests: `nix develop --command pytest`
- Key check (free endpoints only): `nix develop --command python check_key.py`
- New git-tracked files must be `git add`ed before `nix develop` can see changes to flake.nix.

## Branches and worktrees
- Work on a short-lived branch per task; at the end merge into main, push, verify with `git ls-remote origin`, then delete the branch and its worktree. Never leave unmerged branches or worktrees. Report all paths as full absolute paths.
