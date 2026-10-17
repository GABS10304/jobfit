# CV-Quellen und Sync-Regel

Es gibt zwei Fassungen von Gabriels Master-CV. Beide müssen **immer gemeinsam** nachgezogen werden (Regel vom 17.10.2026, ausgelöst durch den Skalar-Fall).

| Fassung | Datei | Wer liest sie |
|---|---|---|
| Strukturiert (Fit-Engine, Shortlist, Open Topics, `/apply`) | `domain/cv_master.yaml` + `domain/cv_master.json` + `domain/Master-CV-structured.md` | job-fit-system |
| Erzählend (CV-Tailoring im Chat) | `domain/cv-tailor-master-cv.md` (Spiegel) → `references/master-cv.md` im cv-tailor-Skill | cv-tailor-Skill |

## Regel

1. **Jede** neue oder geänderte CV-Aussage (z. B. aus `/open-topics`) wird in **allen** Dateien oben eingetragen – im selben Commit.
2. `cv_master.yaml` und `cv_master.json` müssen inhaltlich identisch sein (`yaml.safe_load(...) == json.load(...)`).
3. Belegstärke-Tags bleiben erhalten. Was Gabby ausdrücklich verworfen hat, fliegt aus **beiden** Fassungen (z. B. JTL „Teamproduktivität +25 %").
4. Widersprüche werden nicht stillschweigend aufgelöst, sondern als `open_todos` geparkt.
5. Nach Änderungen am Spiegel `domain/cv-tailor-master-cv.md` muss die Datei im cv-tailor-Skill auf claude.ai ersetzt werden – Änderungen in einer Chat-Sitzung an der Skill-Kopie bleiben dort nicht dauerhaft erhalten.

## Warum

Am 17.10.2026 zeigte der Abgleich: Die Fassungen waren auseinandergelaufen (Ausbildung, Aktuar/ORAKEL, bestätigte FIS-/GBS-/Weidmüller-Belege fehlten im Repo; eine verworfene JTL-Zahl stand noch drin). Die Fit-Engine hat Gabby dadurch mit einem unvollständigen Profil bewertet.
