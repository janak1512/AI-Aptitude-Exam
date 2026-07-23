"""
Migrate DB for company-based AI placement preparation.
Safe to run multiple times.
"""

from db import get_db_connection


def column_exists(cursor, table, column):
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (table, column),
    )
    return cursor.fetchone()[0] > 0


def table_exists(cursor, table):
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        """,
        (table,),
    )
    return cursor.fetchone()[0] > 0


def add_column_if_missing(cursor, table, column, definition):
    if not column_exists(cursor, table, column):
        cursor.execute(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}")
        print(f"  + Added {table}.{column}")
    else:
        print(f"  = {table}.{column} already exists")


def main():
    conn = get_db_connection()
    cursor = conn.cursor()

    print("Migrating company-based AI schema...")

    if not table_exists(cursor, "ai_questions"):
        cursor.execute(
            """
            CREATE TABLE ai_questions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                category_id INT NULL,
                company_name VARCHAR(100) NULL,
                topic VARCHAR(100) NULL,
                difficulty VARCHAR(20) NULL,
                question TEXT NOT NULL,
                option_a VARCHAR(500),
                option_b VARCHAR(500),
                option_c VARCHAR(500),
                option_d VARCHAR(500),
                correct_answer VARCHAR(500),
                explanation TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_ai_user_category (user_id, category_id),
                INDEX idx_ai_user_company (user_id, company_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        print("  + Created ai_questions")
    else:
        print("  = ai_questions already exists")
        add_column_if_missing(
            cursor, "ai_questions", "company_name", "VARCHAR(100) NULL AFTER category_id"
        )
        add_column_if_missing(
            cursor, "ai_questions", "topic", "VARCHAR(100) NULL AFTER company_name"
        )
        add_column_if_missing(
            cursor, "ai_questions", "difficulty", "VARCHAR(20) NULL AFTER topic"
        )
        cursor.execute("ALTER TABLE ai_questions MODIFY category_id INT NULL")
        print("  = ai_questions.category_id set nullable")

    if table_exists(cursor, "results"):
        add_column_if_missing(
            cursor, "results", "company_name", "VARCHAR(100) NULL AFTER category_id"
        )
        cursor.execute("ALTER TABLE results MODIFY category_id INT NULL")
        print("  = results.category_id set nullable")

    conn.commit()
    cursor.close()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
