import os
import glob
import time
import shutil
import socket
import subprocess
import threading
import webbrowser

from config import Config
from db import get_db_connection


def is_port_open(port, host='127.0.0.1'):
    """Check if a TCP port is currently listening."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def check_db_ready():
    """True if we can log in to the MySQL server on any configured port."""
    if not any(is_port_open(p, Config.DB_HOST) for p in Config.DB_PORTS):
        return False
    try:
        get_db_connection(with_db=False, timeout=2).close()
        return True
    except Exception as e:
        print(f"[Database] Server found but login failed: {e}")
        return False


def find_db_server():
    """Locate mysqld/mariadbd and its ini file. Returns (binary, ini_or_None)."""
    if Config.DB_SERVER_BIN and os.path.exists(Config.DB_SERVER_BIN):
        return Config.DB_SERVER_BIN, (Config.DB_SERVER_INI or None)

    for name in ('mariadbd', 'mysqld'):
        found = shutil.which(name)
        if found:
            return found, (Config.DB_SERVER_INI or None)

    patterns = [
        r"C:\wamp64\bin\mariadb\*\bin\mariadbd.exe",
        r"C:\wamp64\bin\mysql\*\bin\mysqld.exe",
        r"C:\wamp\bin\mysql\*\bin\mysqld.exe",
        r"D:\xampp\mysql\bin\mysqld.exe",
        r"C:\xampp\mysql\bin\mysqld.exe",
        r"C:\Program Files\MariaDB*\bin\mariadbd.exe",
        r"C:\Program Files\MySQL\MySQL Server *\bin\mysqld.exe",
    ]
    for pattern in patterns:
        matches = sorted(glob.glob(pattern), reverse=True)  # newest version first
        if matches:
            binary = matches[0]
            bin_dir = os.path.dirname(binary)
            for ini in (os.path.join(bin_dir, 'my.ini'),
                        os.path.join(os.path.dirname(bin_dir), 'my.ini'),
                        os.path.join(os.path.dirname(bin_dir), 'bin', 'my.ini')):
                if os.path.exists(ini):
                    return binary, ini
            return binary, None
    return None, None


def auto_start_database():
    """Use a running DB if there is one; otherwise try to start a local one."""
    if check_db_ready():
        print(f"[Database] Connected on {Config.DB_HOST}:{Config.DB_PORT}.")
        return True

    binary, ini = find_db_server()
    if not binary:
        print("[Warning] No running database and no MySQL/MariaDB install found.")
        print("          Start MySQL yourself, or set DB_SERVER_BIN in .env.")
        return False

    print(f"[Database] Starting server: {binary}")
    cmd = [binary]
    if ini:
        cmd.append(f"--defaults-file={ini}")
    cmd.append("--console")
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags)

    for _ in range(30):
        time.sleep(0.5)
        if check_db_ready():
            print(f"[Database] Ready on {Config.DB_HOST}:{Config.DB_PORT}.")
            return True

    print("[Warning] Started the server but could not connect. "
          "Check DB_USER / DB_PASS / DB_PORT in .env.")
    return False


def open_browser_later(url):
    """Wait for web server to start, then open default browser."""
    time.sleep(1.5)
    for _ in range(10):
        if is_port_open(Config.APP_PORT, Config.APP_HOST):
            webbrowser.open(url)
            break
        time.sleep(0.5)


if __name__ == '__main__':
    print("=" * 65)
    print("AI-Powered MPLADS Road Construction Monitoring System (v1.0)")
    print("Scope: ROAD CONSTRUCTION WORKS ONLY")
    print("=" * 65)

    # Step 1: make sure a database server is running
    auto_start_database()

    # Step 2: ensure schema and sample data exist
    from init_db import init_database
    from app import app

    try:
        init_database()
    except Exception as e:
        print(f"[Database] Schema check failed: {e}")

    from db import query_db
    from services.data_processor import process_and_save_dataset, reprocess_current_dataset, reporting_date
    count = query_db('SELECT COUNT(*) AS n FROM road_projects',one=True)['n']
    if not count:
        result = process_and_save_dataset(Config.MASTER_DATASET)
        if not result.get('success'): raise RuntimeError(result['message'])
    else:
        row = query_db('SELECT MIN(analysis_as_of) AS as_of FROM road_projects',one=True)
        if row['as_of'] is None or row['as_of'] < reporting_date():
            result = reprocess_current_dataset()
            if not result.get('success'): raise RuntimeError(result['message'])

    url = f"http://{Config.APP_HOST}:{Config.APP_PORT}"
    print(f"\n[Application] Starting Web Server on {url} ...")
    print("[Application] Admin / Authority session active by default.")
    print("Press CTRL + C anytime in this terminal to stop.\n")

    threading.Thread(target=open_browser_later, args=(url,), daemon=True).start()
    app.run(host=Config.APP_HOST, port=Config.APP_PORT, debug=False)
