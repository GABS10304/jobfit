# Job Fit System

Lokales Job-Matching- und Bewerbungs-System (inspiriert von [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search), aber eigenständig und schlanker).

**V2 review-ready · Tests grün** — siehe [`docs/V2_RELEASE.md`](docs/V2_RELEASE.md).  
V1-Abschluss: [`docs/V1_FREEZE.md`](docs/V1_FREEZE.md). Nach Team-Review: Freeze auf V2.

**Phase 1 / V2:** Master-CV + Role-Fit-Profil + Fit-Check-API (`POST /fit-check`).  
Kein Scraping, kein Auto-Apply, keine Browser-Automation.

## Voraussetzungen (macOS / Cursor)

- Python 3.11+ (empfohlen)
- Terminal in Cursor (Integrated Terminal)

## Lokal starten

Im Repo-Root (`job-fit-system`):

```bash
# 1) Virtuelle Umgebung
python3 -m venv .venv
source .venv/bin/activate

# 2) Abhängigkeiten
pip install -r requirements.txt

# 3) API starten (aus dem Repo-Root!)
uvicorn backend.main:app --reload --port 8000
```

Dann im Browser oder per curl:

- Health: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- API-Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

Beispiel Fit-Check:

```bash
curl -s -X POST http://127.0.0.1:8000/fit-check \
  -H 'Content-Type: application/json' \
  -d '{
    "job_description": "Remote AI Product Manager for B2B SaaS with product ownership, product discovery, SQL and Python.",
    "role_ids": ["ai_product_manager", "technical_product_manager"]
  }'
```

## Source of Truth

| Datei | Zweck |
|-------|--------|
| [`domain/cv_master.yaml`](domain/cv_master.yaml) | Master-CV (kanonisch, editierbar) |
| [`domain/cv_master.json`](domain/cv_master.json) | Machine-readable Mirror – muss mit YAML identisch sein |
| [`domain/Master-CV-structured.md`](domain/Master-CV-structured.md) | Menschenlesbare Rohdaten (Sync-Quelle) |
| [`domain/role_fit_profile.yaml`](domain/role_fit_profile.yaml) | Zielrollen + Kernsignale |
| [`domain/constraints.yaml`](domain/constraints.yaml) | Hard/Soft Constraints + Application Rules |

**Nichts erfinden:** fehlende Werte (z. B. Gehalt) bleiben `null` / TODO.  
Nach Domain-Änderungen Server neu starten (`--reload` reicht; Cache leert sich beim Restart).

## Tests

```bash
source .venv/bin/activate
pytest -q
```

## Repo-Struktur

```
domain/           # Source of Truth (YAML)
backend/          # FastAPI + Fit-Engine
  sourcing/       # Phase 3 (Platzhalter)
  generation/     # Phase 2 (Platzhalter)
  tracking/       # Phase 4+ (Platzhalter)
docs/             # Architektur & Fit-Notizen
tests/            # Smoke-Tests
```

Mehr Kontext: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Roadmap (kurz)

1. **Phase 1** – Fit-Check ← du bist hier  
2. **Phase 2** – CV-/Anschreiben-Generator  
3. **Phase 3** – Job-Sourcing (APIs / Scraper)  
4. **Phase 4** – Assisted Apply + Tracking  
5. **Phase 5** – optional Auto-Apply mit Regeln & Rate-Limits  
