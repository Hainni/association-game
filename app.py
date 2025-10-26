from flask import Flask, render_template, redirect, url_for, session
from flask_socketio import SocketIO, emit
import random

app = Flask(__name__)
app.secret_key = 'your_secret_key'
socketio = SocketIO(app)

# Initialisiere globale Variablen für die Spieler und Antworten
players = {}
answers = []
max_players = 3
current_players = 0
current_category = None
global categories

### HILFSUNKTIONEN ###
def load_categories():
    """Lädt Kategorien aus einer Textdatei"""
    with open('static/categories.txt', 'r', encoding='utf-8') as file:
        categories = [line.strip() for line in file if line.strip()]
    return categories

def get_new_category():
    global categories, used_categories

    # Prüfe, ob alle Kategorien schon verwendet wurden
    if len(used_categories) == len(categories):
        used_categories.clear()

    # Finde alle Kategorien, die noch übrig sind
    remaining = [cat for cat in categories if cat not in used_categories]

    # Wähle zufällige neue Kategorie
    new_cat = random.choice(remaining)
    used_categories.add(new_cat)
    return new_cat

def reset_game():
    global players, answers, current_players, current_category
    players.clear()
    answers.clear()
    current_players = 0
    current_category = None

### ---------------------- ###

categories = load_categories()
used_categories = set()
ready_players = set()

#####################
### SOCKET EVENTS ###
#####################
@socketio.on('set_players')
def set_players(data):
    global max_players, game_started
    max_players = int(data['players'])
    game_started = True
    emit('player_count', {'current_players': current_players, 'max_players': max_players}, broadcast='/')

@socketio.on('join_game')
def join_game():
    emit('player_count', {'current_players': current_players, 'max_players': max_players}, broadcast=True)

@socketio.on('submit_answer')
def handle_submit_answer(data):
    global answers, current_players, current_category
    player_id = session.get('player_id')

    # Speichert die Antwort des Spielers, wenn dieser noch keine Antwort abgegeben hat
    if player_id not in players:
        players[player_id] = data['answer']
        answers.append(data['answer'])

    # Prüft, ob alle Spieler geantwortet haben
    if len(answers) == current_players:
        # Sendet alle Antworten an alle Clients
        socketio.emit('all_answers_submitted', {'answers': answers})

@socketio.on('player_ready')
def handle_player_ready():
    global ready_players, current_players, current_category, players, answers

    player_id = session.get('player_id')
    ready_players.add(player_id)

    # 🟢 Fortschritt an alle senden
    socketio.emit('ready_count', {
        'ready': len(ready_players),
        'total': current_players
    })

    # Wenn alle Spieler bereit sind → neue Runde starten
    if len(ready_players) == current_players:
        current_category = get_new_category()
        answers.clear()
        players.clear()
        ready_players.clear()  # Reset für nächste Runde

        socketio.emit('new_category', {'category': current_category})

################
### ROUTINGS ###
################
@app.route('/')
def index():
    global current_players
    # Wenn die maximale Anzahl an Spielern erreicht ist, zur vollen Seite weiterleiten
    if current_players >= max_players:
        return redirect(url_for('full'))
    elif current_players == 0:
        return render_template('index.html')
    else:
        return redirect(url_for('join'))

@app.route('/join')
def join():
    global current_players
    current_players += 1
    session['player_id'] = current_players

    # Broadcast an alle Clients über die aktuelle Spieleranzahl
    socketio.emit('player_count', {'current_players': current_players, 'max_players': max_players}, to='/')
    
    return render_template('join.html')

@app.route('/play')
def play():
    global current_category
    categories = load_categories()
    if current_category is None:
        # Wähle zufällig eine Kategorie
        current_category = random.choice(categories)
        # Sende die Kategorie an alle Clients
        socketio.emit('category_selected', {'category': current_category}, to='/')
    return render_template('play.html', category=current_category)

@app.route('/full')
def full():
    return render_template('full.html')


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', debug=True)
