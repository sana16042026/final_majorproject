from werkzeug.security import generate_password_hash
from config import Config
from db import get_db_connection

# Demo accounts, one per role. Existing usernames are never overwritten.
# (username, password, full name, role, district, mp_id, vendor_id)
DEMO_USERS = [
    ('admin',      'admin123',    'District Administrator (All Districts)', 'district_admin', None,   None, None),
    ('admin_pune', 'pune123',     'District Administrator - Pune',          'district_admin', 'Pune', None, None),
    ('ministry',   'ministry123', 'Nodal Ministry Officer',                 'ministry',       None,   None, None),
    ('auditor',    'auditor123',  'Audit Officer',                          'auditor',        None,   None, None),
    ('vendor',     'vendor123',   'Contractor (VEN-101)',                   'vendor',         None,   None, 'VEN-101'),
    ('citizen',    'citizen123',  'Citizen (Public View)',                  'citizen',        None,   None, None),
]

DB_NAME = Config.DB_NAME


def init_database():
    print(f"Connecting to MySQL server to initialize database '{DB_NAME}'...")
    conn = get_db_connection(with_db=False)
    print(f"Connected on {Config.DB_HOST}:{Config.DB_PORT} as '{Config.DB_USER}'.")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )
            print(f"Database `{DB_NAME}` ready.")
        conn.commit()
    finally:
        conn.close()

    conn = get_db_connection(with_db=True)
    try:
        with conn.cursor() as cursor:
            # 1. road_projects table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS `road_projects` (
                `work_id` VARCHAR(50) PRIMARY KEY,
                `description` TEXT,
                `road_type` VARCHAR(100),
                `state` VARCHAR(100),
                `district` VARCHAR(100),
                `constituency` VARCHAR(100),
                `house` VARCHAR(50),
                `mp_id` VARCHAR(50),
                `length_m` DOUBLE DEFAULT 0,
                `estimated_cost` DOUBLE DEFAULT 0,
                `sanctioned_amount` DOUBLE DEFAULT 0,
                `tender_amount` DOUBLE DEFAULT 0,
                `agreement_amount` DOUBLE DEFAULT 0,
                `actual_expenditure` DOUBLE DEFAULT 0,
                `final_amount` DOUBLE DEFAULT 0,
                `cost_overrun_pct` DOUBLE DEFAULT 0,
                `delay_days` INT DEFAULT 0,
                `vendor_id` VARCHAR(100),
                `number_of_bidders` INT DEFAULT 1,
                `physical_progress_pct` DOUBLE DEFAULT 0,
                `financial_progress_pct` DOUBLE DEFAULT 0,
                `physical_financial_gap_pct` DOUBLE DEFAULT 0,
                `status` VARCHAR(50) DEFAULT 'Ongoing',
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            additions = {'work_title': "VARCHAR(255) DEFAULT ''", 'work_type': "VARCHAR(150) DEFAULT ''", 'implementing_agency': "VARCHAR(255) DEFAULT ''", 'payment_status': "VARCHAR(100) DEFAULT ''", 'progress_basis': 'TEXT', 'source_json': 'LONGTEXT', 'length_km': 'DOUBLE NULL', 'cost_per_km': 'DOUBLE NULL', 'latitude': 'DOUBLE NULL', 'longitude': 'DOUBLE NULL', 'invested_amount_inr': 'DOUBLE NULL', 'start_date': 'DATE NULL', 'expected_completion_date': 'DATE NULL', 'completion_date': 'DATE NULL', 'analysis_as_of': 'DATE NULL', 'delay_basis': 'VARCHAR(255)'}
            for column, definition in additions.items():
                cursor.execute('SHOW COLUMNS FROM road_projects LIKE %s',(column,))
                if not cursor.fetchone():
                    cursor.execute(f'ALTER TABLE road_projects ADD COLUMN `{column}` {definition}')
            cursor.execute('ALTER TABLE road_projects MODIFY mp_id VARCHAR(255) NULL')
            cursor.execute('ALTER TABLE road_projects MODIFY vendor_id VARCHAR(255) NULL')

            # 2. ml_analysis table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS `ml_analysis` (
                `analysis_id` INT AUTO_INCREMENT PRIMARY KEY,
                `work_id` VARCHAR(50),
                `anomaly_score` DOUBLE DEFAULT 0,
                `anomaly_detected` TINYINT(1) DEFAULT 0,
                `model_name` VARCHAR(100) DEFAULT 'Isolation Forest',
                `analysis_date` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX (`work_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # 3. nlp_analysis table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS `nlp_analysis` (
                `similarity_id` INT AUTO_INCREMENT PRIMARY KEY,
                `work_id_1` VARCHAR(50),
                `work_id_2` VARCHAR(50),
                `similarity_score` DOUBLE DEFAULT 0,
                `similarity_status` VARCHAR(100),
                INDEX (`work_id_1`),
                INDEX (`work_id_2`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # 4. risk_analysis table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS `risk_analysis` (
                `risk_id` INT AUTO_INCREMENT PRIMARY KEY,
                `work_id` VARCHAR(50),
                `risk_score` DOUBLE DEFAULT 0,
                `risk_level` VARCHAR(20) DEFAULT 'LOW',
                `risk_reason` TEXT,
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX (`work_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # 5. users table (role-based access)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS `users` (
                `user_id` INT AUTO_INCREMENT PRIMARY KEY,
                `username` VARCHAR(50) NOT NULL UNIQUE,
                `password_hash` VARCHAR(255) NOT NULL,
                `full_name` VARCHAR(100),
                `role` VARCHAR(30) NOT NULL,
                `district` VARCHAR(100) NULL,
                `mp_id` VARCHAR(50) NULL,
                `vendor_id` VARCHAR(100) NULL,
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # 8. duplicate_analysis table (location-aware duplicate / overlap pairs)
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

            # 9. duplicate_summary table (counts of the latest duplicate check)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS `duplicate_summary` (
                `summary_id` INT AUTO_INCREMENT PRIMARY KEY,
                `metrics_json` LONGTEXT,
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            for username, pwd, full_name, role, district, mp_id, vendor_id in DEMO_USERS:
                cursor.execute(
                    "INSERT IGNORE INTO `users` "
                    "(username, password_hash, full_name, role, district, mp_id, vendor_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (username, generate_password_hash(pwd), full_name, role,
                     district, mp_id, vendor_id)
                )
            print("All required tables created successfully: "
                  "road_projects, ml_analysis, nlp_analysis, risk_analysis, users, "
                  "duplicate_analysis, duplicate_summary.")
            print("Demo login accounts ready (admin, admin_pune, ministry, auditor, vendor, citizen).")
        conn.commit()
    finally:
        conn.close()


if __name__ == '__main__':
    init_database()
