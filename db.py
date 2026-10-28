import pymysql
from pymysql.cursors import DictCursor
from config import Config


def get_db_connection(with_db=True, timeout=3):
    """Connect to MySQL/MariaDB, trying every configured port until one works.
    with_db=False connects to the server only (used to create the database)."""
    last_err = None
    for port in Config.DB_PORTS:
        try:
            params = dict(
                host=Config.DB_HOST,
                port=port,
                user=Config.DB_USER,
                password=Config.DB_PASS,
                charset='utf8mb4',
                cursorclass=DictCursor,
                autocommit=True,
                connect_timeout=timeout,
            )
            if with_db:
                params['database'] = Config.DB_NAME
            conn = pymysql.connect(**params)
            Config.DB_PORT = port
            # try this working port first next time
            Config.DB_PORTS = [port] + [p for p in Config.DB_PORTS if p != port]
            return conn
        except Exception as e:
            last_err = e
    raise ConnectionError(
        f"Could not connect to MySQL at {Config.DB_HOST} "
        f"(tried ports {Config.DB_PORTS}, user '{Config.DB_USER}'). Last error: {last_err}"
    )


def query_db(query, args=(), one=False):
    """Execute a query and fetch results."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, args)
            results = cursor.fetchall()
            return (results[0] if results else None) if one else results
    finally:
        conn.close()


def execute_db(query, args=()):
    """Execute a single INSERT/UPDATE/DELETE query."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, args)
            conn.commit()
            return cursor.lastrowid
    finally:
        conn.close()


def execute_many(query, args_list):
    """Execute a batch insert or update."""
    if not args_list:
        return 0
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.executemany(query, args_list)
            conn.commit()
            return cursor.rowcount
    finally:
        conn.close()
