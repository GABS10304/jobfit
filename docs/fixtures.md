# Fixtures

## Beta

Persönlicher Job-Fit-Assistent: Betriebsfälle dokumentieren, Entscheidungen nachvollziehbar machen.

**Ablauf:** Paste/JD → V3 Fit-Check (`job-fit-system`, frozen) → PM-Lesart → optional Fixture.

**Nicht im Scope:** Kein Sourcing/Scraping, keine Auto-Apply, keine Ableitung von Produktlogik aus Fixtures.

**V3-Freeze:** Keine Regel- oder Schwellenwert-Änderungen aus Einzelfällen.

**Known limits:**
- Paste-only; kein URL-Scraping
- Fehlende Remote/Hybrid-Angabe → fail-closed `no_go`
- Recruiter-Pings ohne JD unvollständig
- Bekannte Engine-Artefakte (Substring false positives) — dokumentieren, nicht ohne Review „fixen“

**Fixture-Format:** Kontext, Ergebnis, Lesart, Empfehlung. Statuswerte: `proceed`, `verify`, `no_go`. Bei Unklarheit `verify` statt überinterpretieren.

**SSOT:** `domain/fixtures/*.md` (Index hier); YAML-Referenzen nur wo maschinell gekoppelt.

## TeamViewer – AI Product / Discovery-nah
- Ergebnis: `verify_product_ownership`
- Präsenz: `remote_first_ok` / `ok`
- Sales-Gate: passed
- Ownership: unclear → Verify
- Status: realer Betriebsfall, nur dokumentieren
- Kanonisch: `ops_teamviewer_ai_product_discovery_hybrid.md` · `.yaml`
- Alias (superseded): `teamviewer-ai-product-discovery` (citizen-sdlc-fixtures)

## Starke Produktrolle mit mehr Präsenz
- Ergebnis: `verify_product_ownership`
- Präsenz: `exception_granted` möglich
- Ownership: unklar bis implizit
- Status: Grauzonenfall, nur bei hohem Fit
- Kanonisch: `ops_strong_product_more_presence.md`
- Alias (superseded): `strong-product-role-more-onsite` (citizen-sdlc-fixtures)

## Koordinationslastige Rolle mit Produktanteil
- Ergebnis: `verify_product_ownership`
- Präsenz: hybrid / flexibel
- Ownership: unklar
- Status: Grauzonenfall, sauber klären
- Kanonisch: `ops_coordination_with_product_share.md` (verwandt: `ref_smoke_pack_v3.yaml` JD3)
- Alias (superseded): `coordination-heavy-product-signal` (citizen-sdlc-fixtures)

## FLEX Capital – AI Product Manager (m/w/d)
- Ergebnis: `proceed`
- Präsenz: `remote_first_ok` / `ok` (Cue: `hybrid`)
- Sales-Gate: passed
- Ownership: passed; Score-Fit schwach
- Status: realer Betriebsfall, nur dokumentieren
- Datei: `flex-capital-ai-product-manager.md`

## Owkin – Agentic AI Product Builder (K Pro)
- Ergebnis: `proceed`
- Präsenz: `remote_first_ok` / `ok` (Cue: `remote`)
- Sales-Gate: passed
- Ownership: passed; Score-Fit schwach
- Status: realer Betriebsfall, nur dokumentieren
- Datei: `owkin-agentic-ai-product-builder.md`

## BLP Digital – Functional Consultant & Project Manager
- Ergebnis: `verify_product_ownership`
- Präsenz: `remote_first_ok` / `ok` (Cue: `remote`)
- Sales-Gate: passed
- Ownership: unclear → Verify
- Status: realer Betriebsfall, nur dokumentieren
- Datei: `blp-digital-functional-consultant-project-manager.md`

## ING – Prozessmanager Customer Data (w/m/d)
- Ergebnis: `verify_product_ownership`
- Präsenz: `remote_first_ok` / `ok` (Cue: `hybrid`)
- Sales-Gate: passed
- Ownership: unclear → Verify; Top-Score 36 (< 75)
- Status: Grenzfall, nur dokumentieren
- Datei: `ing-prozessmanager-customer-data.md`

## C24 Bank – Produktmanager Anti-Financial Crime
- Ergebnis: `no_go`
- Präsenz: `unclear` → blockiert
- Ownership: `unclear`
- Status: AML/Compliance-PM, kein AI/remote-first-Fit
- Datei: `c24-bank-produktmanager-anti-financial-crime.md`

## Redcare Pharmacy – Product Manager Agentic AI Platform
- Ergebnis: `no_go`
- Präsenz: `unclear` → blockiert (Work mode nicht in JD)
- Sales-Gate: passed
- Ownership: passed (Cue: „product manager“)
- Status: realer Betriebsfall, nur dokumentieren
- Datei: `redcare-product-manager-agentic-ai-platform.md`

---

## Weitere YAML-Referenzen

| Datei | Zweck |
|-------|--------|
| `ref_smoke_pack_v3.yaml` | 4 Smoke-JDs mit Erwartungswerten (Stabilitätscheck) |
| `ref_junior_product_transformation_lead_remote_first.yaml` | Junior Grauzone, ≤1 Office-Tag |
| `ref_senior_product_transformation_lead_hybrid.yaml` | Senior Hybrid Grauzone |
| `ops_teamviewer_ai_product_discovery_hybrid.yaml` | Maschinelles Pendant TeamViewer |
