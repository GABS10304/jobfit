# C24 Bank – (Senior) Produktmanager Anti-Financial Crime (m/w/d)

## Kontext
- Quelle: reale Jobbeschreibung (Paste, C24 Bank / CHECK24).
- Domäne: AML/AFC, mobile Banking, B2C-FinTech.
- Präsenz: nicht genannt; nur „zentrale Büros, ausgezeichnete Verkehrsanbindung“.
- Zweck: Dokumentation eines Betriebsfalls, kein Regel- oder Logik-Change (V3 freeze).

## Ergebnis
- Status: `no_go`
- `verify_product_ownership`: `false`
- Präsenz: `unclear` → `no_go`
- Hard Gates:
  - `remote_first_hybrid_ok`: `unclear` (blockiert)
  - `no_hard_sales`: `passed`
  - `product_ownership_required`: `unclear`
- Soft: `ai_or_data_preferred` matched (False Positive `rag`); regulated/B2B nicht matched
- Rollen-Scores: leer (Hard-Gate vor Scoring)

## Lesart
PM-Titel mit AML/Compliance-Fokus und BA-Anteil (Konzepte, User Stories, API-Analyse, Test). Kein AI-PM-Mandat. Präsenz-Gate blockiert; selbst bei Hybrid wäre Score-Fit schwach (< 30).

## Empfehlung
- Als `no_go`-Fall dokumentieren.
- Nicht verfolgen für Zielprofil AI/Product PM, remote-first.
- Nur bei Compliance-PM-Pivot Präsenz und Ownership nachklären.
