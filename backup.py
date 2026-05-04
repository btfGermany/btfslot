import os
import zipfile
from datetime import datetime

def zip_current_folder():
    # Absoluter Pfad des aktuellen Skripts
    script_path = os.path.abspath(__file__)
    # Ordner, in dem das Skript liegt
    folder_path = os.path.dirname(script_path)
    # Name des Ordners (für ZIP-Dateinamen)
    folder_name = os.path.basename(folder_path)
    # Zeitstempel für eindeutigen Dateinamen
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    zip_filename = f"{folder_name}_{timestamp}.zip"
    zip_path = os.path.join(folder_path, zip_filename)

    # Erstelle ZIP-Datei
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                abs_file_path = os.path.join(root, file)
                # Nicht die ZIP-Datei selbst hinzufügen
                if abs_file_path == zip_path:
                    continue
                # Pfad relativ zum Wurzelordner für saubere Struktur
                relative_path = os.path.relpath(abs_file_path, folder_path)
                zipf.write(abs_file_path, relative_path)

    print(f"ZIP-Datei erstellt: {zip_path}")

if __name__ == "__main__":
    zip_current_folder()
