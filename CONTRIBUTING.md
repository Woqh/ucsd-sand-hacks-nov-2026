# Working on Sitwise

## Source boundaries

- `web/`: dashboard, camera UI and phone notification receiver.
- `api/`: Flask routes, data stores, coaching and notification delivery.
- `bridge/`: adapter between the vendored posture model and Sitwise readings.
- `posture_pipeline-main/`: vendored model, weights and its own documentation.
- `ios/`: native SwiftUI client, built with Xcode on macOS.
- `scripts/`: local development, database setup and model entry points.
- `docs/`: task guides and API reference; use its [index](docs/README.md).

Keep model integration in `bridge/` and `scripts/posture_model.py`. Keep generated output out of source
control: virtual environments, `node_modules`, `public/`, local databases, camera snapshots and secrets
are ignored. Copy `.env.example` for private local configuration; never commit API keys or device tokens.

## Checks

From the repository root, with the API virtual environment activated:

```powershell
python -m pytest api bridge -q
python scripts/check_codemap.py
npm --prefix web test
npm --prefix web run build
git diff --check
```

Use Node 20.19+ or 22.12+. PostgreSQL tests are skipped unless `TEST_DATABASE_URL` points at a disposable
test database; they rebuild its tables. Automated push tests use a fake provider. Confirm delivery and
vibration on a physical iPhone using the [phone guide](docs/iphone-alerts.md).

Update `codemap.md` when adding, moving or deleting files, and update the matching setup guide when
changing a user flow. The model has a separate Python 3.12 environment; install its runtime with
`python -m pip install -r scripts/requirements-model.txt` in that environment.
