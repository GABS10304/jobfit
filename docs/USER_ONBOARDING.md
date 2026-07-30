# User Onboarding & Completeness

**Status:** Entwurf umgesetzt (Completeness + Profil-Store + API).  
**Freeze:** V3 Fit-Logik unverändert — Onboarding liefert nur Profil-Daten.

## Ziel

Andere User onboarding-fähig machen: **CV ablegen** → Maske vorausfüllen → **Fit-ready %** zeigt, was noch fehlt, bis `POST /fit-check` sinnvoll freigeschaltet ist.

## CV-first Flow

1. Startscreen `/onboarding`: „Hier dein CV ablegen“ (PDF, DOCX, MD, TXT)
2. `POST /onboarding/cv-upload` extrahiert Text, mappt Signale deterministisch (Lexikon, kein LLM)
3. Speichert `profiles/{user_id}/profile.yaml` + `cv_draft.md` (Struktur-Indikator analog `domain/Master-CV-structured.md`)
4. Review-Maske zeigt Fit-ready-%; Hard Constraints kommen **nicht** aus dem CV → typisch erst nach 3 Pflichtfragen = 100 %

**Formate:** PDF (`pypdf`), DOCX (`python-docx`), MD/TXT. Legacy `.doc` → Fehlermeldung (bitte als PDF/DOCX speichern).

## Zwei Prozentzahlen

| Feld | Bedeutung | Gate |
|------|-----------|------|
| `fit_ready_pct` | Pflichtblöcke (Rollen + Hard Constraints + Kernsignale), normalisiert auf 100 | **100 = Fit-Check freigeschaltet** |
| `profile_depth_pct` | inkl. optionaler Prefs (0–100) | nur Tiefe, kein Gate |

## Gewichte

### Fit-ready (Pflicht, Summe der Rohgewichte = 90 → normalisiert)

| Block | Rohgewicht | Regel |
|-------|------------|--------|
| Zielrollen | 25 | ≥1 Rolle mit `role_id` + `role_name` → 100 % des Blocks, sonst 0 |
| Hard Constraints | 30 | Je 10 Punkte für vorhandene IDs: `remote_first_hybrid_ok`, `no_hard_sales`, `product_ownership_required` (`enabled` true/false zählt als beantwortet) |
| Kernsignale | 35 | Pro Rolle: min. **5** `core_signals_skills` und **2** `core_signals_domains`. Block-% = Mittel über Rollen (0 Rollen → 0). Tools empfohlen, aber nicht gate-relevant |

`fit_ready_pct = round(100 * (roles_w + hard_w + signals_w) / 90)`

### Profile-Depth (inkl. Prefs, Gewicht 10)

Prefs-Block intern (je 25 %): Soft-Constraints vorhanden · Location (preferred oder travel) · Compensation (`min_annual_base` oder `target_annual_base`) · Job-Types `preferred` nicht leer.

`profile_depth_pct = round(roles_w + hard_w + signals_w + prefs_w)` mit Rohgewichten 25+30+35+10.

## Pflichtfragen (Intake)

1. Remote-Policy → speist Hard `remote_first_hybrid_ok`
2. Hard Sales ausschließen? → `no_hard_sales`
3. Product Ownership Pflicht? → `product_ownership_required`
4. Primäre Zielrolle(n) (max. 3 in Beta) → `roles[]`

CV-Bootstrap darf Signale vorschlagen; **SoT ist nur Bestätigtes** im User-Profil. Kein LLM-Scoring.

## Mapping auf Domain-Schemas

| Intake | Schema |
|--------|--------|
| Zielrollen + Signale | `RoleFitProfile` / `roles[]` |
| Hard/Soft/Prefs/Rules | `Constraints` |
| CV (optional) | `CvMaster` |
| Meta | `user_id`, `display_name`, `profile_version` |

Default-User `gabriel` liest weiter `domain/*.yaml` (bestehende SoT). Weitere User: `profiles/{user_id}/`.

## API

- `GET /onboarding` — Start (CV-Drop) + Review-Maske mit Progress-Bar
- `POST /onboarding/cv-upload` — multipart `file` + `user_id` (+ optional `display_name`)
- `GET /profiles/{user_id}/completeness` — %-Anzeige + `missing_required`
- `GET /profiles/{user_id}` — Profil
- `PUT /profiles/{user_id}` — Profil speichern (nicht `gabriel` Domain überschreiben)
- `POST /profiles` — leeres Profil anlegen
- `POST /fit-check` — optional `user_id` (lädt Profil; Gate bei &lt;100 % Fit-ready; ohne `user_id` → Domain-SoT)

## Referenz

Gabriel-Domain-Profil: `fit_ready_pct` ≈ **100**, `profile_depth_pct` &lt; 100 solange Compensation offen.
