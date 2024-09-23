from flask import Flask, render_template, request, jsonify
# from datetime import datetime
import openai
import sqlite3
import logging
# import re
# import dateparser  # per gestire le date

# Configura il logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)

# Funzione per connettersi al database
def get_db_connection():
    conn = sqlite3.connect('chat.db')
    conn.row_factory = sqlite3.Row
    return conn

# Ricrea la tabella delle conversazioni se non esiste
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

# Route per gestire la chat con l'IA
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

# Endpoint per salvare la chat
@app.route('/save_chat', methods=['POST'])
def save_chat():
    chat_content = request.json.get('chat')
    if chat_content:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO conversazioni (chat, created_at) VALUES (?, datetime('now'))", (chat_content,))
        conn.commit()
        conn.close()
        return jsonify({'status': 'Chat salvata con successo'}), 200
    else:
        return jsonify({'error': 'Chat vuota, non salvata'}), 400

# Altri endpoint (riassunti, appuntamenti, ecc.) rimangono invariati...



# Endpoint per recuperare le chat
@app.route('/get_chats', methods=['GET'])
def get_chats():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, chat, DATE(created_at) as chat_date FROM conversazioni ORDER BY created_at DESC")
    chats = c.fetchall()
    conn.close()

    # Organizza le chat per data
    grouped_chats = {}
    for chat in chats:
        date = chat['chat_date']
        if date not in grouped_chats:
            grouped_chats[date] = []
        grouped_chats[date].append({'id': chat['id'], 'snippet': chat['chat'][:30]})  # Prendi le prime 30 lettere di ogni chat

    return jsonify(grouped_chats)



# Endpoint per generare una sintesi delle chat di oggi
@app.route('/generate_summary', methods=['GET'])
def generate_summary():
    chats = get_today_chats()
    if not chats:
        return jsonify({'error': 'Nessuna chat trovata per oggi.'}), 404

    # Combina le chat in un unico testo
    combined_chats = "\n".join(chats)
    conversazione = [{"role": "user", "content": f"Riassumi i seguenti contenuti: {combined_chats}"}]

    try:
        sintesi = genera_risposta(conversazione)
        return jsonify({'summary': sintesi})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Endpoint per trovare gli impegni
@app.route('/find_appointments', methods=['GET'])
def find_appointments():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT chat FROM conversazioni")
    chats = c.fetchall()
    conn.close()

    combined_chats = "\n".join([chat['chat'] for chat in chats])
    conversazione = [
        {"role": "user",
         "content": (
             f"Trova tutti gli appuntamenti o impegni futuri nei seguenti messaggi: {combined_chats}. "
             "Assicurati di identificare correttamente termini relativi come 'domani', 'la prossima settimana', 'domenica prossima', ecc., e convertirli in date specifiche. "
             "Ad esempio, se il testo contiene 'domani', interpretalo come la data di domani; se contiene 'domenica prossima', converti in una data che corrisponda alla prossima domenica. "
             "Elenca gli impegni nel formato: 'Giorno Mese Anno - Ora - Descrizione dell'impegno'. "
             "Esempi di output: "
             "'Mer 18 Set 2024 - ore 10:00 - Telefonare a Francesca', "
             "'Gio 19 Set 2024 - ore 09:00 - Tagliare l'erba'. "
             "Se non trovi una data specifica, prova a dedurre comunque l'impegno in base al contesto."
         )}
    ]

    try:
        risposta = genera_risposta(conversazione)

        # Parsing manuale dei risultati per estrarre date e contenuti
        parsed_dates = []
        lines = risposta.split('\n')
        unique_appointments = set()  # Usa un set per evitare duplicati

        # Analisi dei risultati
        for line in lines:
            if line.strip():  # Verifica che la linea non sia vuota
                unique_appointments.add(line.strip())

        if not unique_appointments:
            return jsonify({'appointments': 'Nessun impegno trovato.'})

        return jsonify({'appointments': list(unique_appointments)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_chat_content/<int:chat_id>', methods=['GET'])
def get_chat_content(chat_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT chat FROM conversazioni WHERE id = ?", (chat_id,))
    chat = c.fetchone()
    conn.close()

    if chat:
        return jsonify({'chat_content': chat['chat']})
    else:
        return jsonify({'error': 'Chat non trovata'}), 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
