# Public Container Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Publish public amd64/arm64 MeetFlow images from validated Git tags and let operators start the image with one direct docker run command that persists data in ./data/.

**Architecture:** The Dockerfile owns its invariant /app runtime paths. A built-image smoke script proves the same bind-mount and command-line environment contract that README documents, and CI executes that script after loading the image locally. The existing tag-only workflow builds a QEMU/Buildx multi-platform manifest to the public GHCR package.

**Tech Stack:** Docker/Buildx, GitHub Actions, GHCR, Bash, pytest, FastAPI, Vue/Vite

---

## File structure

~~~text
Dockerfile                                    direct-run runtime paths
scripts/ci-container-smoke.sh                 built-image contract test
backend/tests/test_release_workflow.py        workflow source contract
.github/workflows/ci.yml                      load and smoke the CI image
.github/workflows/release.yml                 publish the public manifest
.env.example                                  existing advanced-settings template
README.md                                     server deployment guide
~~~

### Task 1: Test and implement the direct-run image contract

**Files:**
- Create: scripts/ci-container-smoke.sh
- Modify: Dockerfile:11-13
- Modify: .github/workflows/ci.yml:46-58

- [ ] **Step 1: Write the failing built-image smoke test**

Create scripts/ci-container-smoke.sh and make it executable:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

image="${1:?usage: scripts/ci-container-smoke.sh IMAGE}"
work_dir="$(mktemp -d)"
container_name="meetflow-ci-${RANDOM}${RANDOM}"

cleanup() {
  docker rm -f "$container_name" >/dev/null 2>&1 || true
  rm -rf "$work_dir"
}
trap cleanup EXIT

mkdir -p "$work_dir/data"
image_env="$(docker image inspect "$image" --format '{{range .Config.Env}}{{println .}}{{end}}')"
for expected in \
  'DATABASE_URL=sqlite:////app/data/meetflow.db' \
  'DATA_DIR=/app/data' \
  'PLUGINS_DIR=/app/plugins' \
  'FRONTEND_DIST=/app/frontend-dist'; do
  grep -Fxq "$expected" <<<"$image_env" || {
    echo "Missing runtime image default: $expected" >&2
    exit 1
  }
done

docker run -d --name "$container_name" --init --read-only --tmpfs /tmp:size=64m \
  --security-opt no-new-privileges:true --restart no \
  -p 127.0.0.1::8000 \
  -v "$work_dir/data:/app/data" \
  -e APP_ENV=production \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=container-smoke-admin-password \
  -e APP_SECRET_KEY=container-smoke-persistent-secret-key-2026 \
  -e ALLOW_REGISTRATION=false \
  -e SECURE_COOKIES=true \
  -e TRUSTED_ORIGINS=https://meetflow.test \
  "$image" >/dev/null

for _ in $(seq 1 45); do
  health="$(docker inspect --format '{{.State.Health.Status}}' "$container_name")"
  if [[ "$health" == "healthy" ]]; then
    docker exec "$container_name" python -c "import urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2); assert response.status == 200"
    test -f "$work_dir/data/meetflow.db"
    exit 0
  fi
  if [[ "$health" == "unhealthy" ]]; then
    docker logs "$container_name" >&2
    exit 1
  fi
  sleep 1
done

docker logs "$container_name" >&2
echo "Timed out waiting for MeetFlow health check" >&2
exit 1
~~~

- [ ] **Step 2: Run RED against the current Dockerfile**

Run:

~~~bash
docker build -t meetflow:direct-run-test .
bash scripts/ci-container-smoke.sh meetflow:direct-run-test
~~~

Expected: the script exits non-zero with Missing runtime image default: DATABASE_URL=sqlite:////app/data/meetflow.db, because the current image declares only FRONTEND_DIST.

- [ ] **Step 3: Add only the image-owned path defaults**

Replace Dockerfile's ENV instruction with:

~~~dockerfile
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////app/data/meetflow.db \
    DATA_DIR=/app/data \
    PLUGINS_DIR=/app/plugins \
    FRONTEND_DIST=/app/frontend-dist
~~~

Do not add secrets, a named volume, another process, or an entrypoint. docker run -e values remain higher-priority overrides.

- [ ] **Step 4: Rebuild and run GREEN**

Run:

~~~bash
docker build -t meetflow:direct-run-test .
bash scripts/ci-container-smoke.sh meetflow:direct-run-test
~~~

