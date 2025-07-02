# bittorrent_project/tracker.py
import socket
import threading
import json
import time
import os
from datetime import datetime

TRACKER_IP = '172.31.87.191'
TRACKER_PORT = 8080

peers = {}
log_file = "tracker_log.json"

def save_log():
    with open(log_file, "w") as f:
        json.dump(peers, f, indent=2)

def print_status():
    while True:
        os.system('cls' if os.name == 'nt' else 'clear') # Limpiar consola
        print("\n[TRACKER STATUS] Estado actual de la red:")
        active_peers = []
        inactive_peers = []
        for pid, info in peers.items():
            last_seen_time = datetime.strptime(info['last_seen'], "%Y-%m-%d %H:%M:%S")
            if (datetime.now() - last_seen_time).total_seconds() < 30:
                active_peers.append(f"- {pid} ({info['ip']}:{info['port']}) | Status: {info['status']} | Archivos: {info['files']} | Último contacto: {info['last_seen']}")
            else:
                info["status"] = "inactivo" # Actualizar estado a inactivo si no ha habido contacto
                inactive_peers.append(f"- {pid} ({info['ip']}:{info['port']}) | Status: {info['status']} | Archivos: {info['files']} | Último contacto: {info['last_seen']}")
        
        print("\n--- Peers Activos ---")
        if active_peers:
            for peer_str in active_peers:
                print(peer_str)
        else:
            print("No hay peers activos.")

        print("\n--- Peers Inactivos ---")
        if inactive_peers:
            for peer_str in inactive_peers:
                print(peer_str)
        else:
            print("No hay peers inactivos.")

        # Guardar el estado actual incluyendo los cambios de inactividad
        save_log()
        time.sleep(60)

def handle_peer(conn, addr):
    try:
        # Ya no necesitamos el 'while True' aquí si el peer abre una nueva conexión para cada request
        data = conn.recv(4096).decode()
        if not data:
            print(f"[TRACKER] Conexión vacía de {addr}. Cerrando.")
            return # Salir si no hay datos

        message = json.loads(data)
        command = message.get("command")

        if command == "REGISTER":
            peer_id = message["peer_id"]
            peers[peer_id] = {
             "ip": message["ip"],
            "port": message["port"],
            "files": message["files"],
            "status": "activo",
            "last_seen": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            save_log()
            conn.send(json.dumps({"response": "REGISTERED"}).encode())
            print(f"[TRACKER] Peer '{peer_id}' registrado desde {addr}")

        elif command == "UPDATE_FILES":
                peer_id = message["peer_id"]
                if peer_id in peers:
                    peers[peer_id]["ip"] = message["ip"]
                    peers[peer_id]["port"] = message["port"]
                    peers[peer_id]["files"] = message["files"]
                    peers[peer_id]["status"] = "activo"
                    peers[peer_id]["last_seen"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    save_log()
                    conn.send(json.dumps({"response": "FILES_UPDATED"}).encode()) # <-- ¡RESPUESTA ESENCIAL!
                    print(f"[TRACKER] Peer '{peer_id}' archivos actualizados desde {addr}.")
                else:
                    peers[peer_id] = {
                        "ip": message["ip"],
                        "port": message["port"],
                        "files": message["files"],
                        "status": "activo",
                        "last_seen": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    save_log()
                    conn.send(json.dumps({"response": "REGISTERED"}).encode()) # O FILES_UPDATED
                    print(f"[TRACKER] Peer '{peer_id}' (nuevo o inactivo) registrado/actualizado vía UPDATE_FILES desde {addr}.")

        elif command == "GET_PEERS_WITH_FILE":
                filename = message["filename"]
                result = [
                    {"peer_id": pid, "ip": p["ip"], "port": p["port"]}
                    for pid, p in peers.items() if filename in p["files"] and p["status"] == "activo"
                ]
                conn.send(json.dumps({"response": result}).encode())
                print(f"[TRACKER] Solicitud de peers con '{filename}' respondida a {addr}.")

        elif command == "GET_NETWORK_STATUS":
                conn.send(json.dumps(peers).encode())
                print(f"[TRACKER] Estado de la red solicitado y respondido a {addr}.")

        elif command == "PING":
                peer_id = message["peer_id"]
                if peer_id in peers:
                    peers[peer_id]["last_seen"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    peers[peer_id]["status"] = "activo"
                conn.send(json.dumps({"response": "PONG"}).encode())

    except json.JSONDecodeError as json_e:
        print(f"[TRACKER ERROR] Error al decodificar JSON de {addr}: {json_e}")
        print(f"[TRACKER ERROR] Datos recibidos (posiblemente corruptos): {data}")
    except socket.timeout: # Añadir manejo explícito de timeout si recv toma mucho
        print(f"[TRACKER ERROR] Timeout de socket al recibir datos de {addr}")
    except Exception as e:
        print(f"[TRACKER ERROR] Error inesperado al manejar peer {addr}: {e}")
    finally:
        conn.close()

def start_tracker():
    print(f"[TRACKER] Iniciando en {TRACKER_IP}:{TRACKER_PORT}")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Permite reusar la dirección
    
    try:
        s.bind((TRACKER_IP, TRACKER_PORT))
        s.listen()
        print(f"[TRACKER] Escuchando conexiones en {TRACKER_IP}:{TRACKER_PORT}")

        # Inicia un hilo para imprimir el estado de la red periódicamente
        threading.Thread(target=print_status, daemon=True).start()

        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_peer, args=(conn, addr)).start()

    except KeyboardInterrupt:
        print("\n[TRACKER] Detectado Ctrl+C. Cerrando tracker...")
        save_log() # Guarda el estado final de los peers
    except Exception as e:
        print(f"[TRACKER] Error crítico: {e}")
    finally:
        s.close()
        print("[TRACKER] Tracker cerrado.")

if __name__ == "__main__":
    # Cargar logs previos al inicio si existen
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            try:
                peers = json.load(f)
                print("[TRACKER] Log de peers cargado exitosamente.")
            except json.JSONDecodeError:
                print("[TRACKER] Advertencia: Archivo de log corrupto, iniciando con peers vacíos.")
                peers = {}
         
    start_tracker()
