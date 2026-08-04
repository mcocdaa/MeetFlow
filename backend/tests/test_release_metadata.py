import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts/write_release_metadata.py"


def test_release_metadata_writer_records_immutable_image_and_pull_command(tmp_path):
    output_dir = tmp_path / "release-artifacts"
    digest = "sha256:" + "a" * 64

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output-dir",
            str(output_dir),
            "--image",
            "ghcr.io/mcocdaa/meetflow",
            "--release-tag",
            "v0.2.2",
            "--commit",
            "abc123",
            "--digest",
            digest,
            "--platforms",
            "linux/amd64,linux/arm64",
            "--tags",
            "ghcr.io/mcocdaa/meetflow:v0.2.2\nghcr.io/mcocdaa/meetflow:0.2.2",
        ],
        check=True,
    )

    metadata = json.loads((output_dir / "release-metadata.json").read_text())
    notes = (output_dir / "release-notes.md").read_text()

    assert metadata == {
        "attestations": ["provenance", "sbom"],
        "digest": digest,
        "image": "ghcr.io/mcocdaa/meetflow",
        "immutable_image": f"ghcr.io/mcocdaa/meetflow@{digest}",
        "platforms": ["linux/amd64", "linux/arm64"],
        "release_tag": "v0.2.2",
        "schema_version": 1,
        "source_commit": "abc123",
        "tags": [
            "ghcr.io/mcocdaa/meetflow:v0.2.2",
            "ghcr.io/mcocdaa/meetflow:0.2.2",
        ],
    }
    assert f"docker pull ghcr.io/mcocdaa/meetflow@{digest}" in notes
