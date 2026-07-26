from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RELEASE_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/release.yml"


def test_release_workflow_publishes_the_public_multiarch_tag_contract():
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    required_fragments = (
        "IMAGE_NAME: ghcr.io/mcocdaa/meetflow",
        "packages: write",
        "uses: docker/setup-qemu-action@v4",
        "uses: docker/setup-buildx-action@v4",
        "type=ref,event=tag",
        "type=semver,pattern={{version}}",
        "type=semver,pattern={{major}}.{{minor}}",
        "type=sha",
        "latest=false",
        "type=raw,value=latest,enable=${{ !contains(github.ref_name, '-') }}",
        "platforms: linux/amd64,linux/arm64",
        "provenance: mode=max",
        "sbom: true",
    )
    missing = [fragment for fragment in required_fragments if fragment not in workflow]
    assert not missing, f"release workflow is missing: {missing}"
