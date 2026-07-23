from db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# USERS TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fullname VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    mobile VARCHAR(15),
    college VARCHAR(150),
    password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# CATEGORIES TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL,
    description TEXT
)
""")

# QUESTIONS TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT,
    question TEXT NOT NULL,
    option_a VARCHAR(255),
    option_b VARCHAR(255),
    option_c VARCHAR(255),
    option_d VARCHAR(255),
    correct_answer CHAR(1),
    difficulty ENUM('Easy','Medium','Hard') DEFAULT 'Easy',

    FOREIGN KEY(category_id)
    REFERENCES categories(id)
    ON DELETE CASCADE
)
""")

# RESULTS TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    category_id INT,
    score INT,
    total_questions INT,
    percentage FLOAT,
    exam_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(user_id)
    REFERENCES users(id)
    ON DELETE CASCADE,

    FOREIGN KEY(category_id)
    REFERENCES categories(id)
    ON DELETE CASCADE
)
""")

# AI ANALYSIS TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS ai_analysis (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    weak_topics TEXT,
    strengths TEXT,
    ai_suggestion TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(user_id)
    REFERENCES users(id)
    ON DELETE CASCADE
)
""")

# AI QUESTIONS TABLE (category-based + company-based)
cursor.execute("""
CREATE TABLE IF NOT EXISTS ai_questions (
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

    FOREIGN KEY(user_id)
    REFERENCES users(id)
    ON DELETE CASCADE,

    FOREIGN KEY(category_id)
    REFERENCES categories(id)
    ON DELETE SET NULL
)
""")

# Ensure results supports optional company + nullable category
try:
    cursor.execute("""
        ALTER TABLE results
        ADD COLUMN company_name VARCHAR(100) NULL AFTER category_id
    """)
except Exception:
    pass

try:
    cursor.execute("ALTER TABLE results MODIFY category_id INT NULL")
except Exception:
    pass

conn.commit()

print("✅ All Tables Created Successfully!")

cursor.close()
conn.close()