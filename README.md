# Bill X-Ray

**Did you read the bill? We did.**

Bill X-Ray is a source-first legislative intelligence museum. It turns major U.S. laws into plain-English public reports while preserving an exact evidence trail back to official statutory text.

The public launch contains four curated exhibits:

- Affordable Care Act
- Inflation Reduction Act
- Tax Cuts and Jobs Act
- One Big Beautiful Bill Act

Each exhibit passed the same release pipeline: structural segmentation, citation anchoring, plain-English translation, money and authority extraction, Barrel Scan, topic review, Left/Right interpretation, Investigative Skeptic, Neutral Referee, five-panel synthesis, external evidence, consequence context, political-bias red team, hallucination/citation audit, and hostile-context challenge.

## Trust rules

- No citation, no claim.
- Interpretation is never presented as statutory fact.
- The same rubric is applied regardless of party.
- A failed release gate holds the report rather than publishing it.
- The statutory source remains the final authority.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app:app --reload
```

Open `http://127.0.0.1:8000`.

Run tests with:

```bash
python -m pytest -q
```

## Public deployment mode

The Render blueprint sets `BILL_XRAY_PUBLIC_MUSEUM=1`. In this mode the four verified exhibits and evidence drawers remain public, while live bill search and build-mutation endpoints are disabled. This keeps the deployed site a curated read-only museum rather than exposing the development pipeline to anonymous internet traffic.

## Deploy on Render

This repository includes `render.yaml` and a `Procfile`. On Render, create a new Blueprint/Web Service from the GitHub repository. The service installs `requirements.txt`, starts Uvicorn on Render's assigned `$PORT`, and uses `/api/health` for health checks.

## Development history

The repository was developed through a long sequence of adversarial passes focused on provenance, citation integrity, political neutrality, fail-closed release behavior, readability, and deployment hardening. Historical pass notes can be retained separately from the public deployment package; the launch repository is intentionally kept focused on the working product and its verification artifacts.
