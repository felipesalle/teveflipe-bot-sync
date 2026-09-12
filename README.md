# TeveFlipe Bot Sync (Telegram -> GitHub Actions)

Bot automatizado en Python con **Telethon** para clasificar y sincronizar películas y series desde grupos origen hacia el repositorio y foro organizado de **TeveFlipe**.

## 🚀 Características
* **Películas:** Detecta automáticamente nuevos archivos de video (`.mkv`, `.mp4`, etc.) en el grupo origen y los reenvía de forma directa y limpia al canal de **Películas Destino**.
* **Series:**
  * Lee mensajes del grupo/tema origen de series.
  * Si detecta una imagen de presentación o carátula, la guarda para asociarla al póster de la serie.
  * Comprueba si ya existe un **Tema (Forum Topic)** con el nombre de la serie en el supergrupo destino.
  * Si no existe, **crea automáticamente el Tema en el foro**.
  * Reenvía la carátula y los episodios (`S01E01`, etc.) directamente dentro del Tema de la serie.
* **Sin consumo de ancho de banda:** Los archivos multimedia se gestionan directamente en la nube de Telegram (reenvío en servidores de Telegram sin descargar gigabytes al servidor o a GitHub).
* **GitHub Actions:** Corre automáticamente de forma programada con cron y permite ejecución manual con un solo clic.

---

## ⚙️ Configuración de Secretos en GitHub

En tu repositorio de GitHub ve a **Settings** ➡️ **Secrets and variables** ➡️ **Actions** ➡️ **New repository secret**:

1. `TELEGRAM_API_ID`: `28045969`
2. `TELEGRAM_API_HASH`: `d8e515c5687943e5e0bf046f87c3d2cc`
3. `TELEGRAM_STRING_SESSION`: La cadena generada ejecutando `python generar_sesion.py` en tu PC.

---

## 🔑 Cómo generar tu TELEGRAM_STRING_SESSION en local

1. Abre tu terminal en la carpeta del proyecto:
   ```bash
   cd e:\teveflipe-bot-sync
   ```
2. Ejecuta:
   ```bash
   python generar_sesion.py
   ```
3. Ingresa tu número de teléfono y el código de verificación que te llegará a Telegram.
4. Copia el texto largo que aparece al final y pégalo en el Secret `TELEGRAM_STRING_SESSION` de GitHub.
