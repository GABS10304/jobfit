# Architecture (v0.1 / V3)

## Überblick

Lokales, dateibasiertes Job-Matching. Phase 1: Master-CV, Role-Fit-Profil, Fit-Check-API.

**PM-Sicht auf Pipeline, Flags und Entscheidungslogik:** → [`docs/FIT_LOGIC_NOTES.md`](FIT_LOGIC_NOTES.md)  
**Freeze:** → [`docs/V3_FREEZE.md`](V3_FREEZE.md)  
**Multi-User / Completeness-%:** → [`docs/USER_ONBOARDING.md`](USER_ONBOARDING.md)

```
Job Description (Text)
        │
        ▼
 Constraints Engine  ◄── domain/constraints.yaml
        │  Hard Gate fail → status_flag=no_go, leere results
        │  Ownership unclear → verify_product_ownership (Scoring weiter)
        │  Präsenz 2–3 Tage → Penalty, Ausnahme nach Score (sichtbar)
        ▼
   Fit Engine  ◄── domain/role_fit_profile.yaml
        │  Score → Ranking → results / excluded_roles
        │  + presence_policy (V3, immer)
        ▼
   POST /fit-check Response
```

**Source of Truth:** `cv_master.yaml` (+ JSON-Mirror), `role_fit_profile.yaml`, `constraints.yaml`.  
Master-CV steuert den Fit-Check noch nicht direkt (Phase 2: CV-Varianten).

## Zusammenspiel der Bausteine

| Baustein | Rolle |
|----------|--------|
| `cv_master.yaml` | Strukturierte Karriere-Daten (Employments, Projekte, Skills, Tools, Zertifikate) |
| `role_fit_profile.yaml` | Zielrollen + `core_signals_*` für Scoring |
| `constraints.yaml` | Hard Gates + Soft Prefs + Application Rules (aktiv in Fit-Check) |
| `constraints_engine.py` | Hard/Soft-Auswertung am JD-Text |
| `fit_engine.py` | Scoring, Ranking, Präsenz-Ausnahme, Response-Bau |
| `POST /fit-check` | API-Einstieg |
| `completeness.py` / `profile_store.py` | Fit-ready % + Profile unter `profiles/{user_id}/` (gabriel → `domain/`) |
| `cv_ingest.py` / `cv_bootstrap.py` | CV-Upload → Text → Signal-/Rollen-Vorschläge + `cv_draft.md` |
| `GET /onboarding` | CV-Drop Startscreen + Review-Maske mit Progress-Bar |

## Inspiration von Mads Lorentzen / ai-job-search

**Übernommen (konzeptionell):** Dateien als SoT, Trennung Profil/Regeln/Logik/Docs, Pipeline-Denken, lokale Kontrolle.

**Bewusst anders:** Python/FastAPI; Fit als nachvollziehbare, deterministische Signal-Logik statt LLM-Scoring; Sourcing/Scraping ist inzwischen Teil des Systems, Auto-Apply bleibt aber bewusst aus (siehe [`SECURITY.md`](../SECURITY.md)).

## Phasen-Status

```
Phase 1  domain + fit_engine + /fit-check                    ✅ (V3 Freeze)
Phase 2  backend/generation/   → CV- & Anschreiben-Generator  ✅
Phase 3  backend/sourcing/     → Job-Sourcing (LinkedIn/       ✅
         Personio/Workday)
Phase 4  backend/tracking/     → Application Log + Decision-  ← aktuell
         Agent (Advocate/Skeptic/Decision)
Phase 5  optional Auto-Apply (regelngebunden)                 nicht begonnen,
                                                               bewusst zurückgestellt
```

Aktueller Stand ausführlicher: [`README.md`](../README.md#roadmap-kurz), [`SECURITY.md`](../SECURITY.md) (Threat-Model, u. a. welche Pfade heute wirklich ein LLM aufrufen).

## Tech-Stack

- Domain: YAML · API: FastAPI + Pydantic · Tests: pytest · lokal (uvicorn)
