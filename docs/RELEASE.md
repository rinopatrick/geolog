# Release process

1. Update the version in `backend/version.py` and `package.json`.
2. Move the `[Unreleased]` entries in `CHANGELOG.md` under a dated
   `## [x.y.z] - YYYY-MM-DD` section and leave a fresh empty `[Unreleased]`.
3. Run the local gates:

   ```bash
   python -m pytest tests/ -q
   bash scripts/coverage_gate.sh
   python -m alembic check
   for f in frontend/js/*.js scripts/*.js; do node --check "$f"; done
   ```

4. Open a release PR titled `chore(release): vX.Y.Z`, wait for CI and merge it.
5. Tag the merge commit and publish the tag:

   ```bash
   git switch main
   git pull --ff-only
   git tag -a vX.Y.Z -m "GeoLog vX.Y.Z"
   git push origin vX.Y.Z
   ```

6. `.github/workflows/release.yml` builds and pushes
   `ghcr.io/rinopatrick/geolog:vX.Y.Z` and `:latest`, signs the image with
   cosign keyless signing, and creates the GitHub release from generated notes.
7. Verify the release:
   - `GET /api/version` reports the tag.
   - The Actions release run is green.
   - `cosign verify ghcr.io/rinopatrick/geolog:vX.Y.Z` succeeds.
   - `docker run --rm ghcr.io/rinopatrick/geolog:vX.Y.Z` starts and `/api/health`
     returns 200.

`tests/test_version.py` fails when a release tag and `backend/version.py`
disagree.
