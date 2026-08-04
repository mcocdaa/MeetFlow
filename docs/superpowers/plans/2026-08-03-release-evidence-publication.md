# Release Evidence Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make each successful tag release retain a machine-readable immutable image reference and manifest inspection as Actions artifacts and GitHub Release assets, without changing GHCR publication or server-update policy.

**Architecture:** Keep GHCR as the only image distribution channel. After Buildx pushes the existing multi-platform manifest, the release workflow consumes its digest output, inspects that exact manifest from the registry, and invokes a small standard-library Python script to write stable JSON and human-readable release notes. The workflow uploads those files to Actions and creates or refreshes a GitHub Release idempotently; it never builds or uploads `docker save` archives and never deploys to a server.

**Tech Stack:** GitHub Actions, Docker Buildx, GitHub CLI on Ubuntu runner, Python 3.12 standard library, pytest.

---

## File structure

- `.github/workflows/release.yml`: captures the pushed manifest digest, emits release evidence, uploads it as a workflow artifact, and creates/refreshes the tag's GitHub Release.
- `scripts/write_release_metadata.py`: converts workflow inputs into deterministic `release-metadata.json` and `release-notes.md` files.
- `backend/tests/test_release_metadata.py`: executes the metadata script and asserts the public JSON/notes contract.
- `backend/tests/test_release_workflow.py`: asserts that release workflow wiring preserves the existing image contract and adds evidence/release publication requirements.
- `docs/release.md`: documents where operators find immutable image identity, platform inspection, SBOM/provenance, and the unchanged manual update boundary.

### Task 1: Define and test deterministic release evidence files

**Files:**
- Create: `backend/tests/test_release_metadata.py`
- Create: `scripts/write_release_metadata.py`

- [x] **Step 1: Write the failing metadata-script contract test**

Create `backend/tests/test_release_metadata.py` with a subprocess test that invokes the missing script and asserts exactly these generated values:

```python
completed = subprocess.run(
    [
        sys.executable,
        str(SCRIPT),
        "--output-dir", str(output_dir),
        "--image", "ghcr.io/mcocdaa/meetflow",
        "--release-tag", "v0.2.2",
        "--commit", "abc123",
        "--digest", "sha256:" + "a" * 64,
        "--platforms", "linux/amd64,linux/arm64",
        "--tags", "ghcr.io/mcocdaa/meetflow:v0.2.2\nghcr.io/mcocdaa/meetflow:0.2.2",
    ],
    check=True,
)
metadata = json.loads((output_dir / "release-metadata.json").read_text())
assert metadata["immutable_image"] == "ghcr.io/mcocdaa/meetflow@sha256:" + "a" * 64
assert metadata["platforms"] == ["linux/amd64", "linux/arm64"]
assert "docker pull ghcr.io/mcocdaa/meetflow@sha256:" in (output_dir / "release-notes.md").read_text()
```

- [x] **Step 2: Run the focused test and verify RED**

Run:

```bash
.venv/bin/python -m pytest -q backend/tests/test_release_metadata.py
```

Expected: FAIL because `scripts/write_release_metadata.py` does not exist.

- [x] **Step 3: Implement the metadata writer with the Python standard library**

Create `scripts/write_release_metadata.py`. Parse required `--output-dir`, `--image`, `--release-tag`, `--commit`, `--digest`, `--platforms`, and `--tags` arguments. Split platforms on commas and tags on newlines, dropping empty items. Write `<output-dir>/release-metadata.json` as:

```python
{
    "schema_version": 1,
    "release_tag": args.release_tag,
    "source_commit": args.commit,
    "image": args.image,
    "digest": args.digest,
    "immutable_image": f"{args.image}@{args.digest}",
    "platforms": platforms,
    "tags": tags,
    "attestations": ["provenance", "sbom"],
}
```

Write `release-notes.md` that lists the release tag, source commit, immutable image reference, platforms, all published tags, and an exact `docker pull <image>@<digest>` command. Use `json.dumps(..., indent=2, sort_keys=True) + "\\n"` and UTF-8 so reruns are deterministic.

