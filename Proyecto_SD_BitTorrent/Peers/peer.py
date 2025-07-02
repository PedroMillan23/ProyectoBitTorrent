# bittorrent_project/peer.py
import socket
import threading
import json
import os
import time
from tqdm import tqdm
import urllib.request
import random
import base64

# Importaciones de módulos locales
from file_manager import load_progress, save_progress, get_progress, remove_progress, CHUNK_SIZE
from network_utils import send_json, start_listener, register_or_update_peer, get_peers_with_file, get_network_status

# --- CONFIGURACIÓN INICIAL DEL PEER ---
PEER_ID = input("Ingrese el nombre del PEER: ")

# --- MODIFICACIÓN AQUÍ: Función para obtener IPs públicas y privadas ---
def get_aws_instance_ips():
    private_ip = None
    public_ip = None
    try:
        # Obtener IP privada de los metadatos de AWS EC2
        # 'local-ipv4' es el endpoint para la IP privada
        private_ip = urllib.request.urlopen("http://169.254.169.254/latest/meta-data/local-ipv4", timeout=1).read().decode()
        # Obtener IP pública de los metadatos de AWS EC2
        # 'public-ipv4' es el endpoint para la IP pública
        public_ip = urllib.request.urlopen("http://169.254.169.254/latest/meta-data/public-ipv4", timeout=1).read().decode()
        return private_ip, public_ip
    except Exception:
        #print("Nose pudo obtener las IPs")
        # Si falla (no en EC2, metadatos no accesibles, etc.),
        # intenta obtener la IP local del sistema de otra manera (será la misma para binding y advertised)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80)) # Conecta a un servidor externo (Google DNS) para obtener la IP de salida
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip, local_ip # En este caso, la IP local es tanto la de binding como la que se anuncia
        except Exception as e:
            print(f"Error al obtener IPs locales: {e}")
            return None, None

# Obtener IPs al inicio
PEER_BIND_IP, PEER_ADVERTISED_IP = get_aws_instance_ips()

if PEER_BIND_IP is None:
    print("[PEER] No se pudo determinar la IP del peer. Saliendo.")
    exit()
PEER_ADVERTISED_IP=input("Ingrese la IP Publica de este PEER: ")
PEER_IP = PEER_BIND_IP # Esta IP se usará para el binding local del socket
PEER_PORT = int(input("Ingrese el puerto de este PEER: "))

TRACKER_IP= "172.31.87.191"
TRACKER_PORT=8080

SHARED_DIR = "sample_files"
RECEIVED_DIR = "received_files"

# Asegurarse de que los directorios existan
os.makedirs(SHARED_DIR, exist_ok=True)
os.makedirs(RECEIVED_DIR, exist_ok=True)

# Cargar el progreso de descargas al iniciar
load_progress()

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')

# --- HEARTBEAT CON EL TRACKER ---
def heartbeat_to_tracker(interval=10):
    """Envía un mensaje de 'keep-alive' y actualiza archivos al tracker periódicamente."""
    while True:
        # MODIFICACIÓN: Usar PEER_ADVERTISED_IP para registrar con el tracker
        success = register_or_update_peer(TRACKER_IP, TRACKER_PORT, PEER_ID, PEER_ADVERTISED_IP, PEER_PORT, SHARED_DIR, RECEIVED_DIR, initial_registration=False)
        if success:
            #print(f"[PEER] Heartbeat enviado al tracker. Estado: Activo.")
            pass # No imprimir en cada heartbeat para evitar spam en consola
        else:
            print(f"[PEER] Falló el envío del heartbeat al tracker. Reintentando...")
        time.sleep(interval)

