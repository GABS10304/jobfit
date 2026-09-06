# Setup-Anleitung für absolute Anfänger

Diese Anleitung setzt **nichts** voraus — keine Programmiererfahrung, keine Terminal-Erfahrung, kein Claude-Account. Wenn du weißt, was ein Terminal ist und `git clone` kennst, reicht dir wahrscheinlich der Kurzweg in der [README](README.md#lokal-starten). Diese Anleitung hier ist für alle anderen.

## Was ist das hier überhaupt?

Ein Programm, das auf **deinem eigenen Computer** läuft (nicht im Internet, keine fremde Firma sieht deine Daten) und dir sagt, wie gut eine Stellenanzeige zu deinem Lebenslauf passt. Du lädst einmal deinen Lebenslauf hoch, kopierst dann Stellenanzeigen-Texte rein, und bekommst einen Score + eine Begründung.

Es kostet nichts, du brauchst kein Abo und keinen Claude-Account für diesen Grundablauf.

Kleine Vorwarnung: Es kommen gleich ein paar neue Begriffe (Terminal, venv, Server) und wahrscheinlich mindestens eine rote Fehlermeldung unterwegs — das ist völlig normal, kein Zeichen, dass etwas kaputt ist. Für fast jede Meldung steht unten bei "Troubleshooting" die Lösung in zwei Zeilen.

---

## Schritt 1: Python installieren (falls noch nicht vorhanden)

Python ist eine Programmiersprache — dieses Tool ist damit geschrieben und braucht sie, um zu laufen.

**Prüfen, ob du Python schon hast:**

- **Mac:** Öffne die App "Terminal" (Spotlight-Suche, Lupensymbol oben rechts, dann "Terminal" tippen und Enter). Tippe `python3 --version` und drücke Enter.
- **Windows:** Drücke die Windows-Taste, tippe `Eingabeaufforderung` (oder `PowerShell`), öffne es. Tippe `python --version` und drücke Enter.

Steht da etwas wie `Python 3.11.x` oder höher → weiter zu Schritt 2.

Kommt eine Fehlermeldung ("command not found" / "wird nicht erkannt") → Python installieren:

- Geh auf [python.org/downloads](https://www.python.org/downloads/) und lade die neueste Version herunter.
- **Windows wichtig:** Beim Installieren unten die Checkbox **"Add Python to PATH"** anhaken, bevor du auf Install klickst — sonst funktioniert Schritt 2 nicht.
- Nach der Installation das Terminal-Fenster schließen und neu öffnen, dann nochmal die Versions-Prüfung von oben machen.

## Schritt 2: Den Code herunterladen

> Falls du das hier als eingeladene:r Tester:in liest: Das Repository ist aktuell **privat**. Du brauchst einen kostenlosen GitHub-Account, und der Maintainer muss dich vorher unter GitHub → Repo → Settings → Collaborators einladen — sonst zeigt der Link unten nur eine 404-Fehlerseite. Wenn das noch nicht passiert ist, kurz beim Maintainer melden.

Kein Git-Wissen nötig:

1. Geh im Browser auf die GitHub-Seite des Projekts.
2. Klick oben rechts auf den grünen Button **"Code"**.
3. Klick auf **"Download ZIP"**.
4. Entpacke die ZIP-Datei (Doppelklick, meistens landet sie im Downloads-Ordner als Ordner mit "-main" im Namen).

## Schritt 3: Ins Projekt-Verzeichnis wechseln

Im selben Terminal-Fenster von Schritt 1:

**Mac:**
```bash
cd ~/Downloads/job-fit-system-main
```

**Windows:**
```powershell
cd Downloads\job-fit-system-main
```

(`cd` = "change directory", also "wechsle in diesen Ordner". Falls der Ordner woanders liegt oder anders heißt: im Dateimanager reinschauen und den Pfad anpassen.)

Tipp: Wenn du dir nicht sicher bist, tippe `cd ` (mit Leerzeichen danach, ohne Enter) und zieh den entpackten Ordner mit der Maus ins Terminal-Fenster — der Pfad wird automatisch eingefügt.

## Schritt 4: Eine "isolierte Box" für die Pakete erstellen

Das Programm braucht ein paar Zusatz-Pakete. Damit die nicht mit anderen Programmen auf deinem Rechner durcheinanderkommen, packen wir sie in eine eigene, abgeschottete Umgebung ("virtuelle Umgebung").

**Mac:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (Eingabeaufforderung/cmd — empfohlen, einfacher):**
```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

**Windows (PowerShell — falls du die statt Eingabeaufforderung geöffnet hast):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

> Wichtig: In PowerShell **muss** es `Activate.ps1` heißen (mit der Endung!). Nur `activate` oder `.venv\Scripts\activate` tippen sieht in PowerShell so aus, als würde es funktionieren — es passiert aber nichts Sichtbares und die venv bleibt in Wirklichkeit inaktiv. Wenn du unsicher bist, welches Fenster du offen hast: einfach die cmd-Variante oben nehmen, die funktioniert so oder so.

Wenn's geklappt hat, steht jetzt `(.venv)` ganz vorne in deiner Terminal-Zeile. Das musst du bei **jeder neuen Terminal-Sitzung** wiederholen (den Activate-Befehl), bevor du mit dem Tool arbeitest.

> PowerShell-Sonderfall: Falls beim `Activate.ps1`-Befehl eine Fehlermeldung über "execution policy" kommt, einmalig ausführen: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` und die Nachfrage mit `J`/`Y` bestätigen. Dann `Activate.ps1` nochmal versuchen. (Bei der cmd-Variante oben tritt dieser Fehler nicht auf.)

## Schritt 5: Pakete installieren

```bash
pip install -r requirements.txt
```

Das dauert 1–3 Minuten und lädt eine Menge Text. Das ist normal. Wenn am Ende keine Zeile mit "ERROR" steht, hat's geklappt.

Optional (für hübschere PDF-Vorschauen, kann man später nachholen):
```bash
playwright install chromium
```

## Schritt 6: Das Programm starten

```bash
uvicorn backend.main:app --reload --port 8000
```

Es erscheinen ein paar Zeilen Text, unter anderem etwas wie `Uvicorn running on http://127.0.0.1:8000`. **Das Terminal-Fenster muss jetzt offen bleiben** — das ist der "Server", der im Hintergrund läuft, solange du das Tool benutzt. Schließt du das Fenster, geht das Tool aus.

## Schritt 7: Im Browser öffnen

Öffne einen Browser (Chrome, Safari, Firefox, egal) und geh zu:

```
http://127.0.0.1:8000/onboarding
```

Dort siehst du eine Seite zum:

1. **CV hochladen** (PDF, Word/DOCX oder reiner Text) — daraus baut das Tool dein Profil.
2. **Profil prüfen** — hier musst du kurz aktiv werden, nicht nur drüberschauen:
   - Oben siehst du einen Fortschrittsbalken **"Fit-ready"**. Der steht nach dem Upload noch nicht bei 100 % — das ist normal, nicht ausfüllbar aus dem CV allein.
   - Weiter unten findest du 3 Dropdown-Felder (**Remote-Policy**, **Hard Sales ausschließen?**, **Product Ownership erforderlich?**) plus ein Feld für deine **Zielrolle** und **Skills/Domains** (durch Komma getrennt, mindestens 5 Skills und 2 Domains). Die sind meist schon sinnvoll vorausgefüllt — kurz drüberschauen reicht in der Regel, anpassen kannst du trotzdem.
   - **Wichtig:** Erst wenn du unten auf **"Speichern & %-Stand aktualisieren"** klickst und der Fit-ready-Balken 100 % zeigt, erscheint der nächste Abschnitt überhaupt. Ohne diesen Klick bleibt Schritt 3 unsichtbar — das ist kein Fehler, sondern Absicht, wirkt aber leicht wie ein Sackgasse, wenn man's nicht weiß.
3. **Ersten Job testen** (erscheint erst nach Schritt 2) — eine Stellenanzeige (Text reinkopieren) gegen dein Profil prüfen lassen. Du bekommst einen Score und eine Erklärung, was passt und was nicht.

Das war's — mehr braucht's für den Grundablauf nicht.

## Wie höre ich auf?

Geh zurück ins Terminal-Fenster aus Schritt 6 und drücke `Strg + C` (Windows) bzw. `Cmd + .` oder `Ctrl + C` (Mac). Der Server stoppt.

Willst du später weitermachen: Terminal öffnen, in den Projektordner wechseln (Schritt 3), `.venv` aktivieren (Schritt 4, zweite Zeile), dann Schritt 6 wiederholen.

## Deine Daten

Alles bleibt auf deinem Computer. Es gibt keinen Login, keine Cloud, niemand außer dir sieht deinen Lebenslauf oder die Stellenanzeigen, die du reinkopierst — solange du nur diesen Grundablauf (Onboarding + Fit-Check) nutzt. (Mehr Details, auch zu den optionalen KI-Funktionen, die einen eigenen API-Schlüssel bräuchten und hier nicht gebraucht werden: [SECURITY.md](SECURITY.md).)

---

## Was du testen sollst

Da du das gerade als Tester/in ausprobierst, wären hilfreiche Rückmeldungen:

- Hat das Hochladen deines Lebenslaufs geklappt? Wurden die erkannten Infos im Profil-Check als sinnvoll/richtig angezeigt?
- Wenn du eine echte Stellenanzeige reinkopierst: Ist die Erklärung zum Score nachvollziehbar, oder wirkt sie zufällig/unklar?
- Ist irgendwo eine Fehlermeldung aufgetaucht? Wenn ja: welcher Schritt genau, und was stand in der Fehlermeldung (am besten Screenshot)?
- War irgendein Schritt in dieser Anleitung selbst verwirrend oder hat nicht funktioniert wie beschrieben?

## Troubleshooting (häufige Stolpersteine)

- **"python3: command not found" / "python wird nicht erkannt"** → Python ist nicht installiert oder nicht im PATH. Zurück zu Schritt 1, bei Windows unbedingt "Add to PATH" anhaken.
- **"pip: command not found" nach dem Aktivieren der venv** → venv wurde nicht wirklich aktiviert. Prüfen, ob `(.venv)` in der Terminal-Zeile steht; Schritt 4 wiederholen.
- **Port 8000 schon belegt** ("Address already in use") → Ein alter Server läuft noch. Terminal-Fenster suchen, in dem er gestartet wurde, `Strg+C` drücken, dann Schritt 6 erneut versuchen. Oder einen anderen Port nutzen: `uvicorn backend.main:app --reload --port 8001` und dann im Browser `:8001` statt `:8000` verwenden.
- **`pip install` bricht mit einem langen roten Fehlertext ab** → Meistens ein Zusatzpaket, das einen Compiler braucht. Auf dem Mac hilft oft: `xcode-select --install` einmal ausführen, dann `pip install -r requirements.txt` erneut versuchen.
- **Seite im Browser lädt nicht / "kann nicht erreicht werden"** → Prüfen, ob im Terminal (Schritt 6) noch die `Uvicorn running...`-Zeile zu sehen ist und keine Fehlermeldung danach kam. Falls das Terminal-Fenster versehentlich geschlossen wurde: Schritt 6 neu ausführen.

Wenn nichts davon hilft: Screenshot vom Fehler + welcher Schritt genau, dann kurz melden.
