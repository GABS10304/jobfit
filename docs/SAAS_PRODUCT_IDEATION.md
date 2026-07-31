# SaaS-Produkt-Ideation: job-fit-system als externe Web-App (19,99 €/Monat)

Status: Ideation/Brainstorming, keine beschlossene Roadmap. Festgehalten am 2026-07-31, damit der Gedankengang nicht verloren geht.

## Produktvision (User Story, Entwurf)

Als zahlender Nutzer (19,99 €/Monat)
möchte ich mein CV hochladen und täglich automatisch gematchte Jobs mit fertigen, tailored Bewerbungsunterlagen bekommen,
damit ich meine Jobsuche nicht mehr manuell pflegen muss.

**Akzeptanzkriterien (Entwurf):**
- Given Registrierung + Zahlung, when Onboarding abgeschlossen, then eigenes isoliertes Profil (kein Zugriff auf andere Nutzerdaten)
- Given tägliche Suche, when neue Treffer da sind, then Benachrichtigung (E-Mail/Push) + Dashboard zeigt Shortlist
- Given ein Nutzer klickt "Ja" zu einem Job, when die Anschreiben-Generierung läuft, then läuft sie automatisiert (Claude-API-Call, keine manuelle Chat-Session) mit denselben "nichts erfinden"-Leitplanken
- Given fertiges Dokument, when Nutzer reviewt, then Freigabe/Ablehnung im UI, danach PDF-Download
- Given Abo, when Kündigung, then Datenlöschung nach DSGVO-Frist

## Phasenaufteilung

**Phase 1 (Kernprodukt):** Tailored Anschreiben + CV. Technisch größtenteils schon bewiesen durch `job-fit-system` (Fit-Engine, SelectionPlan, deterministische PDF-Generierung). Einziger echter Blocker: die Anschreiben-Generierung läuft heute interaktiv ("Claude schreibt live im Chat"), das trägt kein Multi-Tenant-Produkt.

**Phase 2 (Erweiterung, später):** Automatische Formularausfüllung + eigenständiges Hochladen der PDFs auf Bewerbungsportalen, vermutlich über MCP-Browser-Automation (z. B. Claude-in-Chrome-Skill oder ein Playwright-MCP-Server).

⚠️ **Wichtiger Vorbehalt zu Phase 2:** Das bestehende `job-fit-system` hat "kein Auto-Apply" als explizites Designprinzip (`auto_apply_enabled: false`, `require_manual_approval_for_submit: true` in `domain/constraints.yaml`) — genau aus dem Grund, den Phase 2 anfasst. Vollautonomes Massen-Ausfüllen von Formularen auf fremden Plattformen ist rechtlich/ToS-technisch heikler (viele Bewerbungsportale verbieten automatisierte Bot-Einreichungen) und schwerer rückgängig zu machen als ein PDF zu erzeugen. Empfehlung: Phase 2 als "Human-in-the-Loop-Assist" bauen — Formular vorausfüllen + Dokument hochladen, aber der Mensch klickt den finalen "Absenden"-Button, nicht ein Bot, der eigenständig auf hunderten Seiten einreicht.

## Phase 1 — Lösungsideation

### Kernmechanismus: Anschreiben-Generierung produktisieren

Das cv-tailor-SKILL.md (`Documents/cv-software/.claude/skills/cv-tailor/`), das im Chat bereits zweimal manuell angewendet wurde, wird zum System-Prompt eines Backend-Service:

- **`backend/generation/cover_letter_service.py`** (Service, noch zu bauen) ruft die Claude API mit `context.json` (aus `prepare_application_draft.py`: JD-Text, matched_signals, gefilterte belegte Master-CV-Fakten — "TODO"/unbelegte Claims werden vorher rausgefiltert, gehen also gar nicht erst in den Prompt) auf.
- **System-Prompt + Output-Schema bereits ausformuliert:** [`backend/generation/cover_letter_prompt.py`](../backend/generation/cover_letter_prompt.py) — die cv-tailor-Regeln (DIN-5008-Struktur, 93%-Regel, "nichts erfinden", Belegstärke respektieren, aktiv statt passiv) übersetzt von einer interaktiven Skill (fragt bei Lücken nach) in einen nicht-interaktiven Produktions-Prompt (muss aus dem Input allein arbeiten).
- **Rückfrage-Ersatz:** Da es in der Automatisierung keinen Menschen für Rückfragen mitten in der Generierung gibt, wandert jede Unsicherheit/Lücke/jeder Widerspruch in ein strukturiertes `flags`-Feld im Output — das ersetzt die interaktive Nachfrage und wird stattdessen dem zahlenden Kunden in der Review-UI angezeigt.
- **Automatischer Grounding-Check als zweiter Schritt (noch nicht gebaut):** ein zweiter, günstigerer Call extrahiert alle Fakten-Claims aus dem Entwurf und gleicht sie gegen die Eingabefakten ab — kein Garant, aber ein Sicherheitsnetz gegen Halluzination, bevor der Kunde es sieht.