# --- FUNCIONES DE SERVICIO DE ARCHIVOS (SEEDER) ---
def serve_file_handler(conn, addr):
    try:
        data = conn.recv(4096).decode()
        if not data:
            print(f"[PEER LISTENER] Conexión cerrada por {addr}.")
            return

        request = json.loads(data)
        command = request.get("command")

        # --- Manejo de GET_FILE_INFO ---
        if command == "GET_FILE_INFO":
            filename = request["filename"]
            filepath_shared = os.path.join(SHARED_DIR, filename)
            filepath_received = os.path.join(RECEIVED_DIR, filename)

            file_path = None
            if os.path.exists(filepath_shared):
                file_path = filepath_shared
            elif os.path.exists(filepath_received):
                file_path = filepath_received

            if file_path and os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                num_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
                response = {"status": "success", "file_size": file_size, "num_chunks": num_chunks}
                conn.sendall(json.dumps(response).encode())
                #print(f"[PEER LISTENER] Respondiendo solicitud de info para '{filename}': {file_size} bytes, {num_chunks} chunks.")
            else:
                response = {"status": "error", "message": "File not found"}
                conn.sendall(json.dumps(response).encode())
                print(f"[PEER LISTENER] Archivo '{filename}' no encontrado para info.")

        # --- Manejo de REQUEST_CHUNK ---
        elif command == "REQUEST_CHUNK":
            filename = request["filename"]
            chunk_index = request["chunk_index"]
            
            filepath_shared = os.path.join(SHARED_DIR, filename)
            filepath_received = os.path.join(RECEIVED_DIR, filename)

            file_path = None
            if os.path.exists(filepath_shared):
                file_path = filepath_shared
            elif os.path.exists(filepath_received):
                file_path = filepath_received

            if file_path:
                #print(f"[PEER LISTENER] Sirviendo {filename} (chunk {chunk_index}) desde {file_path}")
                try:
                    with open(file_path, "rb") as f:
                        f.seek(chunk_index * CHUNK_SIZE)
                        chunk_data = f.read(CHUNK_SIZE)
                        
                        if chunk_data:
                            encoded_chunk = base64.b64encode(chunk_data).decode('ascii') 
                            response = {"status": "success", "chunk": encoded_chunk} 
                            conn.sendall(json.dumps(response).encode())
                        else:
                            print(f"[PEER LISTENER] Chunk {chunk_index} vacío para {filename}. Fuera de rango o archivo más corto.")
                            response = {"status": "error", "message": "Chunk out of range or file too small"}
                            conn.sendall(json.dumps(response).encode())
                except Exception as e:
                    print(f"[PEER LISTENER ERROR] Error al leer/enviar chunk {chunk_index} de {filename}: {e}")
                    response = {"status": "error", "message": f"Error al leer/enviar chunk: {e}"}
                    conn.sendall(json.dumps(response).encode())
            else:
                print(f"[PEER LISTENER] Archivo no encontrado en el directorio compartido o de descarga: {filename}")
                response = {"status": "error", "message": "File not found"}
                conn.sendall(json.dumps(response).encode())
        else:
            print(f"[PEER LISTENER] Comando desconocido: {command}")
            response = {"status": "error", "message": "Unknown command"}
            conn.sendall(json.dumps(response).encode())

    except json.JSONDecodeError:
        print(f"[PEER LISTENER ERROR] Datos JSON inválidos recibidos de {addr}")
        try:
            conn.sendall(json.dumps({"status": "error", "message": "Invalid JSON"}).encode())
        except Exception as e:
            print(f"[PEER LISTENER ERROR] Error al enviar respuesta de error JSON: {e}")
    except ConnectionResetError:
        pass # Cliente cerró la conexión
    except Exception as e:
        print(f"[PEER LISTENER ERROR] Error general en serve_file_handler con {addr}: {e}")
    finally:
        conn.close() # Asegúrate de que la conexión se cierre aquí

