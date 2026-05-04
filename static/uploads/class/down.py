from PIL import Image
import os

# Alle Dateien im aktuellen Verzeichnis auflisten
for filename in os.listdir("."):
    if filename.lower().endswith(".png"):
        try:
            # Bild öffnen
            with Image.open(filename) as img:
                # Neue Größe berechnen (50 % der Originalgröße)
                new_size = (img.width // 4, img.height // 4)

                # Bild skalieren mit LANCZOS (hochwertiges Downscaling)
                img_resized = img.resize(new_size, Image.Resampling.LANCZOS)

                # Überschreiben oder unter neuem Namen speichern
                img_resized.save(filename, optimize=True)

                print(f"Komprimiert: {filename}")
        except Exception as e:
            print(f"Fehler bei {filename}: {e}")
