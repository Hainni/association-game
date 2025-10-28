from flask import Flask, render_template, redirect, url_for, request as flask_request
from flask_session import Session
from flask_socketio import SocketIO, emit
import os, random, time, json, logging

logging.getLogger('eventlet.wsgi').setLevel(logging.ERROR)

app = Flask(__name__)
app.secret_key = 'super_secret_key_123'

# Session-Setup
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

# SocketIO
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
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print("💾 Zustand gespeichert.")

def load_state():
    """Lädt gespeicherten Zustand"""
    global game_id, current_round, max_rounds, used_categories, current_category, points
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        game_id = data.get("game_id", game_id)
        current_round = data.get("current_round", 1)
        max_rounds = data.get("max_rounds", 10)
        used_categories = set(data.get("used_categories", []))
        current_category = data.get("current_category", None)
        points = data.get("points", {})
        print("🔁 Gespeicherter Zustand geladen:", data)

def reset_game():
    """Setzt den gesamten Spielzustand zurück"""
    global players, answers, ready_players, used_categories
    global current_players, current_category, game_started, max_players
    global current_round, points, game_id

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
    game_id = str(int(time.time()))

    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)

    print("🔄 Spielzustand vollständig zurückgesetzt (neue game_id:", game_id, ")")
    socketio.emit('force_game_reset')

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
    global max_players, game_started
    if game_started:
        emit('set_players_ack', {'ok': False, 'reason': 'already_started'})
        return

    max_players = int(data['players'])
    game_started = True
    emit('set_players_ack', {'ok': True})
    socketio.emit('game_started_notice', include_self=False)
    print(f"🎮 Neues Spiel gestartet mit {max_players} Spielern.")

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
            'points': points
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
    sid = flask_request.sid
    if sid not in players:
        emit('force_rejoin')
        return

    answer = data['answer']
    player = players[sid]
    player['answer'] = answer
    answers.append({'name': player['name'], 'answer': answer})

    if all(p['answer'] for p in players.values()):
        socketio.emit('all_answers_submitted', {'answers': answers})
        socketio.emit('ready_phase_start')

@socketio.on('player_ready')
def handle_player_ready():
    global ready_players, current_category, current_round

    sid = flask_request.sid
    if sid not in players:
        return

    ready_players.add(sid)
    socketio.emit('ready_count', {
        'ready': len(ready_players),
        'total': len(players),
        'names': [players[s]['name'] for s in ready_players]
    })

    if len(ready_players) == len(players):
        for p in players.values():
            p['answer'] = None
        answers.clear()

        current_category = get_new_category()
        if current_round < max_rounds:
            current_round += 1

        ready_players.clear()

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
            remaining = len(players)
            print(f"❌ {name} hat das Spiel verlassen. ({remaining} verbleibend)")
            if remaining > 0:
                socketio.emit('game_aborted', {'reason': f"{name} hat das Spiel verlassen. Bitte starte ein neues Spiel."})
            reset_game()
    socketio.start_background_task(cleanup)

# --- Routen ---
@app.route('/')
def index():
    global game_started, current_players, max_players, game_id
    print(f"[DEBUG] game_started={game_started}, current_players={current_players}, max_players={max_players}")

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
    import eventlet
    load_state()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