# --- FUNCIONES DE DESCARGA DE ARCHIVOS (LEECHER) ---
# MODIFICACIÓN: Eliminado el parámetro 'chunk_size_limit' ya que no se usa.
def download_chunk_from_peer(peer_ip, peer_port, filename, chunk_index):
    """
    Solicita y descarga un chunk específico de un peer utilizando un protocolo JSON.
    Retorna los bytes del chunk o None si falla.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(35) # Timeout para la conexión y recepción
            s.connect((peer_ip, peer_port))

            request_message = {
                "command": "REQUEST_CHUNK",
                "filename": filename,
                "chunk_index": chunk_index
            }
            s.sendall(json.dumps(request_message).encode())
            
            response_data = b""
            # Recibir todos los datos que el servidor envíe hasta que cierre la conexión.
            while True:
                chunk_recv = s.recv(4096)
                if not chunk_recv:
                    break
                response_data += chunk_recv
            
            if response_data:
                try:
                    decoded_response = json.loads(response_data.decode())
                    if decoded_response.get("status") == "success" and "chunk" in decoded_response:
                        return base64.b64decode(decoded_response["chunk"]) 
                    else:
                        print(f"[DOWNLOAD] Error en la respuesta del peer {peer_ip}:{peer_port}: {decoded_response.get('message', 'Mensaje de error desconocido')}")
                        return None
                except json.JSONDecodeError as json_e:
                    #print(f"[DOWNLOAD] Error al decodificar JSON de respuesta del peer {peer_ip}:{peer_port}: {json_e}")
                    print(f"[DOWNLOAD] Datos RAW recibidos: {response_data.decode(errors='ignore')}") 
                    return None
            else:
                print(f"[DOWNLOAD] No se recibieron datos de chunk del peer {peer_ip}:{peer_port}.")
                return None

    except socket.timeout:
        print(f"[DOWNLOAD] Timeout al descargar chunk de {peer_ip}:{peer_port}.")
    except ConnectionRefusedError:
        print(f"[DOWNLOAD] Conexión rechazada por {peer_ip}:{peer_port} al descargar chunk.")
    except Exception as e:
        print(f"[DOWNLOAD] Error inesperado al descargar chunk de {peer_ip}:{peer_port}: {e}")
    
    return None

def get_file_info_from_peer(peer_ip, peer_port, filename):
    """
    Solicita al peer la información del archivo (tamaño total y número de chunks).
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(35) # Timeout
            s.connect((peer_ip, peer_port))

            request_message = {
                "command": "GET_FILE_INFO", # Este comando es el que tu servidor (Peer B) debe esperar
                "filename": filename
            }
            s.sendall(json.dumps(request_message).encode())

            response_data = b""
            # Recibir todos los datos que el servidor envíe hasta que cierre la conexión.
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                response_data += chunk
            
            if response_data:
                try:
                    decoded_response = json.loads(response_data.decode())
                    if decoded_response.get("status") == "success":
                        # Aquí puedes esperar 'file_size' y 'num_chunks'
                        return decoded_response
                    else:
                        #print(f"[PEER] Error en la respuesta de info del peer {peer_ip}:{peer_port}: {decoded_response.get('message', 'Mensaje de error desconocido')}")
                        return None
                except json.JSONDecodeError as json_e:
                    print(f"[PEER] Error al decodificar JSON de info del peer {peer_ip}:{peer_port}: {json_e}")
                    print(f"[PEER] Datos RAW recibidos: {response_data.decode(errors='ignore')}")
                    return None
            else:
                print(f"[PEER] No se recibieron datos de info del peer {peer_ip}:{peer_port}.")
                return None

    except socket.timeout:
        print(f"[PEER] Timeout al solicitar info del peer {peer_ip}:{peer_port}.")
    except ConnectionRefusedError:
        print(f"[PEER] Conexión rechazada por {peer_ip}:{peer_port} al solicitar info.")
    except Exception as e:
        print(f"[PEER] Error inesperado al solicitar info del peer {peer_ip}:{peer_port}: {e}")
    
    return None

