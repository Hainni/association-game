# 🧠 Das große Assoziationsspiel  
_Ein Multiplayer-Browsergame mit Flask, Socket.IO & PWA-Unterstützung_

![Banner](static/img/banner.png)

---

## 🎮 Übersicht

**Das große Assoziationsspiel** ist ein webbasiertes Multiplayer-Spiel,  
bei dem Spieler*innen spontan Assoziationen zu zufälligen Kategorien eingeben.  
Das Spiel läuft rundenbasiert, Punkte werden vergeben, wenn sich alle Spieler einig sind.

Die Anwendung läuft lokal im Browser, lässt sich aber auch auf einem gemeinsamen WLAN-Server hosten.  
Dank **PWA-Unterstützung** kann sie auf Mobilgeräten installiert werden.

---

## ✨ Hauptfunktionen

| Funktion | Beschreibung |
|-----------|---------------|
| 🧍‍♂️ **Mehrspieler-Unterstützung** | Mehrere Spieler können gleichzeitig über verschiedene Geräte mitspielen. |
| 🧩 **Rundenbasiertes Spielprinzip** | Jede Runde gibt es eine neue Kategorie, zu der alle eine Antwort eingeben. |
| 💬 **Live-Synchronisierung** | Alle Aktionen werden über WebSockets in Echtzeit synchronisiert. |
| 🏅 **Punktesystem** | Punkte werden vergeben, wenn **alle Spieler „Richtig“ drücken** – d. h. alle sind sich einig. |
| 🔄 **Automatischer Rundenwechsel** | Sobald alle bereit sind, startet automatisch die nächste Runde. |
| 📱 **PWA (Progressive Web App)** | Kann auf iOS & Android installiert werden („Zum Startbildschirm hinzufügen“). |

---

## 🧩 Aufbau & Dateien

| Datei / Ordner | Zweck |
|-----------------|-------|
| `app.py` | Haupt-Serverlogik mit Flask + Socket.IO |
| `templates/` | HTML-Templates für `index.html`, `join.html`, `play.html`, `full.html` |
| `static/` | CSS, JS, Icons, Service Worker, Banner |
| `static/categories.txt` | Enthält die möglichen Kategorien für die Spielrunden |
| `static/manifest.json` | PWA-Konfiguration |
| `static/serviceWorker.js` | Caching und Offline-Support |
| `flask_session_data/` | Temporäre Sitzungsdaten (wird automatisch erstellt) |

---

## ⚙️ Installation & Start

### Voraussetzungen
- 🐍 **Python 3.8+**
- 📦 Abhängigkeiten: `Flask`, `Flask-SocketIO`, `Flask-Session`, `eventlet`

### Starten der App
```bash
python app.py
