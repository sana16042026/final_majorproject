import json

from db import get_db_connection, query_db


def _ensure_tables(cursor):
    """Create the duplicate-check tables if an older database does not have them yet."""
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS `duplicate_analysis` (
        `pair_id` INT AUTO_INCREMENT PRIMARY KEY,
        `work_id_1` VARCHAR(50),
        `work_id_2` VARCHAR(50),
        `text_similarity` DOUBLE DEFAULT 0,
        `evidence_score` DOUBLE DEFAULT 0,
        `classification` VARCHAR(30),
        `evidence` TEXT,
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX (`work_id_1`),
        INDEX (`work_id_2`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS `duplicate_summary` (
        `summary_id` INT AUTO_INCREMENT PRIMARY KEY,
        `metrics_json` LONGTEXT,
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)


def save_duplicate_results(records, summary, batch_size=2000):
    """Replace the stored duplicate pairs and summary with a new run."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            _ensure_tables(cursor)
            cursor.execute("DELETE FROM `duplicate_analysis`")
            cursor.execute("DELETE FROM `duplicate_summary`")
            if records:
                sql = """
                INSERT INTO `duplicate_analysis`
                    (work_id_1, work_id_2, text_similarity, evidence_score, classification, evidence)
                VALUES
                    (%(work_id_1)s, %(work_id_2)s, %(text_similarity)s, %(evidence_score)s,
                     %(classification)s, %(evidence)s)
                """
                for i in range(0, len(records), batch_size):
                    cursor.executemany(sql, records[i:i + batch_size])
            cursor.execute("INSERT INTO `duplicate_summary` (metrics_json) VALUES (%s)",
                           (json.dumps(summary),))
        conn.commit()
    finally:
        conn.close()


def get_duplicate_summary():
    """Latest duplicate-check summary or None."""
    try:
        row = query_db("SELECT metrics_json FROM `duplicate_summary` "
                       "ORDER BY summary_id DESC LIMIT 1", one=True)
    except Exception:
        return None
    if not row or not row.get('metrics_json'):
        return None
    try:
        return json.loads(row['metrics_json'])
    except ValueError:
        return None


def get_project_duplicates(work_id, limit=3):
    """Strongest duplicate / overlap matches of one project (either side of the pair)."""
    try:
        rows = query_db("""
            SELECT d.classification, d.evidence_score, d.text_similarity, d.evidence,
                   CASE WHEN d.work_id_1 = %s THEN d.work_id_2 ELSE d.work_id_1 END AS other_work_id
            FROM `duplicate_analysis` d
            WHERE d.work_id_1 = %s OR d.work_id_2 = %s
            ORDER BY d.evidence_score DESC
            LIMIT %s
        """, [work_id, work_id, work_id, limit])
    except Exception:
        return []
    for r in rows:
        other = query_db("SELECT description, district, state FROM road_projects WHERE work_id = %s",
                         [r['other_work_id']], one=True) or {}
        r['other_description'] = other.get('description', '')
        r['other_district'] = other.get('district', '')
    return rows
