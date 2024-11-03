from flask import Flask, request, redirect, render_template, session
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.secret_key = 'dein_geheimer_schlüssel'
socketio = SocketIO(app)

max_players = 0
current_players = 0
game_started = False

@app.route('/')
def home():
    return render_template('index.html')

@socketio.on('set_players')
def set_players(data):
    global max_players, game_started
    max_players = int(data['players'])
    game_started = True
    emit('player_count', {'current_players': current_players, 'max_players': max_players}, broadcast=True)

@app.route('/play')
def play():
    return render_template('play.html')

@app.route('/join')
def join():
    global current_players
    if current_players < max_players:
        current_players += 1
        return render_template('join.html')
    else:
        return redirect('/full')

@socketio.on('join_game')
def join_game():
    emit('player_count', {'current_players': current_players, 'max_players': max_players}, broadcast=True)

@socketio.on('submit_answer')
def handle_answer(data):
    answer = data['answer']
    # Hier kannst du die Antwort verarbeiten
    emit('new_answer', {'answer': answer}, broadcast=True)  # Sende die Antwort an alle Clients

@app.route('/full')
def full():
    return "Das Spiel ist bereits voll. Bitte versuchen Sie es später erneut."

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
