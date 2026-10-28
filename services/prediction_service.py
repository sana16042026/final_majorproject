import json

from db import get_db_connection, query_db


def _ensure_tables(cursor):
    """Create the prediction tables if an older database does not have them yet."""
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS `predictions` (
        `prediction_id` INT AUTO_INCREMENT PRIMARY KEY,
        `work_id` VARCHAR(50),
        `predicted_delay_days` DOUBLE DEFAULT 0,
        `predicted_overrun_pct` DOUBLE DEFAULT 0,
        `delay_likely` TINYINT(1) DEFAULT 0,
        `overrun_likely` TINYINT(1) DEFAULT 0,
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX (`work_id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS `prediction_summary` (
        `summary_id` INT AUTO_INCREMENT PRIMARY KEY,
        `metrics_json` LONGTEXT,
        `trained_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)


def save_prediction_results(records, summary, batch_size=2000):
    """Replace the stored predictions and model summary with a new training run."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            _ensure_tables(cursor)
            cursor.execute("DELETE FROM `predictions`")
            cursor.execute("DELETE FROM `prediction_summary`")
            if records:
                sql = """
                INSERT INTO `predictions`
                    (work_id, predicted_delay_days, predicted_overrun_pct, delay_likely, overrun_likely)
                VALUES
                    (%(work_id)s, %(predicted_delay_days)s, %(predicted_overrun_pct)s,
                     %(delay_likely)s, %(overrun_likely)s)
                """
                for i in range(0, len(records), batch_size):
                    cursor.executemany(sql, records[i:i + batch_size])
            cursor.execute("INSERT INTO `prediction_summary` (metrics_json) VALUES (%s)",
                           (json.dumps(summary),))
        conn.commit()
    finally:
        conn.close()


def get_prediction_summary():
    """Latest model summary (accuracy, drivers) or None if no model was trained yet."""
    try:
        row = query_db("SELECT metrics_json FROM `prediction_summary` "
                       "ORDER BY summary_id DESC LIMIT 1", one=True)
    except Exception:
        return None
    if not row or not row.get('metrics_json'):
        return None
    try:
        return json.loads(row['metrics_json'])
    except ValueError:
        return None


def get_project_prediction(work_id):
    """Stored prediction of one project, or None."""
    try:
        return query_db(
            "SELECT predicted_delay_days, predicted_overrun_pct, delay_likely, overrun_likely "
            "FROM `predictions` WHERE work_id = %s LIMIT 1", [work_id], one=True)
    except Exception:
        return None
