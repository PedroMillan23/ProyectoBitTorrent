# bittorrent_project/network_utils.py
import socket
import json
import time
import threading # Necesario para el heartbeat del peer
import os # Necesario para listar archivos

def send_json(ip, port, message, retries=3, timeout=15): 
    for attempt in range(retries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect((ip, port))
                s.sendall(json.dumps(message).encode()) 
                
                response_data = b""
                # Recibir todos los datos que el servidor envíe hasta que cierre la conexión.
                while True:
                    chunk = s.recv(4096)
                    if not chunk: # Si el chunk está vacío, el servidor ha cerrado su lado
                        break 
                    response_data += chunk
                
                # Una vez que se han recibido *todos* los datos, intentar decodificar el JSON
                if response_data:
                    try:
                        decoded_response = json.loads(response_data.decode())
                        return decoded_response
                    except json.JSONDecodeError as json_e:
                        print(f"[NETWORK_UTILS] Error al decodificar JSON de {ip}:{port}: {json_e}")
                        print(f"[NETWORK_UTILS] Datos RAW recibidos: {response_data.decode(errors='ignore')}")
                        return None
                else:
                    print(f"[NETWORK_UTILS] No se recibieron datos de respuesta de {ip}:{port}.")
                    return None

        except (socket.timeout, ConnectionRefusedError) as e:
            print(f"[RETRY {attempt+1}] Error conectando con {ip}:{port} - {e}")
            time.sleep(1)
        except Exception as e:
            print(f"[NETWORK_UTILS] Error inesperado al enviar JSON a {ip}:{port}: {e}")
            break 
    return None

def start_listener(ip, port, handler):
    """Inicia un servidor socket que ejecuta 'handler' por cada conexión."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((ip, port))
        s.listen()
        print(f"[NETWORK_UTILS LISTENER] Escuchando conexiones entrantes en {ip}:{port}") # <-- **IMPORTANTE: AÑADE/CORRIGE ESTA LÍNEA**
        while True:
            conn, addr = s.accept()
            # El handler debe ser ejecutado en un hilo separado para manejar múltiples conexiones
            #print(f"[NETWORK_UTILS LISTENER] Conexión aceptada de {addr}") # <-- **IMPORTANTE: AÑADE ESTA LÍNEA**
            threading.Thread(target=handler, args=(conn, addr), daemon=True).start()
            # ^^^ Aquí se pasa 'conn' y 'addr' al handler (serve_file_handler)
    except OSError as e:
        print(f"[NETWORK_UTILS LISTENER ERROR] Error al iniciar el listener en {ip}:{port}: {e}") # <-- **IMPORTANTE: CORRIGE ESTA LÍNEA**
    except Exception as e:
        # Captura cualquier otro error inesperado durante la ejecución del listener
        print(f"[NETWORK_UTILS LISTENER ERROR] Error inesperado en el listener: {e}") # <-- **IMPORTANTE: AÑADE ESTA LÍNEA**
    finally:
        if 's' in locals() and s: # Asegúrate de que 's' exista antes de intentar cerrarlo
            s.close()
            print(f"[NETWORK_UTILS LISTENER] Listener en {ip}:{port} cerrado.")

# --- NUEVAS FUNCIONES PARA INTERACCIÓN CON EL TRACKER ---
def register_or_update_peer(tracker_ip, tracker_port, peer_id, peer_bind_ip, peer_port, shared_dir, received_dir, initial_registration=True, advertised_ip=None):
    """Registra o actualiza un peer con el tracker, usando la IP anunciada si se proporciona."""
    # Si no se proporciona advertised_ip, usa peer_bind_ip como fallback (para entornos no-NAT como localhost)
    ip_to_send_to_tracker = advertised_ip if advertised_ip else peer_bind_ip

    files_to_share = [f for f in os.listdir(shared_dir) if os.path.isfile(os.path.join(shared_dir, f))]
    files_to_share.extend([f for f in os.listdir(received_dir) if os.path.isfile(os.path.join(received_dir, f))])
    
    command = "REGISTER" if initial_registration else "UPDATE_FILES"
    
    message = {
        "command": command,
        "peer_id": peer_id,
        "ip": ip_to_send_to_tracker, # <-- ¡Envía la IP pública/anunciada aquí!
        "port": peer_port,
        "files": files_to_share,
        "status": "activo" # Siempre enviamos activo en el heartbeat
    }
    response = send_json(tracker_ip, tracker_port, message)
    if response and (response.get("response") == "REGISTERED" or response.get("response") == "FILES_UPDATED"):
        return True
    else:
        # print(f"[NETWORK_UTILS] Error al {command} con el tracker: {response}") # Puedes comentar esto para menos ruido
        return False

def get_peers_with_file(tracker_ip, tracker_port, filename):
    """Solicita al tracker la lista de peers que tienen un archivo específico."""
    message = {
        "command": "GET_PEERS_WITH_FILE",
        "filename": filename
    }
    response = send_json(tracker_ip, tracker_port, message)
    if response and isinstance(response.get("response"), list):
        return response["response"]
    return []

def get_network_status(tracker_ip, tracker_port):
    """Solicita al tracker el estado actual de la red."""
    message = {"command": "GET_NETWORK_STATUS"}
    response = send_json(tracker_ip, tracker_port, message)
    if response and isinstance(response, dict):
        return response
    return {}
