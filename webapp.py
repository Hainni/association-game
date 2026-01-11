import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, redirect, url_for, request as flask_request
from flask_session import Session
from flask_socketio import SocketIO, emit
import os, random, time, json, logging
# import os, random, time, json, logging # `json` wird für STATE_FILE nicht mehr benötigt

logging.getLogger('eventlet.wsgi').setLevel(logging.ERROR)

app = Flask(__name__)
app.secret_key = 'super_secret_key_123'  # später als ENV setzen

# --- Session-Konfiguration ---
app.config['SESSION_TYPE'] = 'filesystem'
# ACHTUNG: Auch die Session-Daten werden in eine lokale Datei geschrieben.
# Für Render ist es **stark empfohlen**, dies auf 'redis' oder 'memcached' zu ändern,
# oder die Session komplett zu deaktivieren, da das lokale Filesystem bei Render flüchtig ist.
# Fürs Erste belassen wir es, aber es ist ein potenzieller zukünftiger Fehler.
app.config['SESSION_FILE_DIR'] = os.path.join(app.root_path, 'flask_session_data') 
app.config['SESSION_PERMANENT'] = False
Session(app)

@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# --- SocketIO Setup (Render-kompatibel) ---
socketio = SocketIO(
    app,
    async_mode="eventlet",
    manage_session=False,
    cors_allowed_origins="*"
)

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
game_phase = "answering"
correct_players = set()

# STATE_FILE = os.path.join(app.root_path, "game_state.json") ### ENTFERNT ###

# --- Hilfsfunktionen ---
def load_categories():
    path = os.path.join(app.root_path, 'static', 'categories.txt')
    with open(path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def get_new_category():
    if len(used_categories) == len(categories):
        used_categories.clear()
    remaining = [c for c in categories if c not in used_categories]
    new_cat = random.choice(remaining)
    used_categories.add(new_cat)
    return new_cat

# def save_state(): ### ENTFERNT ###
#     data = {
#         "game_id": game_id,
#         "current_round": current_round,
#         "max_rounds": max_rounds,
#         "used_categories": list(used_categories),
#         "current_category": current_category,
#         "points": points,
#         "game_phase": game_phase,
#         "answers": answers if game_phase == "results" else [],
#     }
#     with open(STATE_FILE, "w", encoding="utf-8") as f:
#         json.dump(data, f) ### ENTFERNT ###

def reset_game():
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

    # if os.path.exists(STATE_FILE): ### ENTFERNT ###
    #     os.remove(STATE_FILE) ### ENTFERNT ###

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
    global max_players, game_started, max_rounds
    global current_round, used_categories, game_phase, points, correct_players

    current_round = 1
    used_categories.clear()
    game_phase = "answering"
    points.clear()
    correct_players.clear()

    if game_started:
        emit('set_players_ack', {'ok': False, 'reason': 'already_started'})
        return

    max_players = int(data['players'])
    max_rounds = int(data.get('rounds', 10))
    game_started = True

    emit('set_players_ack', {'ok': True})
    socketio.emit('game_started_notice', include_self=False)

# webapp.py (Auszug, Zeile 139)

@socketio.on('join_game')
def join_game(data):
    global current_players
    name = data.get('name')
    sid = flask_request.sid

    # --- Reconnect/Wiederbeitritt prüfen ---
    old_sid = None
    player_found = False
    
    # Durch alle aktuellen Spieler iterieren, um den Namen zu finden
    for player_sid, player_data in list(players.items()): # list() erstellen, da wir das dict ändern könnten
        if player_data['name'] == name:
            old_sid = player_sid
            player_found = True
            break

    if player_found:
        # Fall 1: Reconnect erkannt
        if old_sid and old_sid != sid:
            # Alte SID löschen, Spieler-Daten auf neue SID übertragen
            player_data = players.pop(old_sid)
            players[sid] = player_data
            print(f"Reconnect erfolgreich: Spieler {name} hat neue SID: {sid}")
        else:
             # Spieler ist bereits mit dieser SID bekannt
             pass 

    # Fall 2: Neuer Spieler tritt bei
    elif max_players is None or len(players) >= max_players:
        emit('game_full')
        return

    else:
        # Neuer Spieler tritt bei
        current_players += 1
        players[sid] = {'id': current_players, 'name': name, 'answer': None}
        points[name] = points.get(name, 0)
        print(f"Neuer Spieler: {name} mit SID: {sid}")

    # --- Status senden ---
    socketio.emit('player_count', {
        'current_players': len(players), 
        'max_players': max_players,
        'names': [p['name'] for p in players.values()]
    })

    if len(players) == max_players:
        socketio.emit('start_game')

@socketio.on('submit_answer')
def submit_answer(data):
    global game_phase
    sid = flask_request.sid

    if game_phase != "answering":
        return

    players[sid]['answer'] = data['answer']
    answers.append({'name': players[sid]['name'], 'answer': data['answer']})

    if all(p['answer'] for p in players.values()):
        game_phase = "results"
        socketio.emit('all_answers_submitted', {'answers': answers})
        socketio.emit('ready_phase_start')
        # save_state() ### ENTFERNT ###

@socketio.on('player_ready')
def handle_player_ready():
    global current_round, current_category, game_phase

    ready_players.add(flask_request.sid)

    if len(ready_players) == len(players):
        answers.clear()
        ready_players.clear()

        if current_round >= max_rounds:
            socketio.emit('game_over', {'points': points})
            reset_game()
            return

        current_round += 1
        current_category = get_new_category()
        game_phase = "answering"

        socketio.emit('new_category', {
            'category': current_category,
            'round': current_round,
            'total_rounds': max_rounds
        })
        # save_state() ### ENTFERNT ###

# --- Routen ---
@app.route('/')
def index():
    return render_template('index.html', game_id=game_id)

@app.route('/join')
def join():
    return render_template('join.html', game_id=game_id)

@app.route('/full')
def full():
    return render_template('full.html', game_id=game_id)

@app.route('/play')
def play():
    global current_category
    if current_category is None:
        current_category = get_new_category()
    return render_template('play.html', category=current_category, game_id=game_id)

# --- NUR LOKAL ---
if __name__ == '__main__':
    socketio.run(app, debug=True)
