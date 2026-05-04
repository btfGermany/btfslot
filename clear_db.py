import sqlite3

def delete_name_from_all_tables(db_path, name_to_delete):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Alle Tabellennamen holen
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    for (table,) in tables:
        try:
            # Prüfen, ob die Tabelle eine Spalte mit dem Namen 'name' enthält
            cursor.execute(f"PRAGMA table_info({table})")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]

            if 'name' in column_names:
                # Löschen, wenn 'name'-Spalte vorhanden ist
                cursor.execute(f"DELETE FROM {table} WHERE name = ?", (name_to_delete,))
                print(f"Einträge mit Name '{name_to_delete}' aus Tabelle '{table}' gelöscht.")
        except Exception as e:
            print(f"Fehler bei Tabelle {table}: {e}")

    conn.commit()
    conn.close()

# Beispiel-Aufruf
delete_name_from_all_tables("btf-pre.db", "Test")
