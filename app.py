from flask import Flask, render_template, redirect, url_for, request as flask_request
from flask_session import Session
from flask_socketio import SocketIO, emit, join_room
import os, random
import time
import logging
logging.getLogger('eventlet.wsgi').setLevel(logging.ERROR)

app = Flask(__name__)
app.secret_key = 'super_secret_key_123'

# Session-Setup (nicht mehr kritisch, aber kann bleiben)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(app.root_path, 'flask_session_data')
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = False
app.config['SESSION_COOKIE_DOMAIN'] = None
app.config['SESSION_COOKIE_PATH'] = '/'

Session(app)

@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# SocketIO Setup
socketio = SocketIO(app, manage_session=False, cors_allowed_origins="*")

# Globale Variablen
players = {}          # { sid: {'id': 1, 'name': 'Alice', 'answer': 'Katze'} }
answers = []
max_players = 2
current_players = 0
current_category = None
game_started = False
categories = []
used_categories = set()
ready_players = set()
game_id = str(int(time.time()))

### HILFSFUNKTIONEN ###
def load_categories():
    path = os.path.join(app.root_path, 'static', 'categories.txt')
    with open(path, 'r', encoding='utf-8') as file:
        return [line.strip() for line in file if line.strip()]

def get_new_category():
    global categories, used_categories
    if len(used_categories) == len(categories):
        used_categories.clear()
    remaining = [c for c in categories if c not in used_categories]
    new_cat = random.choice(remaining)
    used_categories.add(new_cat)
    return new_cat

def reset_game():
    global players, answers, current_players, current_category, ready_players, used_categories, game_id, game_started
    players.clear()
    answers.clear()
    ready_players.clear()
    used_categories.clear()
    current_players = 0
    current_category = None
    game_started = False
    game_id = str(int(time.time()))
    print("🔄 Spielzustand vollständig zurückgesetzt (neue game_id:", game_id, ")")
    socketio.emit('force_game_reset') # Broadcast an alle Clients, damit sie zur Startseite gehen

categories = load_categories()

#####################
### SOCKET EVENTS ###
#####################

@socketio.on('connect')
def on_connect():
    emit('server_game_id', {'game_id': game_id})

@socketio.on('set_players')
def set_players(data):
    global max_players, game_started
    max_players = int(data['players'])
    game_started = True
    emit('player_count', {'current_players': current_players, 'max_players': max_players})


@socketio.on('join_game')
def join_game(data):
    global current_players, players, max_players, game_id
    emit('server_game_id', {'game_id': game_id})  # <-- send current id


    name = data.get('name')
    reconnect_sid = data.get('reconnect_sid')  # <- kommt vom Client
    sid = flask_request.sid

    # Prüfen, ob Spieler reconnectet
    if reconnect_sid and reconnect_sid in players:
        players[sid] = players.pop(reconnect_sid)
        print(f"🔄 Spieler {players[sid]['name']} reconnectet (neue SID {sid})")
        return


    # normaler Beitritt
    if current_players >= max_players:
        emit('game_full')
        print(f"🚫 Spiel ist voll: {name}")
        return

    current_players += 1
    player_id = current_players
    player_name = name or f'Spieler{player_id}'

    players[sid] = {'id': player_id, 'name': player_name, 'answer': None}
    print(f"🔹 Spieler {player_name} beigetreten (ID {player_id}, SID {sid})")
    print(f"🔹 Aktuelle Spieler: {current_players}/{max_players}")

    socketio.emit('player_count', {
        'current_players': current_players,
        'max_players': max_players,
        'names': [p['name'] for p in players.values()]
    })

    if len(players) == max_players:
        global game_started
        game_started = True
        print("🚀 Alle Spieler da – Spiel startet!")
        socketio.emit('start_game')


@socketio.on('submit_answer')
def handle_submit_answer(data):
    sid = flask_request.sid

    # Prüfen, ob Spieler bekannt
    if sid not in players:
        emit('force_rejoin')  # Client soll neu laden
        print(f"⚠️ Antwort empfangen, aber unbekannte SID: {sid}")
        return

    answer = data['answer']
    player = players[sid]
    player['answer'] = answer
    answers.append({'name': player['name'], 'answer': answer})
    print(f"📝 Antwort von {player['name']}: {answer}")

    if all(p['answer'] is not None for p in players.values()):
        print("✅ Alle Antworten abgegeben.")
        socketio.emit('all_answers_submitted', {'answers': answers})
        socketio.emit('ready_phase_start')


@socketio.on('player_ready')
def handle_player_ready():
    global ready_players, current_players, current_category

    sid = flask_request.sid
    if sid not in players:
        print("⚠️ Ready gesendet, aber SID nicht registriert.")
        return

    ready_players.add(sid)
    player_name = players[sid]['name']
    print(f"🟢 {player_name} ist bereit ({len(ready_players)}/{current_players})")

    socketio.emit('ready_count', {
        'ready': len(ready_players),
        'total': current_players,
        'names': [players[s]['name'] for s in ready_players]
    })

    if len(ready_players) == len(players):
        # Antworten zurücksetzen
        for p in players.values():
            p['answer'] = None
        answers.clear()

        # neue Kategorie
        current_category = get_new_category()
        print(f"🚀 Neue Kategorie: {current_category}")

        ready_players.clear()
        socketio.emit('new_category', {'category': current_category})

@socketio.on('disconnect')
def on_disconnect():
    sid = flask_request.sid

    def remove_if_still_gone():
        socketio.sleep(1)
        global current_players

        if sid in players:
            name = players[sid]['name']
            del players[sid]
            current_players = len(players)

            print(f"❌ Spieler {name} hat das Spiel verlassen. ({current_players} verbleibend)")

            socketio.emit('player_count', {
                'current_players': current_players,
                'max_players': max_players,
                'names': [p['name'] for p in players.values()]
            })

            # Wenn Spieler fehlen → Spiel abbrechen und zurücksetzen
            if current_players < max_players and current_players > 0:
                print("⚠️ Ein Spieler hat das Spiel verlassen – Spiel wird zurückgesetzt.")
                # 🔹 ZUERST allen sagen, dass jemand raus ist
                socketio.emit('game_aborted', {'reason': f'{name} hat das Spiel verlassen.'})
                socketio.sleep(0.5)
                # 🔹 Dann Reset durchführen (neue game_id)
                reset_game()

            elif current_players == 0:
                print("🔁 Alle Spieler weg – Spiel zurückgesetzt.")
                reset_game()

    socketio.start_background_task(remove_if_still_gone)



################
### ROUTINGS ###
################
@app.route('/')
def index():
    global game_started, current_players, max_players, game_id
    if game_started:
        return redirect(url_for('join'))
    if current_players >= max_players:
        return redirect(url_for('full'))
    return render_template('index.html', game_id=game_id)

@app.route('/join')
def join():
    return render_template('join.html', game_id=game_id)

@app.route('/play')
def play():
    global current_category, game_id
    if current_category is None:
        current_category = get_new_category()
        socketio.emit('category_selected', {'category': current_category})
    return render_template('play.html', category=current_category, game_id=game_id)

@app.route('/full')
def full():
    return render_template('full.html')


if __name__ == '__main__':
    import eventlet
    import eventlet.wsgi
    reset_game()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)