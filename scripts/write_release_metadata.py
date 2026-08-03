#!/usr/bin/env python3
"""Write deterministic release evidence after a container manifest is pushed."""

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--platforms", required=True)
    parser.add_argument("--tags", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    platforms = [platform.strip() for platform in args.platforms.split(",") if platform.strip()]
    tags = [tag.strip() for tag in args.tags.splitlines() if tag.strip()]
    immutable_image = f"{args.image}@{args.digest}"
    metadata = {
        "attestations": ["provenance", "sbom"],
        "digest": args.digest,
        "image": args.image,
        "immutable_image": immutable_image,
        "platforms": platforms,
        "release_tag": args.release_tag,
        "schema_version": 1,
        "source_commit": args.commit,
        "tags": tags,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "release-metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    lines = [
        f"# MeetFlow {args.release_tag}",
        "",
        f"- Source commit: `{args.commit}`",
        f"- Immutable image: `{immutable_image}`",
        f"- Platforms: {', '.join(f'`{platform}`' for platform in platforms)}",
        "- OCI attestations: `provenance`, `sbom`",
        "",
        "## Published tags",
        "",
        *(f"- `{tag}`" for tag in tags),
        "",
        "## Immutable pull",
        "",
        f"```bash\ndocker pull {immutable_image}\n```",
        "",
    ]
    (args.output_dir / "release-notes.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
