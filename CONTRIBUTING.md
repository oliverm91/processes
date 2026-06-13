# Contributing to Processes

Thanks for your interest in contributing! This document covers the two
contributor paths, project conventions, and how to submit a change.

## Contributor paths

**Maintainer** (direct push access): clone the repository directly.

```bash
git clone https://github.com/oliverm91/processes.git
cd processes
uv sync
```

**External contributor** (everyone else): fork first, then clone your fork.

```bash
# 1. Fork on GitHub (button top-right of the repo page)
# 2. Clone your fork
git clone https://github.com/<your-username>/processes.git
cd processes
uv sync
```

Both paths use [uv](https://docs.astral.sh/uv/) for dependency management.
`uv sync` installs all dev dependencies (pytest, mypy, ruff, mkdocs, commitizen).

## Project layout

```
src/processes/   # library source (the public package)
tests/           # pytest test suite
examples/        # runnable usage examples
docs/            # mkdocs documentation source
```

Keep new public symbols in `src/processes/` and re-export them from
`src/processes/__init__.py` if they are part of the stable API.

## Running checks locally

Before opening a pull request, make sure the following pass:

```bash
uv run pytest          # test suite
uv run mypy            # strict type checking
uv run ruff check .    # linting
uv run ruff format .   # formatting
```

CI runs the same checks on every push and pull request.

## Style guide

- Python >= 3.10 syntax.
- Type hints on all new code. `mypy` is configured with `strict = true` and
  `disallow_untyped_defs = true`.
- Ruff rules: `F`, `E`, `W`, `I`, `B`, `UP`. Line length is 100.
- Prefer the standard library — the library has zero runtime dependencies.
- No comments that just restate the code. A comment is welcome only when it
  captures a non-obvious *why*.

## Tests

- Add or update tests in `tests/` for any behavior change.
- Keep tests focused and deterministic; avoid sleeps where possible.
- If you fix a bug, add a regression test that fails before the fix.

## Commit messages

This project follows [Conventional Commits](https://www.conventionalcommits.org/),
enforced by [commitizen](https://commitizen-tools.github.io/commitizen/). Use
`uv run cz commit` to be prompted through an interactive commit, or write the
message by hand:

```
<type>(<scope>): <short description>

<optional body>

<optional footer>
```

Common types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`,
`build`, `ci`.

## Submitting a pull request

1. Create a feature branch: `git checkout -b feat/my-change`.
2. Make your changes, add tests, and confirm all checks pass.
3. Push the branch to your fork (or directly, if you're a maintainer) and open
   a PR against `main` on the upstream repository.
4. Fill in a clear description of the *what* and the *why*.
5. Make sure CI is green and the changelog preview looks reasonable for
   user-visible changes.
6. Be ready to revise — code review is a normal part of the process.

Prefer several small, focused PRs over one large one.

## Documentation

User-facing changes should be reflected in the docs under `docs/`. To preview
locally:

```bash
uv run mkdocs serve
```

## Versioning and releases

Versions are derived from git tags via `hatch-vcs` (`v$version`, e.g. `v2.0.1`).
Do not edit the version in `pyproject.toml` manually. To cut a release, the
maintainer runs:

```bash
uv run cz bump
```

This updates the version, regenerates the changelog, creates a tag, and
triggers the `publish.yml` workflow to push the release to PyPI.

## Reporting issues

Use the GitHub issue tracker. Please include:

- A minimal, self-contained reproduction.
- The Python version, library version, and operating system.
- The full traceback for crashes, and the smallest possible task graph that
  triggers the problem.

## License

By contributing, you agree that your contributions will be licensed under the
MIT License.