def download_file(filename):
    filepath = os.path.join(RECEIVED_DIR, filename) 
    
    load_progress()
    downloaded_bytes_count = get_progress(filename)
    file_size = None # Inicializar file_size aquí

    # Buscar un peer para obtener la información del archivo (incluido el tamaño)
    peers_for_info_and_download = get_peers_with_file(TRACKER_IP, TRACKER_PORT, filename)
    if not peers_for_info_and_download:
        print(f"[PEER] Ningún peer tiene el archivo '{filename}'.")
        return
    
    # Intenta obtener el tamaño del archivo de un peer
    for peer_info in peers_for_info_and_download:
        if peer_info['ip'] == PEER_ADVERTISED_IP and peer_info['port'] == PEER_PORT:
            continue # No pedir información a sí mismo
        
        file_info = get_file_info_from_peer(peer_info['ip'], peer_info['port'], filename)
        if file_info and 'file_size' in file_info:
            file_size = file_info['file_size']
            break
    
    if file_size is None:
        print(f"[PEER] No se pudo obtener el tamaño del archivo '{filename}' de ningún peer disponible.")
        return # Salir si no se puede obtener el tamaño

    # Lógica de reanudación o inicio de descarga
    if os.path.exists(filepath):
        #print(f"[PEER] El archivo '{filename}' ya existe localmente. Verificando tamaño...")
        current_local_size = os.path.getsize(filepath)
        
        if current_local_size == file_size:
            print(f"[PEER] El archivo '{filename}' ya está completo. Actualizando tracker y saliendo.")
            remove_progress(filename) 
            # MODIFICACIÓN: Usar PEER_ADVERTISED_IP al actualizar el tracker
            register_or_update_peer(TRACKER_IP, TRACKER_PORT, PEER_ID, PEER_ADVERTISED_IP, PEER_PORT, SHARED_DIR, RECEIVED_DIR, initial_registration=False)
            return 
        elif current_local_size < file_size:
            print(f"[PEER] El archivo '{filename}' está incompleto ({current_local_size}/{file_size} bytes). Reanudando descarga.")
            downloaded_bytes_count = current_local_size 
            save_progress(filename, downloaded_bytes_count)
        else: # current_local_size > file_size
            print(f"[PEER] Advertencia: El archivo '{filename}' local es más grande de lo esperado. Reiniciando descarga.")
            os.remove(filepath) 
            remove_progress(filename)
            downloaded_bytes_count = 0 
    else: # Archivo no existe localmente, iniciar descarga desde cero
        downloaded_bytes_count = 0 
        remove_progress(filename) # Asegurarse de que no haya progreso antiguo corrupto

    # Asegurarse de que el directorio de recepción existe
    os.makedirs(RECEIVED_DIR, exist_ok=True)

    print(f"[PEER] Iniciando descarga de '{filename}' ({file_size} bytes). Progreso actual: {downloaded_bytes_count} bytes.")

    mode = "ab" if downloaded_bytes_count > 0 else "wb" 
    with open(filepath, mode) as f:
        if mode == "ab":
            f.seek(0, os.SEEK_END)

        with tqdm(initial=downloaded_bytes_count, total=file_size, unit="B", unit_scale=True,
                    desc=f"Descargando {filename}", ascii=True) as pbar:
            
            while downloaded_bytes_count < file_size:
                available_peers = get_peers_with_file(TRACKER_IP, TRACKER_PORT, filename)
                available_peers = [p for p in available_peers if not (p['ip'] == PEER_ADVERTISED_IP and p['port'] == PEER_PORT)] # Usar advertised IP aquí también

                if not available_peers:
                    print(f"\n[PEER] Todos los peers con '{filename}' se desconectaron o no hay otros peers. Reintentando en 10 segundos...")
                    time.sleep(10)
                    continue
                
                random.shuffle(available_peers)
                # --- PASO 1: Calcular el índice del chunk actual para la descripción ---
                chunk_index_for_display = downloaded_bytes_count // CHUNK_SIZE
                
                # --- PASO 2: Actualizar la descripción de la barra de progreso ---
                # Esta línea debe ir aquí, antes de intentar descargar el chunk
                pbar.set_description(f"Descargando {filename} [Chunk {chunk_index_for_display}]")

                chunk_downloaded_this_iteration = False
                for peer in available_peers:
                    peer_ip, peer_port = peer['ip'], peer['port']
                    
                    chunk_index = downloaded_bytes_count // CHUNK_SIZE
                    
                    #print(f"\n[PEER] Intentando descargar chunk {chunk_index} de '{filename}' desde {peer['peer_id']} ({peer_ip}:{peer_port})...")
                    
                    # MODIFICACIÓN: Eliminado el parámetro 'chunk_size_limit'
                    chunk_data = download_chunk_from_peer(peer_ip, peer_port, filename, chunk_index) 
                    
                    if chunk_data is not None and len(chunk_data) > 0:
                        f.write(chunk_data)
                        downloaded_bytes_count += len(chunk_data)
                        pbar.update(len(chunk_data))
                        save_progress(filename, downloaded_bytes_count) 
                        chunk_downloaded_this_iteration = True
                        break 
                    else:
                        print(f"\n[PEER] No se pudo descargar el chunk {chunk_index} de {peer['peer_id']}.")
                        pass 
                
                if not chunk_downloaded_this_iteration and downloaded_bytes_count < file_size:
                    print(f"\n[PEER] No se pudo conectar con ningún peer para continuar la descarga de '{filename}'. Reintentando en 5 segundos...")
                    time.sleep(5)
    
    if downloaded_bytes_count >= file_size:
        print(f"\n[PEER] Descarga de '{filename}' completada.")
        remove_progress(filename) 
        # MODIFICACIÓN: Usar PEER_ADVERTISED_IP al actualizar el tracker
        register_or_update_peer(TRACKER_IP, TRACKER_PORT, PEER_ID, PEER_ADVERTISED_IP, PEER_PORT, SHARED_DIR, RECEIVED_DIR, initial_registration=False) 
    else:
        print(f"\n[PEER] Descarga de '{filename}' finalizada pero incompleta. Progreso guardado.")