Expected: exit code 0 after the container is healthy, /api/health returns 200, and the bind-mounted host directory contains meetflow.db.

- [ ] **Step 5: Use the same test in CI**

Change the existing build-push step in .github/workflows/ci.yml to load the locally built image, then add the smoke step:

~~~yaml
      - uses: docker/build-push-action@v7
        with:
          context: .
          push: false
          load: true
          tags: meetflow:ci
          cache-from: type=gha
          cache-to: type=gha,mode=max
      - name: Smoke direct Docker run
        run: bash scripts/ci-container-smoke.sh meetflow:ci
~~~

- [ ] **Step 6: Verify and commit**

Run:

~~~bash
bash -n scripts/ci-container-smoke.sh
bash scripts/ci-container-smoke.sh meetflow:direct-run-test
git add Dockerfile scripts/ci-container-smoke.sh .github/workflows/ci.yml
git commit -m "build: verify direct container startup"
~~~

Expected: both checks exit 0 before the commit.

### Task 2: Test and implement public multi-architecture tag publication

**Files:**
- Create: backend/tests/test_release_workflow.py
- Modify: .github/workflows/release.yml:47-69

- [ ] **Step 1: Write the failing release-workflow contract test**

Create backend/tests/test_release_workflow.py:

~~~python
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
~~~

- [ ] **Step 2: Run RED**

Run:

~~~bash
python -m pytest backend/tests/test_release_workflow.py -q
~~~

Expected: FAIL and list the missing QEMU, exact Git tag, latest flavor, platform, provenance, or SBOM fragments.

- [ ] **Step 3: Publish one manifest with deterministic tags**

Keep the current validated v* trigger, test gates, GHCR login, permissions, and cache. Replace the metadata/build tail of .github/workflows/release.yml with:

~~~yaml
      - uses: docker/setup-qemu-action@v4
      - uses: docker/setup-buildx-action@v4
      - uses: docker/login-action@v4
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: metadata
        uses: docker/metadata-action@v6
        with:
          images: ${{ env.IMAGE_NAME }}
          flavor: |
            latest=false
          tags: |
            type=ref,event=tag
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha
            type=raw,value=latest,enable=${{ !contains(github.ref_name, '-') }}
      - uses: docker/build-push-action@v7
        with:
          context: .
          push: true
          platforms: linux/amd64,linux/arm64
          tags: ${{ steps.metadata.outputs.tags }}
          labels: ${{ steps.metadata.outputs.labels }}
          provenance: mode=max
          sbom: true
          cache-from: type=gha
          cache-to: type=gha,mode=max
~~~

latest=false prevents metadata-action from adding latest to a pre-release. The raw stable-only tag is its sole owner; type=ref preserves v1.2.3, while SemVer produces 1.2.3 and 1.2.

- [ ] **Step 4: Verify GREEN and YAML syntax**

Run:

~~~bash
python -m pytest backend/tests/test_release_workflow.py -q
python -c "from pathlib import Path; import yaml; yaml.safe_load(Path('.github/workflows/ci.yml').read_text()); yaml.safe_load(Path('.github/workflows/release.yml').read_text())"
~~~

Expected: pytest and YAML parsing both exit 0. This is a local source-contract check, not evidence that GHCR has received a manifest.

- [ ] **Step 5: Commit**

~~~bash
git add backend/tests/test_release_workflow.py .github/workflows/release.yml
git commit -m "ci: publish public multiarch images"
~~~

### Task 3: Document direct server operation and include the approved env template

**Files:**
- Modify: README.md:34-172
- Modify: .env.example:1-18 (existing user change; stage it without replacing its values)

- [ ] **Step 1: Preserve the approved .env.example content**

Run:

~~~bash
git diff -- .env.example
~~~

Expected: only the user-approved local password, local secret, and localhost/127.0.0.1 trusted-origin refinements are present. Do not create another template or rename this file.

- [ ] **Step 2: Make public docker run the primary server path**

Rewrite README's Docker/GHCR sections so the first server command is:

~~~bash
docker run -d --name meetflow --init --read-only --tmpfs /tmp:size=64m \
  --security-opt no-new-privileges:true --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -v "$PWD/data:/app/data" \
  -e APP_ENV=production \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD='替换为至少12位的强密码' \
  -e APP_SECRET_KEY='替换为至少32字符且长期保存的随机密钥' \
  -e ALLOW_REGISTRATION=false \
  -e SECURE_COOKIES=true \
  -e TRUSTED_ORIGINS=https://meetflow.example.com \
  ghcr.io/mcocdaa/meetflow:latest