**Was unverändert bleibt (das ist der eigentliche USP):** Die CV-Generierung bleibt 100 % deterministisch (`SelectionPlan`, `generate_cv_variant`, `generate_cv_variant_pdf`) — kein LLM, komplett erklärbar. Verkaufsargument: "Dein CV wird nie erfunden, dein Anschreiben ist KI-Text auf verifizierter Faktenbasis."

**Human-in-the-Loop verschiebt sich vom Chat zum Kunden:** Statt dass Gabriel/Claude Code in einer Chat-Session freigibt, reviewt der zahlende Kunde im Web-UI (Entwurf editierbar, "Absatz X neu generieren", dann "Freigeben" → finales PDF). Die Rolle, die bisher für Gabriel manuell übernommen wurde, übernimmt jetzt jeder Kunde für sich selbst.

### Architektur-Anschlussstücke

- **Multi-Tenant-Storage:** `backend/models.py`s `UserProfile`-Schema passt schon fast 1:1 als DB-Zeile (Postgres/JSONB) — `backend/profile_store.py` müsste nur das Storage-Backend tauschen (YAML-Datei → DB), das Interface kann gleich bleiben.
- **Sourcing zentral cachen statt pro Nutzer neu scrapen:** gleiche Boards für mehrere Nutzer → einmal crawlen, pro Nutzer nur den (günstigen, deterministischen) Fit-Check laufen lassen. Wichtig sowohl für Kosten als auch um Rate-Limits/429 bei den Jobbörsen nicht zu vervielfachen.
- **Scheduling:** weg von `launchd` auf Gabriels Mac, hin zu einem echten Cloud-Scheduler, der pro Nutzer den Sourcing-Lauf triggert (oder zentral einmal pro Board, s. o.).
- **Kosten-Sanity-Check:** Claude-API-Kosten pro Anschreiben (kurzer Prompt + Completion) dürften im Cent-Bereich liegen — bei 19,99 €/Monat und vermutlich unter 20 generierten Anschreiben/Monat pro Nutzer bleibt das unkritisch, lohnt sich aber vor Launch grob durchzurechnen.
- **Billing:** Stripe Checkout für ein einzelnes Abo-Preismodell — Standardweg, wenig Integrationsaufwand.
- **DSGVO:** Datenlöschung nach Kündigung, Privacy Policy, ggf. Auftragsverarbeitungsvertrag (AVV) für die Claude-API-Nutzung mit Kundendaten.

### MVP-Vorschlag

Nicht das ganze SaaS auf einmal bauen. Reihenfolge:
1. Backend + Postgres-Swap (Multi-Tenancy) + Anschreiben-Service (größter Hebel, Prompt ist quasi schon fertig getestet)
2. Schlankes Web-UI (Dashboard/Review/Settings) — Onboarding, Shortlist-Dashboard, Review-Screen (CV+Anschreiben nebeneinander, editierbar), Settings (Gehalt/Ausschluss/Impact, existiert schon als `/settings`, braucht nur Multi-Tenant-Auth-Wrapper + hübscheres Frontend)
3. Stripe Checkout fürs Abo
4. Automatischer Grounding-Check (Qualitätssicherung vor Kunden-Review)

## Datenmodell-Skizze (Multi-Tenancy)

Hybrid-Ansatz: relational normalisiert, wo Multi-Tenant-Grenzen, Uniqueness oder Status-Übergänge eine Rolle spielen; JSONB-Blobs, wo heute schon ganze Pydantic-Objekte geladen/gespeichert werden (kein Bedarf, `CvMaster.employments[]` einzeln abzufragen — wird immer als Ganzes geladen, genau wie `data_loader.load_cv_master()` es heute tut).

