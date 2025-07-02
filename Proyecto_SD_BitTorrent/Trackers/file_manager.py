# bittorrent_project/file_manager.py
import os
import hashlib
import json # Asegúrate de importar json aquí

CHUNK_SIZE = 1024 * 512  # 512 KB

progress_file = "downloads_progress.json"
downloads_progress = {} # Diccionario para almacenar el progreso de las descargas

def load_progress():
    """Carga el estado de las descargas desde el archivo JSON."""
    global downloads_progress
    if os.path.exists(progress_file):
        with open(progress_file, "r") as f:
            try:
                downloads_progress = json.load(f)
            except json.JSONDecodeError:
                print(f"[FILE_MANAGER] Advertencia: '{progress_file}' corrupto, iniciando con progreso vacío.")
                downloads_progress = {} # Reiniciar si el archivo está corrupto
    else:
        downloads_progress = {}

def save_progress(filename, downloaded_bytes):
    """Guarda el progreso de un archivo específico."""
    global downloads_progress
    downloads_progress[filename] = downloaded_bytes
    with open(progress_file, "w") as f:
        json.dump(downloads_progress, f, indent=2)

def get_progress(filename):
    """Retorna los bytes descargados de un archivo, o 0 si no hay progreso."""
    return downloads_progress.get(filename, 0)

def remove_progress(filename):
    """Elimina el registro de progreso de un archivo específico."""
    global downloads_progress
    if filename in downloads_progress:
        del downloads_progress[filename]
        with open(progress_file, "w") as f:
            json.dump(downloads_progress, f, indent=2)

def split_file(filepath, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.basename(filepath)
    chunks = []
    with open(filepath, "rb") as f:
        i = 0
        while chunk := f.read(CHUNK_SIZE):
            chunk_name = f"{filename}.part{i}"
            with open(os.path.join(output_dir, chunk_name), "wb") as part:
                part.write(chunk)
            chunks.append(chunk_name)
            i += 1
    return chunks


def join_chunks(chunk_files, output_filepath):
    with open(output_filepath, "wb") as out:
        for chunk in chunk_files:
            # Asegúrate de que el chunk exista antes de intentar leerlo
            if os.path.exists(chunk):
                with open(chunk, "rb") as f:
                    out.write(f.read())
            else:
                print(f"[FILE_MANAGER] Advertencia: Chunk no encontrado para unir: {chunk}")


def get_file_hash(filepath):
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def check_integrity(original_path, downloaded_path):
    """Compara el hash MD5 de dos archivos para verificar su integridad."""
    if not os.path.exists(original_path):
        print(f"[FILE_MANAGER] Error: Archivo original no encontrado en {original_path}")
        return False
    if not os.path.exists(downloaded_path):
        print(f"[FILE_MANAGER] Error: Archivo descargado no encontrado en {downloaded_path}")
        return False

    hash_original = get_file_hash(original_path)
    hash_downloaded = get_file_hash(downloaded_path)

    if hash_original == hash_downloaded:
        print(f"[FILE_MANAGER] Integridad verificada: {os.path.basename(downloaded_path)} es idéntico al original.")
        return True
    else:
        print(f"[FILE_MANAGER] Fallo de integridad: Hashes diferentes para {os.path.basename(downloaded_path)}.")
        print(f"  Original Hash: {hash_original}")
        print(f"  Downloaded Hash: {hash_downloaded}")
        return False