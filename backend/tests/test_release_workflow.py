from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RELEASE_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/release.yml"


def test_release_workflow_publishes_the_public_multiarch_tag_contract():
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    required_fragments = (
        'tags:\n      - "v*"',
        "uses: ./.github/workflows/test-backend.yml",
        "uses: ./.github/workflows/test-frontend.yml",
        "Tag must be valid SemVer prefixed with v",
        "Verify tag matches package version",
        "must match v$package_version from pyproject.toml",
        "git merge-base --is-ancestor",
        "IMAGE_NAME: ghcr.io/mcocdaa/meetflow",
        "packages: write",
        "uses: docker/setup-qemu-action@v4",
        "platforms: linux/amd64,linux/arm64",
        "provenance: mode=max",
        "sbom: true",
        "type=raw,value=latest,enable=${{ !contains(github.ref_name, '-') }}",
        "steps.build.outputs.digest",
        "gh release create",
        "--prerelease",
    )
    missing = [fragment for fragment in required_fragments if fragment not in workflow]
    assert not missing, f"release workflow is missing: {missing}"


def test_release_notes_include_the_immutable_image_pull_command():
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert "docker pull ${IMAGE_NAME}@${{ steps.build.outputs.digest }}" in workflow