```sql
-- Konto/Auth
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT UNIQUE NOT NULL,
    display_name    TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 1:1 zu backend/models.py::UserProfile — cv_master/role_fit_profile/constraints
-- bleiben JSONB, validiert per Pydantic auf App-Ebene beim Lesen/Schreiben
-- (ersetzt profiles/<user_id>/profile.yaml; domain/*.yaml bleibt Gabriels
-- eigener Fixtures-/Referenz-Stand, kein Sonderfall mehr in Produktion).
CREATE TABLE user_profiles (
    user_id            UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    profile_version     TEXT NOT NULL DEFAULT '0.1',
    cv_master           JSONB,            -- CvMaster, nullable bis Onboarding fertig
    role_fit_profile    JSONB NOT NULL DEFAULT '{"version":"0.1","roles":[]}',
    constraints         JSONB NOT NULL DEFAULT '{}',  -- inkl. compensation, excluded_companies, impact_notes
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Billing (Stripe)
CREATE TABLE subscriptions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    stripe_customer_id      TEXT NOT NULL,
    stripe_subscription_id  TEXT NOT NULL UNIQUE,
    status                  TEXT NOT NULL,   -- active | past_due | canceled ...
    current_period_end     TIMESTAMPTZ NOT NULL
);

-- Ersetzt domain/personio_boards.yaml + workday_boards.yaml — geteilt über
-- alle Nutzer, nicht pro Nutzer dupliziert.
CREATE TABLE job_boards (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type     TEXT NOT NULL,     -- personio | workday
    name            TEXT NOT NULL,
    url             TEXT NOT NULL,
    region          TEXT,
    disabled        BOOLEAN NOT NULL DEFAULT false
);

-- Zentraler Scrape-Cache: EIN Eintrag pro entdeckter Stelle, unabhängig davon
-- wie viele Nutzer dagegen matchen — genau der Punkt aus dem "Sourcing
-- zentral cachen"-Absatz oben, der Rate-Limit-Risiko und Redundanz vermeidet.
CREATE TABLE job_postings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    board_id            UUID NOT NULL REFERENCES job_boards(id),
    external_job_id     TEXT NOT NULL,   -- z. B. Personio-Job-ID aus der URL
    title               TEXT NOT NULL,
    url                 TEXT NOT NULL,
    jd_text             TEXT NOT NULL,
    location            TEXT,
    work_mode           TEXT,
    employment_type     TEXT,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (board_id, external_job_id)
);

-- Ersetzt backend/tracking/state_store.py (JSON-Datei) — ein Eintrag pro
-- (Nutzer, Stelle), inkl. des gleichen Status-Lifecycles wie heute schon
-- in state_store.py definiert (new -> proposed -> approved -> draft_ready
-- -> finalized, + rejected). top_score/status_flag kommen 1:1 aus dem
-- deterministischen Fit-Check, pro Nutzer unterschiedlich (gleiche Stelle,
-- anderes Master-CV -> anderer Score).
CREATE TABLE user_job_matches (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_posting_id      UUID NOT NULL REFERENCES job_postings(id),
    status_flag         TEXT,            -- proceed | verify_product_ownership | no_go
    top_score           INTEGER,
    sourcing_bucket     TEXT NOT NULL,   -- passed | watchlist
    status              TEXT NOT NULL DEFAULT 'proposed',
    first_seen          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, job_posting_id)
);

-- Entwurf: CV-Markdown (deterministisch) + Anschreiben als strukturierter
-- Output gemäß backend/generation/cover_letter_prompt.py::COVER_LETTER_OUTPUT_SCHEMA,
-- inkl. der flags (Lücken/Unsicherheiten fürs Kunden-Review-UI).
CREATE TABLE application_drafts (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_job_match_id       UUID NOT NULL REFERENCES user_job_matches(id) ON DELETE CASCADE,
    cv_markdown             TEXT NOT NULL,
    cover_letter_json       JSONB NOT NULL,   -- siehe COVER_LETTER_OUTPUT_SCHEMA
    cover_letter_flags      JSONB NOT NULL DEFAULT '[]',
    edited_by_user          BOOLEAN NOT NULL DEFAULT false,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Final: erst nach Kunden-Freigabe, ersetzt out/applications_ready/*.pdf
-- (lokale Datei) durch eine Objektspeicher-Referenz (S3/GCS o. ä.).
CREATE TABLE application_finals (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_draft_id    UUID NOT NULL REFERENCES application_drafts(id),
    pdf_object_key          TEXT NOT NULL,   -- Pfad/Key im Objektspeicher
    finalized_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Warum kein voll normalisiertes `employments`/`projects`-Schema:** Die Fit-Engine, `selection_plan.py` und die CV-Generierung laden `CvMaster` heute immer als Ganzes (`data_loader.load_cv_master()`), nie einzelne Stationen isoliert. Eine relationale Aufsplittung würde nur Joins ohne Nutzen erzeugen — der JSONB-Blob mit Pydantic-Validierung auf App-Ebene reicht und spiegelt exakt das bestehende `domain/cv_master.yaml`-Schema.

**Migrationspfad von heute:** `backend/profile_store.py` bekommt ein DB-Backend statt Dateisystem, Interface (`load_user_profile`/`save_user_profile`/…) bleibt gleich — Aufrufer (API-Endpunkte, Fit-Engine) merken im Idealfall nichts vom Wechsel.

## Offene Punkte / nächste Schritte

- [x] Datenmodell/DB-Schema für Multi-Tenancy konkret skizzieren
- [ ] `cover_letter_service.py` tatsächlich implementieren (ruft die API mit dem Prompt aus `cover_letter_prompt.py` auf) — braucht Anthropic-API-Key-Setup, Retry-/Error-Handling
- [ ] Automatischer Grounding-Check konkret spezifizieren
- [ ] Kosten-Modell grob durchrechnen (API-Kosten + Hosting vs. 19,99 €/Monat)
- [ ] Phase 2 (Auto-Formularausfüllung) erst angehen, wenn Phase 1 steht — inkl. der ToS-/Safety-Guardrails oben
