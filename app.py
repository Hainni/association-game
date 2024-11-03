from flask import Flask, request, redirect, render_template, session
from flask_socketio import SocketIO, emit
import random

app = Flask(__name__)
app.secret_key = 'dein_geheimer_schlüssel'
socketio = SocketIO(app)

# Globale Variablen für Spielstatus und Teilnehmer
max_players = 0
current_players = 0
game_started = False

@app.route('/')
def home():
    global game_started, max_players, current_players
    # Wenn das Spiel gestartet wurde und die maximale Spielerzahl nicht erreicht ist, zur Join-Seite weiterleiten
    if game_started:
        if current_players < max_players:
            return redirect('/join')
        else:
            return redirect('/full')  # Weiterleitung zur "Spiel voll"-Seite, wenn das Spiel voll ist
    return render_template('index.html')  # Ansonsten zum Startbildschirm

@socketio.on('set_players')
def set_players(data):
    global max_players, game_started
    max_players = int(data['players'])
    game_started = True
    emit('player_count', {'current_players': current_players, 'max_players': max_players}, broadcast=True)

def load_categories():
    with open('static/categories.txt', 'r', encoding='utf-8') as file:
        categories = [line.strip() for line in file.readlines()]
    return categories

@app.route('/play')
def play():
    categories = load_categories()
    random_category = random.choice(categories)  # Wähle eine zufällige Kategorie
    return render_template('play.html', category=random_category)

@app.route('/join')
def join():
    global current_players, max_players
    # Überprüfen, ob die maximale Teilnehmerzahl erreicht ist
    if current_players < max_players:
        current_players += 1
        socketio.emit('player_count', {'current_players': current_players, 'max_players': max_players}, to='/')
        return render_template('join.html')
    else:
        return redirect('/full')  # Falls voll, weiterleiten zur "Spiel voll"-Seite

@socketio.on('join_game')
def join_game():
    # Sende die aktuelle Teilnehmerzahl an alle Clients
    emit('player_count', {'current_players': current_players, 'max_players': max_players}, broadcast=True)

@socketio.on('submit_answer')
def handle_answer(data):
    answer = data['answer']
    # Hier könntest du die Antwort verarbeiten oder speichern
    emit('new_answer', {'answer': answer}, broadcast=True)  # Sende die Antwort an alle Clients

@app.route('/full')
def full():
    return "Das Spiel ist bereits voll. Bitte versuchen Sie es später erneut."

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