- [x] **Step 4: Run the focused test and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest -q backend/tests/test_release_metadata.py
```

Expected: PASS with one test.

### Task 2: Wire the pushed digest into workflow artifacts and GitHub Releases

**Files:**
- Modify: `backend/tests/test_release_workflow.py`
- Modify: `.github/workflows/release.yml`

- [x] **Step 1: Write failing workflow-contract assertions**

Extend `test_release_workflow_publishes_the_public_multiarch_tag_contract()` with the fragments below:

```python
"contents: write",
"- id: build",
"steps.build.outputs.digest",
"scripts/write_release_metadata.py",
"docker buildx imagetools inspect",
"uses: actions/upload-artifact@v4",
"name: meetflow-release-\${{ github.ref_name }}",
"if-no-files-found: error",
"gh release create",
"gh release edit",
"gh release upload",
"--prerelease",
```

Keep the existing assertions for tag validation, tag policy, Buildx platforms, provenance, and SBOM.

- [x] **Step 2: Run the workflow-contract test and verify RED**

Run:

```bash
.venv/bin/python -m pytest -q backend/tests/test_release_workflow.py
```

Expected: FAIL and list the missing evidence/release fragments.

- [x] **Step 3: Add post-push evidence and idempotent release publication**

In `.github/workflows/release.yml`:

1. Change `permissions.contents` to `write`; retain `packages: write`.
2. Give `docker/build-push-action@v7` the ID `build`.
3. After it succeeds, run the metadata script with `\${{ steps.build.outputs.digest }}` and `\${{ steps.metadata.outputs.tags }}`; write into `release-artifacts/`.
4. Run `docker buildx imagetools inspect "\${IMAGE_NAME}@\${{ steps.build.outputs.digest }}" > release-artifacts/image-manifest.txt` so the artifact is a registry read-back of the pushed multi-platform manifest.
5. Upload `release-artifacts/` with `actions/upload-artifact@v4`, name it `meetflow-release-\${{ github.ref_name }}`, set `if-no-files-found: error`, and retain it for 90 days.
6. Create a GitHub Release with `gh release create` if it does not already exist; otherwise use `gh release edit`. Both paths set the tag title, target SHA, and `release-artifacts/release-notes.md`. For tags containing `-`, append `--prerelease`; stable tags omit that flag. Finally use `gh release upload ... --clobber` to attach `release-metadata.json` and `image-manifest.txt` on a rerun without duplicate-asset failure.

Set `GH_TOKEN: \${{ github.token }}` only on the GitHub Release step. Do not add `docker save`, server credentials, SSH, workflow dispatch, or deployment steps.

- [x] **Step 4: Run focused workflow-contract and YAML checks**

Run:

```bash
.venv/bin/python -m pytest -q backend/tests/test_release_workflow.py
.venv/bin/python -c "from pathlib import Path; import yaml; yaml.safe_load(Path('.github/workflows/release.yml').read_text())"
```

Expected: the contract test passes and YAML parses without error.

### Task 3: Document artifact use without changing deployment ownership

**Files:**
- Modify: `docs/release.md`

- [x] **Step 1: Update the maintainer release guide**

In the `发布镜像` section, state that a successful workflow publishes a GitHub Release and an Actions artifact named `meetflow-release-<tag>`. Document the two files:

```text
release-metadata.json  exact image digest, source commit, platforms, tags, and attestation types
image-manifest.txt     registry read-back of the pushed Buildx multi-platform manifest
```

State that `provenance` and `SBOM` stay attached to the OCI image, while the release files make its immutable digest easy to retain. Show `docker pull ghcr.io/mcocdaa/meetflow@sha256:<digest>` as the immutable pull form. Keep the existing version-tag update/rollback instructions and state that GitHub Actions does not update the server.

- [x] **Step 2: Verify document links and diff hygiene**

Run:

```bash
git diff --check
rg -n '\\]\\([^)]+' docs/release.md
```

Expected: `git diff --check` is silent and the existing local Markdown links remain valid.

### Task 4: Full verification and focused commit

**Files:**
- Modify: `.github/workflows/release.yml`
- Create: `scripts/write_release_metadata.py`
- Create: `backend/tests/test_release_metadata.py`
- Modify: `backend/tests/test_release_workflow.py`
- Modify: `docs/release.md`
- Create: `docs/superpowers/plans/2026-08-03-release-evidence-publication.md`

- [x] **Step 1: Run all release-scope checks**

Run:

```bash
.venv/bin/python -m pytest -q backend/tests/test_release_metadata.py backend/tests/test_release_workflow.py
.venv/bin/python -c "from pathlib import Path; import yaml; yaml.safe_load(Path('.github/workflows/ci.yml').read_text()); yaml.safe_load(Path('.github/workflows/release.yml').read_text())"
git diff --check
```

Expected: all tests pass, both workflow files parse, and no diff whitespace errors are reported.

- [x] **Step 2: Review the exact diff and commit only task files**

Run:

```bash
git diff -- .github/workflows/release.yml scripts/write_release_metadata.py backend/tests/test_release_metadata.py backend/tests/test_release_workflow.py docs/release.md docs/superpowers/plans/2026-08-03-release-evidence-publication.md
git status --short
git add -- .github/workflows/release.yml scripts/write_release_metadata.py backend/tests/test_release_metadata.py backend/tests/test_release_workflow.py docs/release.md docs/superpowers/plans/2026-08-03-release-evidence-publication.md
git commit -m "ci: publish release image evidence"
```

Expected: the commit includes only the six listed implementation/documentation files and the plan.
