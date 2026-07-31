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

## Offene Punkte / nächste Schritte

- [ ] Datenmodell/DB-Schema für Multi-Tenancy konkret skizzieren (noch nicht gemacht)
- [ ] `cover_letter_service.py` tatsächlich implementieren (ruft die API mit dem Prompt aus `cover_letter_prompt.py` auf) — braucht Anthropic-API-Key-Setup, Retry-/Error-Handling
- [ ] Automatischer Grounding-Check konkret spezifizieren
- [ ] Kosten-Modell grob durchrechnen (API-Kosten + Hosting vs. 19,99 €/Monat)
- [ ] Phase 2 (Auto-Formularausfüllung) erst angehen, wenn Phase 1 steht — inkl. der ToS-/Safety-Guardrails oben
