# Tagged Release Publishing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable Windows packaging script and a tag-triggered GitHub Actions workflow that publishes the same tagged build to GitHub Releases and PyPI.

**Architecture:** `scripts/package-release.ps1` is the single packaging/validation entry point and writes all six release files to `outputs/release/vX.Y.Z`. `.github/workflows/release.yml` checks out the pushed tag, runs that script on Windows Python 3.12, stores the complete directory as a workflow artifact, then creates a draft GitHub Release, publishes wheel/sdist through PyPI Trusted Publishing, and publishes the GitHub Release.

**Tech Stack:** PowerShell 7-compatible Windows script, Python `build`/`twine`/PyInstaller, GitHub Actions, GitHub CLI, PyPI Trusted Publishing via `pypa/gh-action-pypi-publish`.

## Global Constraints

- Trigger only on tags matching `v*.*.*`.
- Require the tag version and `pyproject.toml` version to match exactly.
- Use Windows + Python 3.12 for tests and packaging.
- Build both wheel and source distribution, plus `luna-agent.exe`, plugin ZIP, Skill ZIP, and `SHA256SUMS.txt`.
- Run `python -m unittest discover -s tests -q`, `python -m twine check`, plugin validation, and EXE version validation before publishing.
- Publish to PyPI with OIDC Trusted Publishing; do not add a PyPI token to repository files.
- Do not move, force-update, or overwrite existing tags; `v0.1.1` remains unchanged.
- Do not commit or push automatically; leave all changes in the current working tree for user review.

---

### Task 1: Add deterministic release packaging script

**Files:**
- Create: `scripts/package-release.ps1`
- Modify: `tests/test_release_layout.py`

**Interfaces:**
- Consumes: `-Version` such as `0.1.2`; repository files; the current Python 3.12 environment.
- Produces: `outputs/release/v<Version>/luna-agent.exe`, wheel, sdist, plugin ZIP, Skill ZIP, and `SHA256SUMS.txt`; exits nonzero on any validation failure.

- [ ] **Step 1: Add layout assertions for the script and workflow contract**

  Extend `ReleaseLayoutTests` to require `scripts/package-release.ps1` and assert that it contains the version check, `python -m unittest discover -s tests -q`, `python -m twine check`, `SHA256SUMS.txt`, and the six expected output names.

- [ ] **Step 2: Run the focused layout tests and verify the new assertions fail**

  Run:

  ```powershell
  .\.venv\Scripts\python.exe -m unittest tests.test_release_layout -q
  ```

  Expected: failure because `scripts/package-release.ps1` does not exist yet.

- [ ] **Step 3: Implement `scripts/package-release.ps1`**

  The script must:

  1. Stop on errors and accept mandatory `-Version`.
  2. Validate `-Version` with `^\d+\.\d+\.\d+$` and compare it with the `version = "..."` value in `pyproject.toml`.
  3. Resolve `.venv\Scripts\python.exe`, create the virtual environment if absent, and install `build`, `twine`, and `pyinstaller>=6,<7`.
  4. Run the full unittest command.
  5. Remove only the script-owned `build`, `dist`, and versioned output directory before building; never remove source files or other release versions.
  6. Run `python -m build --outdir <release-dir>` to create wheel and sdist.
  7. Run PyInstaller with `scripts\launcher.py`, `src` on the import path, and `assets;assets` bundled, then copy `dist\luna-agent.exe` into the release directory and assert `--version` equals the requested version.
  8. Compress `plugins\luna-agent-bridge` and its `skills\luna-agent-bridge` directory into the plugin and Skill ZIP names.
  9. Run the plugin validator against `plugins\luna-agent-bridge`.
  10. Run `python -m twine check` on exactly the generated wheel and sdist.
  11. Generate `SHA256SUMS.txt` with uppercase SHA256 values and stable filenames.
  12. Print the final output directory and fail if any expected file is missing.

- [ ] **Step 4: Run the focused layout tests again**

  Run:

  ```powershell
  .\.venv\Scripts\python.exe -m unittest tests.test_release_layout -q
  ```

  Expected: pass, including the packaging-script assertions.

### Task 2: Add tag-triggered GitHub Release and PyPI workflow

**Files:**
- Create: `.github/workflows/release.yml`
- Modify: `tests/test_release_layout.py`

