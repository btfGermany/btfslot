#!/usr/bin/env python3
"""
Reset-Script für die BTF Slot Datenbank.

Dieses Script:
1. Löscht die gesamte Datenbank
2. Erstellt die Datenbank neu mit allen Tabellen
3. Erstellt den Admin-Benutzer aus config.json
"""

import os
import sqlite3
import random
import string
import json
from werkzeug.security import generate_password_hash

DATABASE_FILE = 'btf-pre.db'
CONFIG_FILE = 'config.json'

def load_config():
    """Lädt die Konfiguration"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

def save_config(config):
    """Speichert die Konfiguration"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def get_db_connection():
    """Erstellt eine Datenbankverbindung"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def reset_database():
    """Löscht und erstellt die Datenbank neu"""
    
    # 1. Datenbank löschen falls vorhanden
    if os.path.exists(DATABASE_FILE):
        os.remove(DATABASE_FILE)
        print(f"✓ Datenbank '{DATABASE_FILE}' gelöscht")
    
    # 2. Datenbank neu erstellen
    conn = get_db_connection()
    
    # Schema ausführen
    with open('schema.sql', 'r') as f:
        conn.executescript(f.read())
    
    print(f"✓ Datenbank '{DATABASE_FILE}' erstellt")
    
    # 3. Rollen und Berechtigungen erstellen
    conn.execute('INSERT INTO user_roles (name, description) VALUES (?, ?)', ('admin', 'Vollzugriff'))
    conn.execute('INSERT INTO user_roles (name, description) VALUES (?, ?)', ('manager', 'Bestellverwaltung'))
    conn.execute('INSERT INTO user_roles (name, description) VALUES (?, ?)', ('terminal', 'Terminal'))
    print("✓ Rollen erstellt")
    
    permissions = [
        ('manage_users', 'Benutzer verwalten'),
        ('manage_products', 'Produkte verwalten'),
        ('manage_orders', 'Bestellungen verwalten'),
        ('access_terminal', 'Terminal'),
        ('view_reports', 'Berichte'),
        ('manage_system', 'System')
    ]
    conn.executemany('INSERT INTO permissions (name, description) VALUES (?, ?)', permissions)
    print("✓ Berechtigungen erstellt")
    
    # Admin alle Berechtigungen zuweisen
    perms = conn.execute('SELECT id FROM permissions').fetchall()
    admin_role = conn.execute('SELECT id FROM user_roles WHERE name = "admin"').fetchone()
    for p in perms:
        conn.execute('INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)', 
                    (admin_role['id'], p['id']))
    
    # Manager Berechtigungen zuweisen
    manager_role = conn.execute('SELECT id FROM user_roles WHERE name = "manager"').fetchone()
    for pn in ['manage_products', 'manage_orders', 'view_reports']:
        p = conn.execute('SELECT id FROM permissions WHERE name = ?', (pn,)).fetchone()
        if p:
            conn.execute('INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)', 
                        (manager_role['id'], p['id']))
    
    # Terminal Berechtigungen zuweisen
    term_role = conn.execute('SELECT id FROM user_roles WHERE name = "terminal"').fetchone()
    p = conn.execute('SELECT id FROM permissions WHERE name = "access_terminal"').fetchone()
    if p:
        conn.execute('INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)', 
                    (term_role['id'], p['id']))
    
    print("✓ Rollen-Berechtigungen zugewiesen")
    
    # 4. Admin-Benutzer erstellen
    config = load_config()
    
    if config and 'admin' in config:
        username = config['admin']['username']
        password = config['admin']['password']
    else:
        # Neue Zugangsdaten erstellen
        username = 'admin'
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        config = {'admin': {'username': username, 'password': password}}
        save_config(config)
        print(f"✓ Admin-Zugangsdaten in '{CONFIG_FILE}' gespeichert")
    
    # Admin in Datenbank erstellen
    password_hash = generate_password_hash(password)
    conn.execute(
        'INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
        (username, password_hash, 'admin')
    )
    
    conn.commit()
    conn.close()
    
    print(f"\n{'='*50}")
    print("DATENBANK ERFOLGREICH ZURÜCKGESETZT")
    print(f"{'='*50}")
    print(f"Admin-Benutzer: {username}")
    print(f"Passwort: {password}")
    print(f"(Passwort gespeichert in {CONFIG_FILE})")
    print(f"{'='*50}")

if __name__ == '__main__':
    print("BTF Slot Datenbank Reset")
    print("="*50)
    
    confirm = input("Möchten Sie die Datenbank wirklich zurücksetzen? (ja/nein): ")
    
    if confirm.lower() in ['ja', 'j', 'yes', 'y']:
        reset_database()
    else:
        print("Abgebrochen.")