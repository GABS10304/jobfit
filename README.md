# Job Fit System

[![CI](https://github.com/GABS10304/job-fit-system/actions/workflows/ci.yml/badge.svg)](https://github.com/GABS10304/job-fit-system/actions/workflows/ci.yml)

Lokales Job-Matching- und Bewerbungs-System (inspiriert von [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search), aber eigenständig und schlanker).

**V2 review-ready · Tests grün** — siehe [`docs/V2_RELEASE.md`](docs/V2_RELEASE.md).  
V1-Abschluss: [`docs/V1_FREEZE.md`](docs/V1_FREEZE.md). Nach Team-Review: Freeze auf V2.

**Phase 1 / V2:** Master-CV + Role-Fit-Profil + Fit-Check-API (`POST /fit-check`).  
Sourcing/Scraping ist inzwischen Teil des Systems (`backend/sourcing/`, `scripts/fetch_jobs_*.py`) — was weiterhin bewusst **nicht** passiert: Auto-Apply. Kein Skript füllt Formulare aus oder klickt "Absenden" — das bleibt manuell (`domain/constraints.yaml`: `auto_apply_enabled: false`).

Noch nie ein Terminal benutzt oder unsicher mit Python/venv? → **[SETUP.md](SETUP.md)** — Schritt-für-Schritt-Anleitung für absolute Anfänger, keine Vorkenntnisse nötig.

## Voraussetzungen

- Python 3.11+ (empfohlen)
- Ein Terminal (macOS/Linux/Windows) — egal ob in [Claude Code](https://claude.com/claude-code), Cursor oder einem eigenständigen Shell-Fenster
- Optional: [Claude Code](https://claude.com/claude-code) für den `cv-tailor`-Skill (CV-/Anschreiben-Tailoring) und die anderen Claude-Command-Workflows dieses Repos

## Lokal starten

Im Repo-Root (`job-fit-system`):

```bash
# 1) Virtuelle Umgebung
python3 -m venv .venv
source .venv/bin/activate

# 2) Abhängigkeiten
pip install -r requirements.txt
playwright install chromium  # einmalig, für Board-Scraping-Fallback + styled CV/PDF-Rendering

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

## Zusammenarbeit (Multi-User)

Privates Repo, zwei Personen. Damit sich niemand gegenseitig überschreibt:

- **Branches statt direkt auf `main`:** neue Arbeit auf einem Feature-Branch (`git checkout -b feature/xyz`), dann PR + Merge. Für triviale Änderungen (Typo, ein Kommentar) ist direktes Pushen auf `main` ok.
- **Vor jeder Session:** `git pull origin main`, um nicht auf altem Stand zu arbeiten.
- **Vor jedem Push:** `pytest -q` muss grün sein.

**Wichtig:** `domain/*.yaml` (`cv_master.yaml`, `constraints.yaml`, `role_fit_profile.yaml`) ist das persönliche Profil von Gabriel (fest verdrahteter `gabriel`-User) — **nicht anfassen**, wenn du nicht Gabriel bist. Eigenes Profil stattdessen über `/onboarding` anlegen: CV hochladen, es entsteht ein separates Profil unter `profiles/<deine-user-id>/`, komplett getrennt von `domain/`. Gehalts-Untergrenze, Ausschluss-Firmen und die Impact-Notiz für Gabriels eigenes Setup gehören auf `/settings` (schreibt gezielt in `domain/constraints.yaml`, ohne die übrigen Constraints anzufassen).

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

1. **Phase 1** – Fit-Check ✅  
2. **Phase 2** – CV-/Anschreiben-Generator ✅  
3. **Phase 3** – Job-Sourcing (APIs / Scraper) ✅  
4. **Phase 4** – Assisted Apply + Tracking ← du bist hier  
5. **Phase 5** – optional Auto-Apply mit Regeln & Rate-Limits (noch nicht begonnen, bewusst zurückgestellt)

## Forken und selbst nutzen

Dieses Repo ist so gedacht, dass du es forkst und **auf deiner eigenen Maschine mit deinem eigenen Claude-/API-Zugang** betreibst — es gibt keinen Server, den irgendjemand für dich hostet, keine gemeinsame Datenbank, keine Anmeldung. Deine Daten bleiben bei dir; niemand sonst verarbeitet sie.

> [!IMPORTANT]
> Ein Fork eines öffentlichen Repos ist auf GitHub standardmäßig selbst **öffentlich** — private Forks gehen nicht. `/profiles/` ist zwar gitignored, aber bevor du `/onboarding` durchläufst, lohnt sich trotzdem ein zweiter Gedanke an dieser Stelle: Willst du das lieber komplett unter eigener Kontrolle laufen lassen, ist ein **privates Repository mit diesem Repo als `upstream`** in zwei Minuten erledigt:
>
> ```bash
> git clone <dein-neues-privates-repo-url>
> cd job-fit-system
> git remote add upstream https://github.com/GABS10304/job-fit-system
> # Updates später: git fetch upstream && git merge upstream/main
> ```

Sicherheitsmodell und was das System bewusst nicht automatisiert: [`SECURITY.md`](SECURITY.md). Lizenz: [`LICENSE`](LICENSE) (MIT).