~~~

State directly below it that the image is public and needs no GHCR login; $PWD/data persists data as ./data/; inline -e values remain visible to shell history and Docker administrators; a TLS proxy is required for this loopback-only production setup; APP_SECRET_KEY must be reused after updates/restores; and the bootstrap password never resets an existing administrator.

- [ ] **Step 3: Keep the env file advanced and document maintenance**

Add the optional, secondary route:

~~~bash
cp .env.example .env
# Edit .env for production before use.
docker run -d --name meetflow --init --read-only --tmpfs /tmp:size=64m \
  --security-opt no-new-privileges:true --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -v "$PWD/data:/app/data" \
  --env-file ./.env \
  ghcr.io/mcocdaa/meetflow:latest
~~~

Document docker ps --filter name=meetflow, curl http://127.0.0.1:8000/api/health, the direct backup command below, exact vX.Y.Z rollback after docker pull, and docker restart meetflow after plugin configuration changes:

~~~bash
docker exec meetflow python /app/scripts/backup.py \
  --database /app/data/meetflow.db \
  --uploads /app/data/uploads \
  --output /app/data/backups
~~~

Explain that custom plugins are optional and use -v "$PWD/plugins:/app/plugins:ro"; this replaces the image's whole plugin directory and the host tree must supply plugins.yaml plus all required plugins. Retain Compose only as the source-checkout/advanced operation path.

- [ ] **Step 4: Update tag examples and validate prose**

List stable tags v1.4.2, 1.4.2, 1.4, latest, and sha-<short-commit>. State that v1.4.2-rc.1 never moves latest or 1.4. Then run:

~~~bash
rg -n 'meetflow-data|meetflow.env|私有镜像需要|docker compose pull meetflow' README.md
rg -n 'ghcr.io/mcocdaa/meetflow|$PWD/data:/app/data|--env-file ./\.env|linux/amd64,linux/arm64' README.md .github/workflows/release.yml
git diff --check
~~~

Expected: the first search has no stale primary-deployment guidance, the second finds the current contract, and git diff --check exits 0.

- [ ] **Step 5: Commit only the intended docs and configuration**

~~~bash
git add README.md .env.example
git commit -m "docs: document direct container deployment"
~~~

Before committing, inspect git status --short and ensure only README.md and .env.example are staged. Do not amend the previously committed design document.

### Task 4: Run the release-readiness gate and report its boundary

**Files:**
- Verify: Dockerfile
- Verify: scripts/ci-container-smoke.sh
- Verify: backend/tests/test_release_workflow.py
- Verify: .github/workflows/ci.yml
- Verify: .github/workflows/release.yml
- Verify: README.md
- Verify: .env.example

- [ ] **Step 1: Run all code and frontend checks**

~~~bash
python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
~~~

Expected: all test suites pass and Vite produces the production bundle. npm must run with the frontend prefix because package.json is not at repository root.

- [ ] **Step 2: Build and smoke the final image**

~~~bash
docker build -t meetflow:release-verify .
bash scripts/ci-container-smoke.sh meetflow:release-verify
~~~

Expected: the build completes and the direct bind-mount smoke test exits 0. If external dependency download is blocked, report that environment boundary instead of claiming an image was verified.

- [ ] **Step 3: Recheck config and repository state**

~~~bash
python -c "from pathlib import Path; import yaml; yaml.safe_load(Path('.github/workflows/ci.yml').read_text()); yaml.safe_load(Path('.github/workflows/release.yml').read_text())"
bash -n scripts/ci-container-smoke.sh
git diff --check HEAD~3..HEAD
git status --short --branch
~~~

Expected: YAML, Bash, and whitespace checks pass. The three implementation commits are the direct-run contract, public multiarch workflow, and documentation/template change.

- [ ] **Step 4: Hand off without fabricating a release**

Report fresh test/build evidence, commit hashes, and the exact direct server command. State that a public GHCR manifest is created only by a future reviewed command:

~~~bash
git tag vX.Y.Z
git push origin vX.Y.Z
~~~

Do not create, push, or claim an image tag during this implementation.
