from flask import Flask, render_template, request, jsonify
import openai
import sqlite3
import logging
import os

# Configura il logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)

# Funzione per connettersi al database
def get_db_connection():
    conn = sqlite3.connect('chat.db')
    conn.row_factory = sqlite3.Row
    return conn

# Crea la tabella delle conversazioni se non esiste
conn = get_db_connection()
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS conversazioni (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
conn.commit()
conn.close()

# Funzione per generare una risposta da GPT-4
def genera_risposta(conversazione, api_key):
    try:
        openai.api_key = api_key  # Usa la chiave API fornita dall'utente
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=conversazione
        )
        logging.debug(f"Response from OpenAI: {response}")
        return response.choices[0].message['content']
    except Exception as e:
        logging.error(f"Error generating response: {str(e)}")
        return f"Si è verificato un errore: {str(e)}"

@app.route('/')
def home():
    return render_template('index.html')

# Route per la chat
@app.route('/chat', methods=['POST'])
def chat():
    user_input = request.json.get('message')
    api_key = request.headers.get('Authorization').replace('Bearer ', '')  # Riceve l'API Key dall'header
    if not user_input:
        return jsonify({'error': 'Messaggio vuoto'}), 400

    # Recupera le chat precedenti dal database
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT chat FROM conversazioni ORDER BY id ASC")
    previous_chats = c.fetchall()
    conn.close()

    # Crea il contesto combinando tutte le chat precedenti
    combined_chats = "\n".join([chat['chat'] for chat in previous_chats])

    conversazione = [
        {"role": "system", "content": "Sei un assistente che aiuta a gestire appuntamenti e impegni."},
        {"role": "user", "content": f"Contesto delle conversazioni precedenti: {combined_chats}"},
        {"role": "user", "content": user_input}
    ]

    risposta = genera_risposta(conversazione, api_key)
    if risposta.startswith("Si è verificato un errore"):
        return jsonify({'error': risposta}), 500

    # Salva la conversazione nel database
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO conversazioni (chat, created_at) VALUES (?, datetime('now'))",
              (f"Utente: {user_input}\nAI: {risposta}",))
    conn.commit()
    conn.close()

    return jsonify({'response': risposta})

# Avvia l'app su Replit usando la porta 8080
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))  # Porta standard su Replit
    app.run(host='0.0.0.0', port=port)