**Interfaces:**
- Consumes: pushed tags matching `v*.*.*`; `pypi` GitHub Environment; PyPI Trusted Publisher registration.
- Produces: a published GitHub Release and PyPI version using artifacts built from the exact tag commit.

- [ ] **Step 1: Add workflow contract tests**

  Extend `test_github_ci_and_feedback_entrypoints_exist` or add a separate test that checks `release.yml` for `tags:`, `v*.*.*`, `windows-latest`, Python `3.12`, `package-release.ps1`, `actions/upload-artifact`, `actions/download-artifact`, `pypa/gh-action-pypi-publish`, `id-token: write`, `contents: write`, `gh release create`, and `gh release edit`.

- [ ] **Step 2: Run the focused tests and verify the new workflow assertions fail**

  Run:

  ```powershell
  .\.venv\Scripts\python.exe -m unittest tests.test_release_layout -q
  ```

  Expected: failure because `.github/workflows/release.yml` does not exist yet.

- [ ] **Step 3: Implement `.github/workflows/release.yml`**

  Configure:

  - `on.push.tags: ["v*.*.*"]` and `workflow_dispatch` omitted to prevent accidental untagged publishing.
  - A Windows `build` job using `windows-latest`, Python `3.12`, `actions/checkout@v4` with the pushed ref, and `scripts\package-release.ps1 -Version ...` where the leading `v` is removed.
  - Upload the complete `outputs/release/v<Version>` directory as one artifact.
  - A `publish` job dependent on `build`, with `contents: write` and `id-token: write`, running on `ubuntu-latest`.
  - Download the artifact, create a draft release with `gh release create --draft --verify-tag`, upload all six files, and use `pypa/gh-action-pypi-publish@release/v1` under environment `pypi` with URL `https://pypi.org/p/luna-agent-bridge`.
  - Publish the release only after PyPI succeeds using `gh release edit --draft=false`.
  - Set `GH_TOKEN: ${{ github.token }}` for GitHub CLI operations and fail if the release already exists rather than overwriting a public release.

- [ ] **Step 4: Run the focused layout tests again**

  Run:

  ```powershell
  .\.venv\Scripts\python.exe -m unittest tests.test_release_layout -q
  ```

  Expected: pass, including all release workflow assertions.

### Task 3: Document one-time PyPI setup and release usage

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: `.github/workflows/release.yml` and the PyPI Trusted Publishing setup.
- Produces: user-facing instructions that explain the one-time setup and the single tag push used for later releases.

- [ ] **Step 1: Add the release automation section**

  Document the required PyPI Trusted Publisher fields: owner `ZaviWayne`, repository `luna-agent-bridge`, workflow `.github/workflows/release.yml`, and environment `pypi`. Document the release sequence:

  ```powershell
  # Update pyproject.toml version first, then commit it.
  git tag v0.1.2
  git push origin v0.1.2
  ```

  State that the workflow builds from the tag and publishes both GitHub Release assets and PyPI distributions, and that existing tags must not be moved.

- [ ] **Step 2: Run documentation and release layout tests**

  Run:

  ```powershell
  .\.venv\Scripts\python.exe -m unittest tests.test_release_layout -q
  ```

  Expected: pass.

### Task 4: Verify the complete implementation locally

**Files:**
- Test: `scripts/package-release.ps1`
- Test: `.github/workflows/release.yml`
- Test: `tests/test_release_layout.py`

**Interfaces:**
- Consumes: current working tree and local Python 3.12 environment.
- Produces: verified packaging script, workflow contract, and release artifacts without committing or publishing.

- [ ] **Step 1: Run all automated tests**

  Run:

  ```powershell
  .\.venv\Scripts\python.exe -m unittest discover -s tests -q
  ```

  Expected: all tests pass.

- [ ] **Step 2: Run the packaging script against the current version**

  Run:

  ```powershell
  .\scripts\package-release.ps1 -Version 0.1.1
  ```

  Expected: the six files are generated under `outputs\release\v0.1.1`, `twine check` passes, and the executable reports `0.1.1`.

- [ ] **Step 3: Inspect the final diff and leave it uncommitted**

  Run:

  ```powershell
  git diff --check
  git status --short
  ```

  Expected: no whitespace errors; only the intended script, workflow, test, documentation, design, and plan changes are present. Do not run `git commit`, `git push`, or a real release from the local verification step.
