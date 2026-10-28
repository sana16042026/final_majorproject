import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _load_env_file(path):
    """Tiny .env loader (no extra dependency). Real environment variables win."""
    if not os.path.isfile(path):
        return
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(os.path.join(BASE_DIR, '.env'))


def _candidate_ports():
    """Ports to try, in order. A port you set explicitly is tried first,
    then the common MySQL/MariaDB defaults as a fallback."""
    raw = os.getenv('DB_PORT') or os.getenv('DB_PORTS') or ''
    ports = [int(p) for p in raw.replace(' ', '').split(',') if p.isdigit()]
    for default in (3306, 3307):
        if default not in ports:
            ports.append(default)
    return ports


class Config:
    BASE_DIR = BASE_DIR
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    MASTER_DATASET = os.path.join(BASE_DIR, 'data', 'Master_Road_Work_Dataset_15000.xlsx')
    DATA_FOLDER = os.path.join(BASE_DIR, 'data')
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32 MB max upload
    ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}

    # Login sessions. Set SECRET_KEY in .env for anything beyond a demo.
    SECRET_KEY = os.getenv('SECRET_KEY', 'mplads-dev-secret-change-me')

    # Database
    DB_HOST = os.getenv('DB_HOST', '127.0.0.1')
    DB_PORTS = _candidate_ports()
    DB_PORT = DB_PORTS[0]          # updated automatically once a connection works
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASS = os.getenv('DB_PASS', '')
    DB_NAME = os.getenv('DB_NAME', 'drishti_master_road')

    # Web server
    APP_HOST = os.getenv('APP_HOST', '127.0.0.1')
    APP_PORT = int(os.getenv('APP_PORT', 5000))

    # Optional: full path to mysqld/mariadbd (and my.ini) if auto-detection fails
    DB_SERVER_BIN = os.getenv('DB_SERVER_BIN', r'D:\xampp\mysql\bin\mysqld.exe')
    DB_SERVER_INI = os.getenv('DB_SERVER_INI', r'D:\xampp\mysql\bin\my.ini')


os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(Config.DATA_FOLDER, exist_ok=True)
