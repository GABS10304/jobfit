# CV Passed Review (Sprint 11)

Review der beiden Strong-Pass-CVs gegen deutsche ATS-/PM-Standards.  
Quellen: `out/cv_passed/*` (regeneriert nach Renderer-Fix), JDs aus `/tmp/multi_board_sprint10.json`, Master-CV unverändert.

| Check | FLEX (76) | credium (79) | Notes |
|-------|-----------|--------------|-------|
| Nur echte Master-CV-Bullets (keine Erfindung) | **pass** | **pass** | Selection nur aus `cv_master`; Meta-Bullet „CV-Varianten“ ausgeschlossen |
| Role focus AI/Product PM | **pass*** | **pass** | *FLEX enthält noch Scrum-Master-Station (JTL); RIWA/FIS/Projekte tragen den AI-PM-Fit |
| Section order ATS-freundlich | **pass** | **pass** | Profil → Erfahrung → Projekte → Skills → Tools → Zertifizierungen |
| Keyword-Overlap natürlich | **pass** | **pass** | Kein Stuffing; JD-nahe Auswahl (Python, Prototypen, Discovery, AI) |
| Evidence / keine TODO-Bullets | **pass** | **pass** | `[TODO]` ausgeschlossen; Provenance-Tags (`[belegt]` …) im Renderer gestrippt |
| Länge / Klarheit | **pass*** | **pass*** | *~2 Seiten ok; Zertifikatsliste lang; einzelne Problem-Fragmente als Bullets schwach |

## Fixes in diesem Sprint (Renderer / Rules only)

- Provenance-Tags (`[belegt]`, `[teilweise belegt]`, …) werden beim Render entfernt.
- Meta-Notizen mit `CV-Varianten` / `Original-CV` werden nicht mehr selektiert.
- Profil-Kernel beginnt mit Großbuchstaben.

Keine Master-CV-Claims umgeschrieben.

## Nächste Verbesserungen (kein Claim-Rewrite ohne Review)

1. Master-Bullets wie „Produkt/Proof ist weiterhin live“ fachlich klarer formulieren (SSOT-Edit).
2. Project-Selection: `problem`-Fragmente hinter `approach`/`result` priorisieren oder nicht allein ausgeben.
3. Zertifizierungen auf Top-N (z. B. PSPO/PSM/PAL + Product) begrenzen für ATS-Länge.
4. FLEX: Employment-Ranking stärker an `ai_product_manager`-Signalen ausrichten (Scrum-Master nur wenn JD Coach-Signale hat).
5. Optional: kurzes JD-spezifisches Profil (weiterhin nur aus Master-Kernel + Role-Name, keine erfundenen Achievements).
