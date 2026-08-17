# Tagged Release Publishing Design

## Goal

Make a new version release reproducible and mostly one-command: pushing a version tag builds the Windows executable and Python distributions, publishes the package to PyPI, and creates a GitHub Release containing all distributable files.

## Scope

- Trigger only from tags matching `v*.*.*`.
- Require the tag version, `pyproject.toml` version, and generated artifact versions to match.
- Run the existing test suite on Windows with Python 3.12.
- Build the Python wheel and source distribution, Windows single-file executable, Codex plugin archive, Skill archive, and `SHA256SUMS.txt`.
- Publish Python distributions through PyPI Trusted Publishing using GitHub Actions OIDC; no PyPI API token is stored in the repository.
- Create a draft GitHub Release from the exact pushed tag, upload all six release assets, and publish the Release only after PyPI publishing succeeds.
- Do not move or overwrite existing tags. The already-published `v0.1.1` remains unchanged; the workflow is intended for the next release, such as `v0.1.2`.

## Architecture

`scripts/package-release.ps1` owns deterministic packaging and validation. It reads the version from `pyproject.toml`, receives the tag version from the workflow, builds into `outputs/release/vX.Y.Z`, runs tests and `twine check`, validates the executable version, and writes the checksums file.

`.github/workflows/release.yml` runs on a pushed version tag. A Windows job checks out that exact tag and invokes the packaging script, then uploads the complete release directory as a workflow artifact. A publish job downloads the artifact, creates a draft GitHub Release with `gh`, publishes wheel and sdist to PyPI with Trusted Publishing, and finally changes the GitHub Release from draft to published.

## Release flow

1. The maintainer updates `pyproject.toml` and the package version, commits the change, and pushes a tag such as `v0.1.2` pointing to that commit.
2. The workflow verifies that the tag version equals the project version.
3. Windows CI runs all tests and builds all release files from the tagged checkout.
4. The packaging step validates the EXE version, wheel/sdist metadata, plugin manifest, and SHA256 checksums.
5. The workflow creates a draft GitHub Release and uploads the EXE, wheel, sdist, plugin ZIP, Skill ZIP, and checksum file.
6. The PyPI job publishes only the wheel and sdist through the `pypi` GitHub Environment.
7. After PyPI succeeds, the workflow publishes the GitHub Release.

## Failure handling

- A version mismatch stops the workflow before building or publishing.
- Test, packaging, metadata, plugin validation, or checksum failures stop the workflow before external publishing.
- A PyPI failure leaves the GitHub Release as a draft so the maintainer can inspect the artifacts.
- Existing public tags are never force-updated by automation.
- The workflow requires a manually configured PyPI Trusted Publisher for repository `ZaviWayne/luna-agent-bridge`, workflow `.github/workflows/release.yml`, and GitHub Environment `pypi`.

## Verification

- Local packaging script can be run with `.\scripts\package-release.ps1 -Version 0.1.2` before pushing a tag.
- CI runs `python -m unittest discover -s tests -q` on Windows Python 3.12.
- CI runs `python -m twine check` against both Python distributions.
- CI runs the plugin validator and `luna-agent.exe --version`.
- The final GitHub Release asset list and PyPI version are visible in the workflow summary.
