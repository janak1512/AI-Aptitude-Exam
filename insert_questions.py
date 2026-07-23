import os
import pandas as pd
from db import get_db_connection

# Connect to MySQL
conn = get_db_connection()
cursor = conn.cursor()

# CSV file -> Category ID
categories = {
    "quantitative.csv": 1,
    "logical.csv": 2,
    "verbal.csv": 3,
    "programming.csv": 4,
    "data_interpretation.csv": 5,
    "puzzle.csv": 6
}

print("\n===== Importing Questions =====\n")

for file_name, category_id in categories.items():

    file_path = os.path.join("data", file_name)

    # Skip if file doesn't exist
    if not os.path.exists(file_path):
        print(f"⚠ {file_name} not found. Skipping...\n")
        continue

    try:
        df = pd.read_csv(file_path)

        inserted = 0
        skipped = 0

        for _, row in df.iterrows():

            # Check if question already exists
            cursor.execute(
                "SELECT id FROM questions WHERE question=%s",
                (row["question"],)
            )

            if cursor.fetchone():
                skipped += 1
                continue

            cursor.execute("""
                INSERT INTO questions (
                    category_id,
                    question,
                    option_a,
                    option_b,
                    option_c,
                    option_d,
                    correct_answer,
                    explanation,
                    difficulty,
                    marks
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                category_id,
                row["question"],
                row["option_a"],
                row["option_b"],
                row["option_c"],
                row["option_d"],
                row["correct_answer"],
                row["explanation"],
                row["difficulty"],
                row["marks"]
            ))

            inserted += 1

        conn.commit()

        print(f"✅ {file_name}")
        print(f"   Imported : {inserted}")
        print(f"   Skipped  : {skipped}\n")

    except Exception as e:
        print(f"❌ Error in {file_name}")
        print(e)
        print()

cursor.close()
conn.close()

print("=================================")
print("🎉 Question Import Completed!")
print("=================================")