# --- MENÚ PRINCIPAL ---
def main_menu():
    """Presenta el menú de opciones al usuario del peer."""
    while True:
        clear_console() # MODIFICACIÓN: Mover clear_console() al inicio del bucle
        print(f"\n---------------------------------------------------------------------")
        print(f"|                     PEER {PEER_ID}                                    |")
        print(f"| IP Local (Bind): {PEER_BIND_IP}, Puerto: {PEER_PORT}                      |") 
        print(f"| IP Publicada (Tracker): {PEER_ADVERTISED_IP}                        |") # Añadido para mostrar IP Publicada
        print(f"---------------------------------------------------------------------")
        print("1. Mostrar archivos locales")
        print("2. Mostrar archivos disponibles en la red")
        print("3. Descargar archivo")
        print("4. Forzar actualización de archivos compartidos al tracker")
        print("5. Salir")
        choice = input("Seleccione una opción: ")

        if choice == '1':
            # clear_console() # Eliminado: se limpia al inicio del bucle
            print("\n--- Archivos Locales ---")
            local_files = [f for f in os.listdir(SHARED_DIR) if os.path.isfile(os.path.join(SHARED_DIR, f))]
            local_files.extend([f for f in os.listdir(RECEIVED_DIR) if os.path.isfile(os.path.join(RECEIVED_DIR, f))])
            if local_files:
                for f in sorted(list(set(local_files))): 
                    print(f"- {f}")
            else:
                print("No hay archivos locales.")
            input("\nPresione Enter para continuar...") 
        elif choice == '2':
            # clear_console() # Eliminado: se limpia al inicio del bucle
            print("\n--- Archivos Disponibles en la Red (según el tracker) ---")
            network_status = get_network_status(TRACKER_IP, TRACKER_PORT)
            if network_status:
                available_files = set()
                for pid, info in network_status.items():
                    if info.get('status') == 'activo': 
                        for f in info['files']:
                            available_files.add(f)
                if available_files:
                    for f in sorted(list(available_files)):
                        print(f"- {f}")
                else:
                    print("No hay archivos disponibles en la red de peers activos.")
            else:
                print("[PEER] No se pudo obtener el estado de la red del tracker.")
            input("\nPresione Enter para continuar...") 
        elif choice == '3':
            # clear_console() # Eliminado: se limpia al inicio del bucle
            print("\n--- Archivos Disponibles en la Red (según el tracker) ---")
            network_status = get_network_status(TRACKER_IP, TRACKER_PORT)
            if network_status:
                available_files = set()
                for pid, info in network_status.items():
                    if info.get('status') == 'activo':
                        for f in info['files']:
                            available_files.add(f)
                if available_files:
                    for f in sorted(list(available_files)):
                        print(f"- {f}")
                else:
                    print("No hay archivos disponibles en la red de peers activos.")
            else:
                print("[PEER] No se pudo obtener el estado de la red del tracker.")

            filename = input("Ingrese el nombre del archivo a descargar: ")
            threading.Thread(target=download_file, args=(filename,)).start()
            input("\nLa descarga ha comenzado en segundo plano. Presione Enter para continuar...")
        elif choice == '4':
            # clear_console() # Eliminado: se limpia al inicio del bucle
            # MODIFICACIÓN: Usar PEER_ADVERTISED_IP al actualizar el tracker
            success = register_or_update_peer(TRACKER_IP, TRACKER_PORT, PEER_ID, PEER_ADVERTISED_IP, PEER_PORT, SHARED_DIR, RECEIVED_DIR, initial_registration=False)
            if success:
                print("\nArchivos locales actualizados en el tracker.")
            else:
                print("\nNo se pudieron actualizar los archivos en el tracker.")
            input("\nPresione Enter para continuar...")
        elif choice == '5':
            print("[PEER] Saliendo...")
            break
        else:
            print("Opción no válida. Intente de nuevo.")
            input("\nPresione Enter para continuar...")

def main():
    """Función principal del peer."""
    # Registro inicial al tracker
    print("[PEER] Registrando peer con el tracker...")
    # MODIFICACIÓN: Usar PEER_ADVERTISED_IP para el registro inicial
    if not register_or_update_peer(TRACKER_IP, TRACKER_PORT, PEER_ID, PEER_ADVERTISED_IP, PEER_PORT, SHARED_DIR, RECEIVED_DIR, initial_registration=True):
        print("[PEER] Falló el registro inicial. Asegúrese de que el tracker esté corriendo.")
        exit() # Salir si el registro inicial falla
    print("[PEER] Registro exitoso. Iniciando servicios...")

    print(f"[PEER] Iniciando servicio de archivos en {PEER_BIND_IP}:{PEER_PORT}") # Clarificado para mostrar la IP de binding
    # Inicia el servicio de archivos (seeder) en un hilo daemon
    threading.Thread(target=start_listener, args=(PEER_BIND_IP, PEER_PORT, serve_file_handler), daemon=True).start() # Usar PEER_BIND_IP

    # Inicia el heartbeat periódico al tracker en un hilo daemon
    threading.Thread(target=heartbeat_to_tracker, daemon=True).start()

    main_menu()

if __name__ == "__main__":
    main()