from flask import Flask, render_template, redirect, url_for, request as flask_request
from flask_session import Session
from flask_socketio import SocketIO, emit
import os, random, time, json, logging
import eventlet

logging.getLogger('eventlet.wsgi').setLevel(logging.ERROR)

app = Flask(__name__)
app.secret_key = 'super_secret_key_123'

# Session-Konfiguration
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(app.root_path, 'flask_session_data')
app.config['SESSION_PERMANENT'] = False

Session(app)

@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# SocketIO Setup
socketio = SocketIO(app, manage_session=False, cors_allowed_origins="*")

# --- Globale Variablen ---
players = {}
answers = []
ready_players = set()
categories = []
used_categories = set()
game_started = False
current_players = 0
max_players = None
current_category = None
max_rounds = 10
current_round = 1
points = {}
game_id = str(int(time.time()))
game_phase = "answering"  # "answering", "results", "ready"
correct_players = set()   # ✅ Spieler, die „Richtig“ aktiv haben

STATE_FILE = os.path.join(app.root_path, "game_state.json")

# --- Hilfsfunktionen ---
def load_categories():
    path = os.path.join(app.root_path, 'static', 'categories.txt')
    with open(path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def get_new_category():
    global categories, used_categories
    if len(used_categories) == len(categories):
        used_categories.clear()
    remaining = [c for c in categories if c not in used_categories]
    new_cat = random.choice(remaining)
    used_categories.add(new_cat)
    return new_cat

def save_state():
    """Speichert aktuellen Spielzustand"""
    data = {
        "game_id": game_id,
        "current_round": current_round,
        "max_rounds": max_rounds,
        "used_categories": list(used_categories),
        "current_category": current_category,
        "points": points,
        "game_phase": game_phase,
        "answers": answers if game_phase == "results" else [],
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print("💾 Zustand gespeichert (Phase:", game_phase, ")")

def reset_game():
    """Setzt den gesamten Spielzustand zurück"""
    global players, answers, ready_players, used_categories
    global current_players, current_category, game_started, max_players
    global current_round, points, game_id, game_phase, correct_players

    players.clear()
    answers.clear()
    ready_players.clear()
    used_categories.clear()
    current_players = 0
    current_category = None
    max_players = None
    game_started = False
    current_round = 1
    points = {}
    game_phase = "answering"
    correct_players.clear()
    game_id = str(int(time.time()))

    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)

    print("🔄 Spielzustand vollständig zurückgesetzt (neue game_id:", game_id, ")")
    socketio.emit('force_game_reset')

def load_state():
    """Lädt gespeicherten Zustand (nicht mehr automatisch bei Start)"""
    if not os.path.exists(STATE_FILE):
        return
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    print("🔁 Gespeicherter Zustand geladen:", data)

categories = load_categories()

# --- Socket Events ---
@socketio.on('connect')
def on_connect():
    emit('server_status', {
        'game_id': game_id,
        'game_started': game_started,
        'current_players': len(players),
        'max_players': max_players or 0,
    })

@socketio.on('set_players')
def set_players(data):
    global max_players, game_started, max_rounds
    global current_round, used_categories, game_phase, points, correct_players

    # 🧼 Reset, falls vorherige Daten noch gespeichert waren
    current_round = 1
    used_categories.clear()
    game_phase = "answering"
    points.clear()
    correct_players.clear()
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        print("🧹 Alter Spielstand gelöscht – neues Spiel startet bei Runde 1.")

    # 🚫 Falls schon ein anderes Spiel läuft
    if game_started:
        emit('set_players_ack', {'ok': False, 'reason': 'already_started'})
        print("⚠️ Ein weiterer Spieler wollte ein neues Spiel starten – abgelehnt.")
        return

    # 🎮 Neues Spiel initialisieren
    max_players = int(data['players'])
    max_rounds = int(data.get('rounds', 10))
    game_started = True

    # ✅ Host bestätigen
    emit('set_players_ack', {'ok': True})
    socketio.emit('game_started_notice', include_self=False)
    print(f"🎮 Neues Spiel gestartet mit {max_players} Spielern und {max_rounds} Runden (Runde 1).")

@socketio.on('join_game')
def join_game(data):
    global current_players, players, game_started
    name = data.get('name')
    reconnect_sid = data.get('reconnect_sid')
    sid = flask_request.sid

    if reconnect_sid and reconnect_sid in players:
        players[sid] = players.pop(reconnect_sid)
        print(f"🔁 {players[sid]['name']} reconnectet (neue SID {sid})")
        emit('sync_state', {
            'round': current_round,
            'total_rounds': max_rounds,
            'category': current_category,
            'points': points,
            'phase': game_phase,
            'answers': answers if game_phase == "results" else []
        }, room=sid)
        return

    if max_players is None:
        emit('force_rejoin')
        return

    if current_players >= max_players:
        emit('game_full')
        return

    current_players += 1
    player_id = current_players
    player_name = name or f'Spieler{player_id}'
    players[sid] = {'id': player_id, 'name': player_name, 'answer': None}
    points[player_name] = points.get(player_name, 0)

    socketio.emit('player_count', {
        'current_players': current_players,
        'max_players': max_players,
        'names': [p['name'] for p in players.values()]
    })

    if len(players) == max_players:
        print("🚀 Alle Spieler da – Spiel startet!")
        socketio.emit('start_game')
        save_state()

@socketio.on('submit_answer')
def submit_answer(data):
    global game_phase
    sid = flask_request.sid
    if sid not in players:
        emit('force_rejoin')
        return

    if game_phase != "answering":
        emit('info', {'msg': 'Antwortphase bereits beendet!'})
        return

    answer = data['answer']
    player = players[sid]
    player['answer'] = answer
    answers.append({'name': player['name'], 'answer': answer})
    print(f"📝 Antwort von {player['name']}: {answer}")

    if all(p['answer'] for p in players.values()):
        game_phase = "results"
        print("✅ Alle Antworten abgegeben → Ergebnisphase startet.")
        socketio.emit('all_answers_submitted', {'answers': answers})
        socketio.emit('ready_phase_start')
        save_state()

# ✅ „Richtig“-Button (toggle)
@socketio.on('player_correct')
def handle_player_correct():
    """Spieler toggelt den 'Richtig'-Status für die aktuelle Runde."""
    global correct_players
    sid = flask_request.sid
    if sid not in players:
        return

    name = players[sid]['name']

    if name in correct_players:
        correct_players.remove(name)
        print(f"❌ {name} hat 'Richtig' wieder deaktiviert.")
    else:
        correct_players.add(name)
        print(f"✅ {name} hat 'Richtig' aktiviert.")

    # Optional: an Clients senden, wer „Richtig“ aktiv hat
    socketio.emit('correct_count', {'names': list(correct_players)})

@socketio.on('player_ready')
def handle_player_ready():
    global ready_players, current_category, current_round, game_phase, correct_players, points

    sid = flask_request.sid
    if sid not in players:
        return

    ready_players.add(sid)
    socketio.emit('ready_count', {
        'ready': len(ready_players),
        'total': len(players),
        'names': [players[s]['name'] for s in ready_players]
    })

    # Wenn alle bereit sind → prüfen ob alle "Richtig" gedrückt haben
    if len(ready_players) == len(players):
        if len(correct_players) == len(players):  # ✅ nur wenn ALLE "Richtig" gedrückt haben
            for name in correct_players:
                if name in points:
                    points[name] += 1
                    print(f"🏅 +1 Punkt für {name} (neu: {points[name]})")
            socketio.emit('update_points', {'points': points})
        else:
            print("⚠️ Nicht alle Spieler haben 'Richtig' gedrückt – keine Punkte vergeben.")

        # --- Nächste Runde oder Spielende ---
        for p in players.values():
            p['answer'] = None
        answers.clear()

        if current_round >= max_rounds:
            print("🏁 Spielende erreicht.")
            socketio.emit('game_over', {'points': points})
            reset_game()
            return

        current_round += 1
        current_category = get_new_category()
        ready_players.clear()
        correct_players.clear()
        game_phase = "answering"

        socketio.emit('new_category', {
            'category': current_category,
            'round': current_round,
            'total_rounds': max_rounds
        })
        save_state()

@socketio.on('disconnect')
def on_disconnect():
    sid = flask_request.sid
    def cleanup():
        socketio.sleep(2)
        if sid in players:
            name = players[sid]['name']
            del players[sid]
            if name in correct_players:
                correct_players.discard(name)
            remaining = len(players)
            print(f"❌ {name} hat das Spiel verlassen. ({remaining} verbleibend)")
            if remaining > 0:
                socketio.emit('game_aborted', {'reason': f"{name} hat das Spiel verlassen. Bitte starte ein neues Spiel."})
            reset_game()
    socketio.start_background_task(cleanup)

# --- Routen ---
@app.route('/')
def index():
    if game_started and current_players > 0:
        return redirect(url_for('join'))
    if max_players and current_players >= max_players:
        return redirect(url_for('full'))
    return render_template('index.html', game_id=game_id)

@app.route('/join')
def join():
    return render_template('join.html', game_id=game_id)

@app.route('/play')
def play():
    global current_category
    if current_category is None:
        current_category = get_new_category()
    return render_template('play.html', category=current_category, game_id=game_id)

@app.route('/full')
def full():
    return render_template('full.html')

if __name__ == '__main__':
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        print("🧹 Alter Spielstand gelöscht (Serverneustart).")
    reset_game()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)