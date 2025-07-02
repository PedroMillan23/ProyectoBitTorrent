# bittorrent_project/README.md
# Simulación de Red BitTorrent — Proyecto de Sistemas Distribuidos

## Descripción
Este proyecto emula una red BitTorrent con múltiples nodos (peers) y un tracker central. Cada peer puede actuar como cliente (leecher) y servidor (seeder), compartiendo archivos con otros nodos y descargando simultáneamente.

## Estructura del Proyecto
- `tracker.py`: Servidor que coordina la red.
- `peer.py`: Nodo de la red, que puede descargar y compartir archivos.
- `file_manager.py`: Fragmentación, unión y verificación de archivos.
- `network_utils.py`: Comunicación robusta entre nodos.
- `config.json`: Configuración del sistema.
- `sample_files/`: Archivos a compartir.
- `received_files/`: Archivos descargados.

## Cómo ejecutar
1. Ejecuta el tracker:
   ```bash
   python tracker.py
   ```

2. Ejecuta varios peers en diferentes terminales:
   ```bash
   python peer.py
   ```
   Al iniciar, te pedirá nombre del peer y puerto (ej. A, 6001).

3. En cada peer:
   - Puedes ver archivos locales.
   - Descargar archivos de la red.

## Video de Demostración
Graba los siguientes puntos:
1. Registro de peers (muestra IP y puerto).
2. Visualización del estado de la red desde el tracker.
3. Compartición de archivos por cada peer.
4. Solicitud de archivos por otro peer.
5. Transferencia de múltiples archivos simultáneamente.
6. Desconexión de un peer y su reconexión con recuperación del progreso.

## Requisitos Técnicos
- Python 3.10+
- Ejecutable en red local o servicios en la nube (AWS, GCP, etc.)

---
Desarrollado para la Unidad de Aprendizaje: **Sistemas Distribuidos - Proyecto Final (Ago-Dic 2024)**
