from db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

categories = [
    ("Quantitative Aptitude", "Mathematics and numerical ability"),
    ("Logical Reasoning", "Logical and analytical thinking"),
    ("Verbal Ability", "English grammar and vocabulary"),
    ("Programming", "C, C++, Java, Python, SQL"),
    ("Data Interpretation", "Charts, graphs and tables"),
    ("Puzzle & Seating Arrangement", "Puzzle solving and arrangements")
]

for category in categories:
    cursor.execute(
        "SELECT id FROM categories WHERE category_name = %s",
        (category[0],)
    )

    if cursor.fetchone() is None:
        cursor.execute(
            """
            INSERT INTO categories (category_name, description)
            VALUES (%s, %s)
            """,
            category
        )

conn.commit()

print("✅ Categories Added Successfully!")

cursor.close()
conn.close()