from db import get_db_connection

try:
    conn = get_db_connection()
    print("✅ Connected to MySQL Successfully!")

    conn.close()

except Exception as e:
    print("❌ Connection Failed")
    print(e)