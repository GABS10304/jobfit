# /open-topics – Master-CV mit offenen Themen anreichern

Die tägliche Shortlist listet für **jeden** neuen Treffer (Strong-Pass **und** Watchlist) die „offenen Themen": Anforderungen, die die Stellenanzeige nennt, zu denen im Master-CV (`domain/cv_master.yaml`) aber noch nichts steht. Regel aus dem Skalar-Fall (Okt 2026): **„Kein Beleg im CV" ist eine Frage, keine Lücke.** Dieser Befehl arbeitet die Fragen mit dem Nutzer ab.

Optionales Argument `$ARGUMENTS`: eine Topic-ID (z. B. `evals`), um nur dieses Thema zu besprechen.

---

## Schritt 1: Offene Themen holen

```bash
python scripts/open_topics.py list
```

Ist `$ARGUMENTS` gesetzt, nur dieses Thema. Sonst die **drei** häufigsten nehmen. Nicht alle auf einmal fragen.

## Schritt 2: Fragen – ein Thema nach dem anderen

Für jedes Thema die `question` stellen und konkret nachhaken, bis die Antwort CV-tauglich ist:

- **Wo?** Rolle, Projekt, Zeitraum
- **Was genau?** Eigener Beitrag, nicht der des Teams
- **Wie?** Methode, Tools
- **Ergebnis?** Zahl oder Entscheidung, die daraus folgte
- **Beleg?** Zeugnis, Repo, Doku, Referenzperson

Nichts erfinden, nichts aufhübschen. Was der Nutzer nicht sagt, steht nicht im CV.

## Schritt 3: In den Master-CV schreiben

- Passende Stelle in `domain/cv_master.yaml` finden: bestehende Rolle oder Projekt ergänzen, nur wenn nötig neues Projekt anlegen.
- Belegstärke-Tag nach dem, was der Nutzer genannt hat: `[belegt]` (Zeugnis/Dokument), `[teilweise belegt]` (plausibel, Beleg nur teilweise), `[qualitativ belegt]` (keine Zahl).
- Neue Skills/Tools zusätzlich unter `skills` bzw. `tools` aufnehmen, damit die Topic-Erkennung sie beim nächsten Lauf findet.
- `domain/cv_master.json` synchron halten (gleicher Inhalt).
- **Immer beide CV-Fassungen nachziehen** (Regel, siehe `docs/CV_SOURCES.md`): dieselbe Aussage auch in `domain/Master-CV-structured.md` und im cv-tailor-Spiegel `domain/cv-tailor-master-cv.md` eintragen – im selben Commit. Danach dem Nutzer sagen, dass die Skill-Datei auf claude.ai ersetzt werden muss.
- Dem Nutzer den Diff zeigen und bestätigen lassen, **bevor** gespeichert wird.

## Schritt 4: Status setzen

```bash
python scripts/open_topics.py answer <id> --note "<kurz: wo/was>"   # in den CV übernommen
python scripts/open_topics.py none <id>                              # keine Erfahrung → nicht mehr fragen
```

Zum Schluss in einem Satz sagen, welche Themen jetzt im CV stehen und welches das nächste häufigste offene Thema ist.
