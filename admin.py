import sqlite3
import json
import os
from werkzeug.security import generate_password_hash

CONFIG_FILE = 'config.json'
DATABASE_FILE = 'btf-pre.db'  # Passe den Datenbanknamen an, falls nötig

def get_db_connection():
    """Stellt eine Verbindung zur Datenbank her"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def load_config():
    """Lädt die Konfigurationsdatei"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Fehler: Die Datei {CONFIG_FILE} enthält ungültiges JSON.")
            return None
    else:
        print(f"Fehler: Die Datei {CONFIG_FILE} existiert nicht.")
        return None

def create_admin(overwrite_existing=True):
    """Erstellt oder überschreibt einen Admin-Benutzer basierend auf config.json"""
    conn = get_db_connection()

    # Prüfe ob die Users-Tabelle existiert
    table_exists = conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='users'
    """).fetchone()

    if not table_exists:
        print("Die Users-Tabelle existiert nicht. Bitte initialisiere die Datenbank zuerst.")
        conn.close()
        return

    # Lade Admin-Zugangsdaten aus config.json
    config = load_config()

    if config and 'admin' in config:
        username = config['admin']['username']
        password = config['admin']['password']
        password_hash = generate_password_hash(password)

        # Prüfe ob Admin existiert
        existing_admin = conn.execute('SELECT * FROM users WHERE role = "admin"').fetchone()

        if existing_admin:
            if overwrite_existing:
                conn.execute(
                    'UPDATE users SET username = ?, password = ? WHERE role = "admin"',
                    (username, password_hash)
                )
                print(f"Admin-Benutzer wurde überschrieben. Neuer Benutzername: {username}")
            else:
                print(f"Admin-Benutzer existiert bereits mit Benutzername: {existing_admin['username']}")
                conn.close()
                return
        else:
            conn.execute(
                'INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
                (username, password_hash, 'admin')
            )
            print(f"Admin-Benutzer erfolgreich erstellt! Benutzername: {username}")

        conn.commit()
    else:
        print("Fehler: Keine Admin-Zugangsdaten in config.json gefunden. Bitte füge sie hinzu und starte das Skript erneut.")

    conn.close()

if __name__ == "__main__":
    print("Admin-Benutzer wird erstellt...")
    create_admin()