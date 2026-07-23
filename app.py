from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify
)

from db import get_db_connection

import os
import json

from dotenv import load_dotenv
from google import genai

load_dotenv()

app = Flask(__name__)
app.secret_key = "ai_aptitude_exam"

# ==========================================================
# GEMINI AI
# ==========================================================

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

GEMINI_MODEL = "gemini-3.5-flash-lite"

# ==========================================================
# AI HELPERS (JSON parse, adaptive history, company pattern)
# ==========================================================


def parse_gemini_json(text):
    """Extract JSON array/object from Gemini response text."""
    if not text:
        raise ValueError("Empty Gemini response")

    cleaned = text.strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        # Drop opening ``` / ```json and closing ```
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    start_arr = cleaned.find("[")
    start_obj = cleaned.find("{")

    if start_arr == -1 and start_obj == -1:
        raise ValueError("No JSON found in Gemini response")

    if start_arr != -1 and (start_obj == -1 or start_arr < start_obj):
        end = cleaned.rfind("]")
        cleaned = cleaned[start_arr:end + 1]
    else:
        end = cleaned.rfind("}")
        cleaned = cleaned[start_obj:end + 1]

    return json.loads(cleaned)


def get_student_adaptive_context(cursor, user_id):
    """
    Build adaptive generation context from past results.
    Returns weak/strong topics, average %, and target difficulty.
    """
    cursor.execute(
        """
        SELECT
            COUNT(*) AS total_tests,
            AVG(percentage) AS average_score
        FROM results
        WHERE user_id=%s
        """,
        (user_id,),
    )
    perf = cursor.fetchone() or {}
    total_tests = perf.get("total_tests") or 0
    average_score = round(perf.get("average_score") or 0, 2)

    cursor.execute(
        """
        SELECT
            c.category_name,
            AVG(r.percentage) AS score
        FROM results r
        JOIN categories c ON r.category_id = c.id
        WHERE r.user_id=%s
          AND r.category_id IS NOT NULL
        GROUP BY c.category_name
        """,
        (user_id,),
    )
    category_rows = cursor.fetchall() or []

    weak_topics = []
    strong_topics = []
    category_report_lines = []

    for row in category_rows:
        name = row["category_name"]
        score = round(row["score"] or 0, 2)
        category_report_lines.append(f"{name}: {score}%")
        if score < 50:
            weak_topics.append(name)
        elif score >= 70:
            strong_topics.append(name)

    # Topic-level signal from recent company/AI questions (if available)
    cursor.execute(
        """
        SELECT topic, COUNT(*) AS cnt
        FROM ai_questions
        WHERE user_id=%s
          AND topic IS NOT NULL
          AND topic != ''
        GROUP BY topic
        ORDER BY cnt DESC
        LIMIT 8
        """,
        (user_id,),
    )
    recent_topics = [r["topic"] for r in (cursor.fetchall() or []) if r.get("topic")]

    if average_score < 50:
        difficulty = "Easy"
    elif average_score <= 80:
        difficulty = "Medium"
    else:
        difficulty = "Hard"

    # No history yet → start Medium
    if total_tests == 0:
        difficulty = "Medium"

    return {
        "total_tests": total_tests,
        "average_score": average_score,
        "weak_topics": weak_topics,
        "strong_topics": strong_topics,
        "category_report": "\n".join(category_report_lines) or "No category history yet",
        "recent_topics": recent_topics,
        "difficulty": difficulty,
    }


def analyze_company_pattern(company_name):
    """Ask Gemini to analyze placement pattern for ANY company name."""
    prompt = f"""
Company Name:
{company_name}

Analyze this company's placement preparation pattern.

Consider:
- Common aptitude rounds
- Technical rounds
- Coding assessment pattern
- Frequently asked topics
- Difficulty level
- Fresher hiring pattern

If company-specific information is unavailable:
Use general industry placement patterns based on the company type
(e.g. product company, IT services, consulting, startup, MNC).

Return a clear structured analysis covering focus areas for freshers.
Do NOT invent fake company facts. Prefer industry-typical patterns when unsure.
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    return (response.text or "").strip()


def generate_company_placement_questions(company_name, pattern_text, adaptive):
    """Generate 20 company-pattern MCQs with adaptive focus/difficulty."""
    weak = ", ".join(adaptive["weak_topics"]) or "None identified yet"
    strong = ", ".join(adaptive["strong_topics"]) or "None identified yet"
    recent = ", ".join(adaptive["recent_topics"]) or "None"
    difficulty = adaptive["difficulty"]

    focus_hint = ""
    if adaptive["weak_topics"]:
        focus_hint = (
            f"Student is weak in: {weak}. "
            "Generate MORE questions from these weak areas while still "
            "matching the company placement pattern."
        )
    else:
        focus_hint = (
            "Balance questions across the company's typical placement topics."
        )

    prompt = f"""
You are generating placement preparation MCQs for company hiring.

Company Name:
{company_name}

Company Placement Pattern Analysis:
{pattern_text}

Student Adaptive Context:
- Average score: {adaptive['average_score']}%
- Tests taken: {adaptive['total_tests']}
- Strong topics: {strong}
- Weak topics: {weak}
- Recent practice topics: {recent}
- Target difficulty for THIS set: {difficulty}

Adaptive rules:
- Below 50% overall → Easy questions
- 50-80% overall → Medium questions
- Above 80% overall → Hard questions
- {focus_hint}

Generate exactly 20 multiple choice questions suitable for {company_name} placement prep.

Each question must include:
- 4 options
- correct answer (use the full option text matching one of option_a/b/c/d)
- explanation
- topic name
- difficulty level (Easy / Medium / Hard — mostly {difficulty})
- company relevance (short note)

Return ONLY valid JSON array. No markdown. No extra text.

Format:
[
{{
"question":"",
"option_a":"",
"option_b":"",
"option_c":"",
"option_d":"",
"answer":"",
"topic":"",
"difficulty":"",
"explanation":"",
"company":"{company_name}"
}}
]
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    questions = parse_gemini_json(response.text)

    if not isinstance(questions, list) or len(questions) == 0:
        raise ValueError("Gemini did not return a question list")

    return questions


# ==========================================================
# HOME
# ==========================================================

@app.route('/')
def home():
    return render_template("index.html")


# ==========================================================
# REGISTER
# ==========================================================

@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        fullname = request.form['fullname']
        email = request.form['email']
        mobile = request.form['mobile']
        college = request.form['college']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            return "Passwords do not match!"

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM users WHERE email=%s",
            (email,)
        )

        user = cursor.fetchone()

        if user:
            conn.close()
            return "Email already exists!"

        cursor.execute("""
            INSERT INTO users
            (
                fullname,
                email,
                mobile,
                college,
                password
            )
            VALUES
            (%s,%s,%s,%s,%s)
        """, (
            fullname,
            email,
            mobile,
            college,
            password
        ))

        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("register.html")


# ==========================================================
# LOGIN
# ==========================================================

@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT *
            FROM users
            WHERE email=%s
            AND password=%s
        """, (
            email,
            password
        ))

        user = cursor.fetchone()

        conn.close()

        if user:

            session["user_id"] = user["id"]
            session["fullname"] = user["fullname"]

            return redirect("/dashboard")

        return "Invalid Email or Password"

    return render_template("login.html")


# ==========================================================
# DASHBOARD
# ==========================================================

@app.route('/dashboard')
def dashboard():

    if "user_id" not in session:
        return redirect("/login")


    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)


    user_id = session["user_id"]



    # ===============================
    # Categories
    # ===============================

    cursor.execute("""
        SELECT *
        FROM categories
        ORDER BY id
    """)

    categories = cursor.fetchall()



    # ===============================
    # Total Tests Taken
    # ===============================

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM results
        WHERE user_id=%s
    """,(user_id,))


    total_attempts = cursor.fetchone()["total"]




    # ===============================
    # Average Score
    # ===============================

    cursor.execute("""
        SELECT AVG(percentage) AS average
        FROM results
        WHERE user_id=%s
    """,(user_id,))


    avg_result = cursor.fetchone()["average"]


    average_score = round(avg_result,2) if avg_result else 0




    # ===============================
    # Best Score
    # ===============================

    cursor.execute("""
        SELECT MAX(percentage) AS best
        FROM results
        WHERE user_id=%s
    """,(user_id,))


    best_result = cursor.fetchone()["best"]

    best_score = round(best_result,2) if best_result else 0


    # ===============================
    # Accuracy
    # ===============================

    cursor.execute("""
        SELECT

            AVG(percentage) AS accuracy

        FROM results

        WHERE user_id=%s

    """,(user_id,))


    accuracy_result = cursor.fetchone()["accuracy"]


    accuracy = round(
        accuracy_result,2
    ) if accuracy_result else 0



    # ===============================
    # AI Rating
    # ===============================

    if average_score >= 90:

        ai_rating = "Excellent"


    elif average_score >= 75:

        ai_rating = "Very Good"


    elif average_score >= 60:

        ai_rating = "Good"


    else:

        ai_rating = "Needs Improvement"



    conn.close()



    return render_template(
        "dashboard.html",

        fullname=session["fullname"],

        categories=categories,

        total_attempts=total_attempts,

        average_score=average_score,

        best_score=best_score,

        accuracy=accuracy,

        ai_rating=ai_rating
    )

# ==========================================================
# INSTRUCTIONS
# ==========================================================

@app.route('/instructions/<int:category_id>')
def instructions(category_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM categories
        WHERE id=%s
    """, (
        category_id,
    ))

    category = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM questions
        WHERE category_id=%s
    """, (
        category_id,
    ))

    total = cursor.fetchone()

    conn.close()

    return render_template(
        "instructions.html",
        category=category,
        total_questions=total["total"]
    )


# ==========================================================
# START EXAM
# ==========================================================

@app.route('/start_exam/<int:category_id>')
def start_exam(category_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO exam_sessions
        (
            user_id,
            category_id,
            duration,
            status
        )
        VALUES
        (%s,%s,%s,%s)
    """, (
        session["user_id"],
        category_id,
        20,
        "IN_PROGRESS"
    ))

    conn.commit()

    session_id = cursor.lastrowid

    conn.close()

    return redirect(f"/exam/{session_id}/1")
# ==========================================================
# EXAM
# ==========================================================

@app.route("/exam/<int:session_id>/<int:question_no>")
def exam(session_id, question_no):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # -------------------------
    # Get Exam Session
    # -------------------------

    cursor.execute("""
        SELECT *
        FROM exam_sessions
        WHERE id=%s
    """, (session_id,))

    exam_session = cursor.fetchone()

    if not exam_session:
        conn.close()
        return "Exam session not found."

    category_id = exam_session["category_id"]

    # -------------------------
    # Get Questions
    # -------------------------

    cursor.execute("""
        SELECT *
        FROM questions
        WHERE category_id=%s
        ORDER BY id
    """, (category_id,))

    questions = cursor.fetchall()

    total_questions = len(questions)

    if total_questions == 0:
        conn.close()
        return "No questions available."

    # -------------------------
    # Validate Question Number
    # -------------------------

    if question_no < 1:
        question_no = 1

    if question_no > total_questions:
        question_no = total_questions

    # -------------------------
    # Current Question
    # -------------------------

    question = questions[question_no - 1]

    # -------------------------
    # Previously Selected Answer
    # -------------------------

    cursor.execute("""
        SELECT selected_option
        FROM user_answers
        WHERE exam_session_id=%s
        AND question_id=%s
    """, (
        session_id,
        question["id"]
    ))

    answer = cursor.fetchone()

    selected_option = None

    if answer:
        selected_option = answer["selected_option"]

    # -------------------------
    # Question Palette
    # -------------------------

    palette = []

    for q in questions:

        cursor.execute("""
            SELECT id
            FROM user_answers
            WHERE exam_session_id=%s
            AND question_id=%s
        """, (
            session_id,
            q["id"]
        ))

        answered = cursor.fetchone()

        palette.append({

            "number": len(palette) + 1,

            "question_id": q["id"],

            "answered": answered is not None

        })

    # -------------------------
    # Navigation
    # -------------------------

    previous_question = None
    next_question = None

    if question_no > 1:
        previous_question = question_no - 1

    if question_no < total_questions:
        next_question = question_no + 1

    # -------------------------
    # Progress
    # -------------------------

    answered_count = sum(
        1 for item in palette if item["answered"]
    )

    progress = int(
        (answered_count / total_questions) * 100
    )

    conn.close()

    return render_template(

        "exam.html",

        session_id=session_id,

        question=question,

        question_no=question_no,

        total_questions=total_questions,

        selected_option=selected_option,

        previous_question=previous_question,

        next_question=next_question,

        palette=palette,

        progress=progress
    )

# ==========================================================
# SAVE ANSWER & NAVIGATE
# ==========================================================

@app.route("/save_answer", methods=["POST"])
def save_answer():

    if "user_id" not in session:
        return redirect("/login")

    session_id = request.form["session_id"]
    question_id = request.form["question_id"]
    question_no = int(request.form["question_no"])

    action = request.form["action"]

    selected_option = request.form.get("selected_option")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # ------------------------------------
    # Check existing answer
    # ------------------------------------

    cursor.execute("""
        SELECT id
        FROM user_answers
        WHERE exam_session_id=%s
        AND question_id=%s
    """, (
        session_id,
        question_id
    ))

    answer = cursor.fetchone()

    # ------------------------------------
    # Update existing answer
    # ------------------------------------

    if answer:

        cursor.execute("""
            UPDATE user_answers
            SET selected_option=%s
            WHERE id=%s
        """, (
            selected_option,
            answer["id"]
        ))

    # ------------------------------------
    # Insert new answer
    # ------------------------------------

    else:

        cursor.execute("""
            INSERT INTO user_answers
            (
                exam_session_id,
                question_id,
                selected_option,
                is_correct
            )
            VALUES
            (%s,%s,%s,%s)
        """, (
            session_id,
            question_id,
            selected_option,
            0
        ))

    conn.commit()

    # ------------------------------------
    # Total Questions
    # ------------------------------------

    cursor.execute("""
        SELECT category_id
        FROM exam_sessions
        WHERE id=%s
    """, (
        session_id,
    ))

    exam = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*) total
        FROM questions
        WHERE category_id=%s
    """, (
        exam["category_id"],
    ))

    total = cursor.fetchone()["total"]

    conn.close()

    # ------------------------------------
    # Navigation
    # ------------------------------------

    if action == "previous":

        question_no -= 1

        if question_no < 1:
            question_no = 1

        return redirect(
            f"/exam/{session_id}/{question_no}"
        )

    elif action == "next":

        question_no += 1

        if question_no > total:
            question_no = total

        return redirect(
            f"/exam/{session_id}/{question_no}"
        )

    elif action == "palette":

        goto = int(request.form["goto"])

        return redirect(
            f"/exam/{session_id}/{goto}"
        )

    elif action == "submit":

        return redirect(
            f"/submit_exam/{session_id}"
        )

    return redirect(
        f"/exam/{session_id}/{question_no}"
    )
# ==========================================================
# SUBMIT EXAM
# ==========================================================

@app.route("/submit_exam/<int:session_id>")
def submit_exam(session_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # ------------------------------------
    # Get Exam Session
    # ------------------------------------

    cursor.execute("""
        SELECT *
        FROM exam_sessions
        WHERE id=%s
    """, (session_id,))

    exam = cursor.fetchone()

    if not exam:
        conn.close()
        return "Exam session not found."

    user_id = exam["user_id"]
    category_id = exam["category_id"]

    # ------------------------------------
    # Get All Questions
    # ------------------------------------

    cursor.execute("""
        SELECT *
        FROM questions
        WHERE category_id=%s
        ORDER BY id
    """, (category_id,))

    questions = cursor.fetchall()

    total_questions = len(questions)

    score = 0
    wrong = 0

    # ------------------------------------
    # Check Every Answer
    # ------------------------------------

    for q in questions:

        cursor.execute("""
            SELECT *
            FROM user_answers
            WHERE exam_session_id=%s
            AND question_id=%s
        """, (
            session_id,
            q["id"]
        ))

        answer = cursor.fetchone()

        is_correct = 0

        if answer:

            if answer["selected_option"] == q["correct_answer"]:
                is_correct = 1
                score += 1
            else:
                wrong += 1

            cursor.execute("""
                UPDATE user_answers
                SET is_correct=%s
                WHERE id=%s
            """, (
                is_correct,
                answer["id"]
            ))

        else:
            wrong += 1

    # ------------------------------------
    # Percentage
    # ------------------------------------

    if total_questions == 0:
        percentage = 0
    else:
        percentage = round(
            (score / total_questions) * 100,
            2
        )

    # ------------------------------------
    # Save Result
    # ------------------------------------

    cursor.execute("""
        INSERT INTO results
        (
            user_id,
            category_id,
            total_questions,
            correct_answers,
            wrong_answers,
            score,
            percentage,
            time_taken
        )
        VALUES
        (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        user_id,
        category_id,
        total_questions,
        score,
        wrong,
        score,
        percentage,
        exam["duration"]
    ))

    conn.commit()

    result_id = cursor.lastrowid

    # ------------------------------------
    # Link Answers With Result
    # ------------------------------------

    cursor.execute("""
        UPDATE user_answers
        SET result_id=%s
        WHERE exam_session_id=%s
    """, (
        result_id,
        session_id
    ))

    # ------------------------------------
    # Complete Session
    # ------------------------------------

    cursor.execute("""
        UPDATE exam_sessions
        SET
            status='COMPLETED',
            end_time=NOW()
        WHERE id=%s
    """, (
        session_id,
    ))

    conn.commit()

    conn.close()

    return redirect(f"/result/{result_id}")
# ==========================================================
# RESULT
# ==========================================================

@app.route("/result/<int:result_id>")
def result(result_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get Result
    cursor.execute("""
        SELECT
            r.*,
            c.category_name
        FROM results r
        LEFT JOIN categories c
        ON r.category_id = c.id
        WHERE r.id=%s
    """, (result_id,))

    result = cursor.fetchone()

    if not result:
        conn.close()
        return "Result not found."

    conn.close()

    return render_template(
        "result.html",
        result=result
    )
# ==========================================================
# REVIEW ANSWERS
# ==========================================================

@app.route("/review/<int:result_id>")
def review_answers(result_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Result Information
    cursor.execute("""
        SELECT *
        FROM results
        WHERE id=%s
    """, (result_id,))

    result = cursor.fetchone()

    if not result:
        conn.close()
        return "Result not found."

    # All Questions
    cursor.execute("""
        SELECT
            q.id,
            q.question,
            q.option_a,
            q.option_b,
            q.option_c,
            q.option_d,
            q.correct_answer,
            q.explanation,
            ua.selected_option,
            ua.is_correct
        FROM questions q
        LEFT JOIN user_answers ua
            ON ua.question_id = q.id
            AND ua.result_id = %s
        WHERE q.category_id = %s
        ORDER BY q.id
    """, (
        result_id,
        result["category_id"]
    ))

    review = cursor.fetchall()

    conn.close()

    return render_template(
        "review.html",
        result=result,
        review=review
    )
# ==========================================================
# AI REPORT
# ==========================================================

@app.route("/ai_report/<int:result_id>")
def ai_report(result_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # --------------------------------------------------
    # RESULT DETAILS
    # --------------------------------------------------

    cursor.execute("""
        SELECT
            r.*,
            c.category_name
        FROM results r
        JOIN categories c
            ON c.id = r.category_id
        WHERE r.id = %s
    """, (result_id,))

    result = cursor.fetchone()

    if not result:
        cursor.close()
        conn.close()
        flash("Result not found.", "danger")
        return redirect(("/dashboard"))

    percentage = float(result["percentage"])

    # --------------------------------------------------
    # AI ANALYSIS
    # --------------------------------------------------

    if percentage >= 90:

        readiness = "Excellent"

        strengths = [
            "Excellent logical thinking",
            "Strong problem solving ability",
            "High accuracy",
            "Fast decision making"
        ]

        weaknesses = [
            "No major weaknesses detected"
        ]

        recommendations = [
            "Continue solving advanced aptitude questions.",
            "Practice competitive coding.",
            "Maintain your consistency."
        ]

        ai_summary = (
            "Outstanding performance! You demonstrate excellent aptitude "
            "skills and are highly prepared for placement assessments."
        )

    elif percentage >= 75:

        readiness = "Very Good"

        strengths = [
            "Good understanding of aptitude",
            "Strong analytical skills",
            "Consistent performance"
        ]

        weaknesses = [
            "Needs improvement in difficult questions",
            "Increase solving speed"
        ]

        recommendations = [
            "Practice medium and hard questions daily.",
            "Take weekly mock tests.",
            "Improve time management."
        ]

        ai_summary = (
            "Very good performance. Continue practicing to achieve "
            "excellent placement readiness."
        )

    elif percentage >= 60:

        readiness = "Good"

        strengths = [
            "Basic concepts are clear",
            "Good reasoning ability"
        ]

        weaknesses = [
            "Accuracy needs improvement",
            "Calculation speed is average"
        ]

        recommendations = [
            "Solve previous placement papers.",
            "Practice under time limits.",
            "Review incorrect answers."
        ]

        ai_summary = (
            "Good attempt. Your fundamentals are clear but improving "
            "speed and accuracy will increase your overall performance."
        )

    elif percentage >= 40:

        readiness = "Average"

        strengths = [
            "Can solve easy questions"
        ]

        weaknesses = [
            "Logical reasoning",
            "Calculation speed",
            "Accuracy"
        ]

        recommendations = [
            "Revise aptitude fundamentals.",
            "Practice every day.",
            "Take weekly mock tests."
        ]

        ai_summary = (
            "Average performance. Consistent practice will significantly "
            "improve your aptitude skills."
        )

    else:

        readiness = "Needs Improvement"

        strengths = [
            "Shows willingness to attempt questions"
        ]

        weaknesses = [
            "Core aptitude concepts",
            "Accuracy",
            "Speed"
        ]

        recommendations = [
            "Start from basic aptitude topics.",
            "Solve easy questions first.",
            "Practice topic-wise before mock tests."
        ]

        ai_summary = (
            "Your aptitude fundamentals need improvement. Focus on basic "
            "concepts and regular practice."
        )

    # --------------------------------------------------
    # CATEGORY PERFORMANCE
    # --------------------------------------------------

    category_scores = [
        {
            "category": result["category_name"],
            "percentage": percentage
        }
    ]

    # --------------------------------------------------
    # SAVE AI REPORT
    # --------------------------------------------------

    strengths_db = ", ".join(strengths)
    weaknesses_db = ", ".join(weaknesses)
    recommendations_db = "\n".join(recommendations)

    cursor.execute("""
        SELECT id
        FROM ai_analysis
        WHERE user_id=%s
    """, (session["user_id"],))

    existing = cursor.fetchone()

    if existing:

        cursor.execute("""
            UPDATE ai_analysis
            SET
                strengths=%s,
                weak_topics=%s,
                ai_suggestion=%s
            WHERE user_id=%s
        """, (
            strengths_db,
            weaknesses_db,
            recommendations_db,
            session["user_id"]
        ))

    else:

        cursor.execute("""
            INSERT INTO ai_analysis
            (
                user_id,
                strengths,
                weak_topics,
                ai_suggestion
            )
            VALUES
            (%s,%s,%s,%s)
        """, (
            session["user_id"],
            strengths_db,
            weaknesses_db,
            recommendations_db
        ))

    conn.commit()

    cursor.close()
    conn.close()

    # --------------------------------------------------
    # SEND DATA TO TEMPLATE
    # --------------------------------------------------

    return render_template(
        "ai_report.html",
        result=result,
        readiness=readiness,
        strengths=strengths,
        weaknesses=weaknesses,
        recommendations=recommendations,
        category_scores=category_scores,
        ai_summary=ai_summary
    )

# ==========================================================
# STUDENT MENU ROUTES
# ==========================================================

# ==========================================================
# PRACTICE
# ==========================================================

@app.route("/practice")
def practice():

    if "user_id" not in session:
        return redirect("/login")


    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)



    # Fetch Categories

    cursor.execute("""
        SELECT *
        FROM categories
        ORDER BY id
    """)


    categories = cursor.fetchall()



    conn.close()



    return render_template(
        "practice.html",
        fullname=session["fullname"],
        categories=categories
    )



# ==========================================================
# AI QUESTION GENERATOR
# ==========================================================


@app.route("/generate_ai_test/<int:category_id>")
def generate_ai_test(category_id):


    if "user_id" not in session:
        return redirect("/login")



    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)



    cursor.execute("""
        SELECT category_name
        FROM categories
        WHERE id=%s
    """,(category_id,))


    category = cursor.fetchone()

    if not category:
        conn.close()
        flash("Category not found.")
        return redirect(url_for("practice"))

    user_id = session["user_id"]
    adaptive = get_student_adaptive_context(cursor, user_id)
    difficulty = adaptive["difficulty"]

    prompt = f"""

Generate 20 multiple choice aptitude questions.

Category:
{category['category_name']}

Student adaptive context:
- Average score: {adaptive['average_score']}%
- Weak topics: {', '.join(adaptive['weak_topics']) or 'None'}
- Target difficulty: {difficulty}

Return ONLY JSON.

Format:

[
{{
"question":"",
"option_a":"",
"option_b":"",
"option_c":"",
"option_d":"",
"answer":"",
"topic":"",
"difficulty":"",
"explanation":""
}}
]

Difficulty:
{difficulty}


"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        questions = parse_gemini_json(response.text)
    except Exception as e:
        conn.close()
        print("AI GENERATE ERROR:", e)
        flash("Could not generate AI questions. Please try again.")
        return redirect(url_for("practice"))



    for q in questions:


        cursor.execute("""

        INSERT INTO ai_questions

        (
        user_id,
        category_id,
        company_name,
        topic,
        difficulty,
        question,
        option_a,
        option_b,
        option_c,
        option_d,
        correct_answer,
        explanation
        )

        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)

        """,

        (
        user_id,
        category_id,
        None,
        q.get("topic") or category["category_name"],
        q.get("difficulty") or difficulty,
        q["question"],
        q["option_a"],
        q["option_b"],
        q["option_c"],
        q["option_d"],
        q["answer"],
        q.get("explanation", "")
        ))



    conn.commit()


    conn.close()

    session.pop("ai_exam_company", None)
    session["ai_exam_mode"] = "category"



    return redirect(
        url_for(
            "ai_exam",
            category_id=category_id
        )
    )


# ==========================================================
# COMPANY-BASED AI PLACEMENT PRACTICE
# ==========================================================


@app.route("/company_practice", methods=["GET", "POST"])
def company_practice():
    """
    Company selection before AI test.
    Accepts ANY company name (free text — not limited to a dropdown).
    """

    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":
        company_name = (request.form.get("company_name") or "").strip()

        if not company_name:
            flash("Please enter a target company name.")
            return redirect(url_for("company_practice"))

        if len(company_name) > 100:
            flash("Company name is too long (max 100 characters).")
            return redirect(url_for("company_practice"))

        try:
            pattern_text = analyze_company_pattern(company_name)
        except Exception as e:
            print("COMPANY PATTERN ERROR:", e)
            flash("Could not analyze company pattern. Please try again.")
            return redirect(url_for("company_practice"))

        session["target_company"] = company_name
        session["company_pattern"] = pattern_text

        return render_template(
            "company_practice.html",
            fullname=session.get("fullname"),
            company_name=company_name,
            pattern_text=pattern_text,
            analyzed=True,
        )

    # Recent companies practiced by this user (dynamic suggestions, not hardcoded)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT company_name, MAX(id) AS last_id
        FROM ai_questions
        WHERE user_id=%s
          AND company_name IS NOT NULL
          AND company_name != ''
        GROUP BY company_name
        ORDER BY last_id DESC
        LIMIT 8
        """,
        (session["user_id"],),
    )
    recent_companies = [r["company_name"] for r in (cursor.fetchall() or [])]
    conn.close()

    return render_template(
        "company_practice.html",
        fullname=session.get("fullname"),
        company_name=session.get("target_company", ""),
        pattern_text=None,
        analyzed=False,
        recent_companies=recent_companies,
    )


@app.route("/generate_company_test", methods=["POST"])
def generate_company_test():
    """Generate adaptive company-pattern questions via Gemini."""

    if "user_id" not in session:
        return redirect("/login")

    company_name = (request.form.get("company_name") or session.get("target_company") or "").strip()
    pattern_text = request.form.get("pattern_text") or session.get("company_pattern") or ""

    if not company_name:
        flash("Please enter a target company first.")
        return redirect(url_for("company_practice"))

    user_id = session["user_id"]
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        if not pattern_text:
            pattern_text = analyze_company_pattern(company_name)
            session["company_pattern"] = pattern_text

        adaptive = get_student_adaptive_context(cursor, user_id)
        questions = generate_company_placement_questions(
            company_name, pattern_text, adaptive
        )

        for q in questions:
            cursor.execute(
                """
                INSERT INTO ai_questions
                (
                    user_id,
                    category_id,
                    company_name,
                    topic,
                    difficulty,
                    question,
                    option_a,
                    option_b,
                    option_c,
                    option_d,
                    correct_answer,
                    explanation
                )
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    user_id,
                    None,
                    q.get("company") or company_name,
                    q.get("topic") or "Placement Aptitude",
                    q.get("difficulty") or adaptive["difficulty"],
                    q["question"],
                    q["option_a"],
                    q["option_b"],
                    q["option_c"],
                    q["option_d"],
                    q["answer"],
                    q.get("explanation", ""),
                ),
            )

        conn.commit()

        session["target_company"] = company_name
        session["company_pattern"] = pattern_text
        session["ai_exam_company"] = company_name
        session["ai_exam_mode"] = "company"

    except Exception as e:
        conn.rollback()
        conn.close()
        print("COMPANY GENERATE ERROR:", e)
        flash("Could not generate company questions. Please try again.")
        return redirect(url_for("company_practice"))

    conn.close()
    return redirect(url_for("ai_company_exam"))

# ==========================================================
# AI EXAM PAGE (category-based — existing)
# ==========================================================

@app.route("/ai_exam/<int:category_id>")
def ai_exam(category_id):


    if "user_id" not in session:
        return redirect("/login")


    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)


    user_id = session["user_id"]



    cursor.execute("""
        SELECT *

        FROM ai_questions

        WHERE user_id=%s

        AND category_id=%s

        ORDER BY id DESC

        LIMIT 20

    """,
    (
        user_id,
        category_id
    ))



    questions = cursor.fetchall()



    conn.close()



    return render_template(

        "ai_exam.html",

        questions=questions,

        company_name=None,

        exam_title="AI Practice Test",

        exam_subtitle="Questions generated by Gemini — select one option for each question."

    )


# ==========================================================
# AI COMPANY EXAM PAGE
# ==========================================================

@app.route("/ai_company_exam")
def ai_company_exam():

    if "user_id" not in session:
        return redirect("/login")

    company_name = session.get("ai_exam_company") or session.get("target_company")

    if not company_name:
        flash("Select a company to start company AI practice.")
        return redirect(url_for("company_practice"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session["user_id"]

    cursor.execute(
        """
        SELECT *
        FROM ai_questions
        WHERE user_id=%s
          AND company_name=%s
        ORDER BY id DESC
        LIMIT 20
        """,
        (user_id, company_name),
    )
    questions = cursor.fetchall()
    conn.close()

    if not questions:
        flash("No company questions found. Generate a test first.")
        return redirect(url_for("company_practice"))

    return render_template(
        "ai_exam.html",
        questions=questions,
        company_name=company_name,
        exam_title=f"{company_name} Placement Test",
        exam_subtitle=f"AI-generated questions matched to {company_name} placement pattern.",
    )

# ==========================================================
# SUBMIT AI EXAM
# ==========================================================

@app.route("/submit_ai_exam", methods=["POST"])
def submit_ai_exam():


    if "user_id" not in session:
        return redirect("/login")



    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)



    user_id = session["user_id"]



    # Get submitted answers

    answers = request.form



    correct = 0

    total = 0



    question_ids = []



    # ===============================
    # Check Answers
    # ===============================

    for key, value in answers.items():


        if key.startswith("q"):


            question_id = key.replace("q","")


            question_ids.append(question_id)



            cursor.execute("""

                SELECT correct_answer

                FROM ai_questions

                WHERE id=%s

            """,(question_id,))



            question = cursor.fetchone()



            total += 1



            if question:


                if question["correct_answer"] == value:

                    correct += 1





    # ===============================
    # Calculate Percentage
    # ===============================


    percentage = 0


    if total > 0:

        percentage = round(
            (correct / total) * 100,
            2
        )





    # ===============================
    # Get Category / Company meta
    # ===============================

    category_id = None
    company_name = None

    if question_ids:

        cursor.execute("""

            SELECT category_id, company_name

            FROM ai_questions

            WHERE id=%s

        """,(question_ids[0],))



        meta = cursor.fetchone() or {}

        category_id = meta.get("category_id")
        company_name = meta.get("company_name")





    # ===============================
    # Save Result
    # ===============================


    cursor.execute("""

        INSERT INTO results

        (
        user_id,
        category_id,
        company_name,
        score,
        percentage,
        total_questions,
        correct_answers
        )

        VALUES(%s,%s,%s,%s,%s,%s,%s)

    """,
    (
    user_id,
    category_id,
    company_name,
    correct,
    percentage,
    total,
    correct
    ))





    conn.commit()



    conn.close()

    if company_name:
        session["target_company"] = company_name




    return render_template(

        "ai_result.html",

        score=correct,

        total=total,

        percentage=percentage,

        company_name=company_name

    )

# ==========================================================
# AI COACH
# ==========================================================

@app.route("/ai_coach")
def ai_coach():

    if "user_id" not in session:
        return redirect("/login")


    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)


    user_id = session["user_id"]




    # ===============================
    # Get AI Analysis
    # ===============================

    cursor.execute("""
        SELECT *
        FROM ai_analysis
        WHERE user_id=%s
        ORDER BY id DESC
        LIMIT 1
    """,(user_id,))


    analysis = cursor.fetchone()



    # ===============================
    # Performance Data
    # ===============================

    cursor.execute("""
        SELECT

            COUNT(*) AS total,

            AVG(percentage) AS average

        FROM results

        WHERE user_id=%s

    """,(user_id,))


    performance = cursor.fetchone()



    tests_taken = performance["total"]



    average_score = round(
        performance["average"],2
    ) if performance["average"] else 0





    # ===============================
    # Accuracy
    # ===============================

    cursor.execute("""
        SELECT

            AVG(percentage) AS accuracy

        FROM results

        WHERE user_id=%s

    """,(user_id,))


    accuracy_result = cursor.fetchone()["accuracy"]



    accuracy = round(
        accuracy_result,2
    ) if accuracy_result else 0





    # ===============================
    # AI Rating
    # ===============================

    if average_score >= 90:

        level = "Excellent"


    elif average_score >= 75:

        level = "Very Good"


    elif average_score >= 60:

        level = "Good"


    elif average_score >= 40:

        level = "Average"


    else:

        level = "Needs Improvement"

    # Target company (session or latest company attempt)
    target_company = session.get("target_company")

    if not target_company:
        cursor.execute(
            """
            SELECT company_name
            FROM results
            WHERE user_id=%s
              AND company_name IS NOT NULL
              AND company_name != ''
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        if row:
            target_company = row["company_name"]

    adaptive = get_student_adaptive_context(cursor, user_id)

    conn.close()

    return render_template(

        "ai_coach.html",


        level=level,


        tests_taken=tests_taken,


        average_score=average_score,


        accuracy=accuracy,



        strengths=
        analysis["strengths"]
        if analysis else
        (", ".join(adaptive["strong_topics"]) if adaptive["strong_topics"] else "No analysis available"),



        weakness=
        analysis["weak_topics"]
        if analysis else
        (", ".join(adaptive["weak_topics"]) if adaptive["weak_topics"] else "No weak topics available"),



        suggestion=
        analysis["ai_suggestion"]
        if analysis else
        "Complete exams to get AI suggestions",

        target_company=target_company,

    )

# ==========================================================
# AI CHATBOT API
# ==========================================================

@app.route("/ai_chat", methods=["POST"])
def ai_chat():


    if "user_id" not in session:

        return jsonify({
            "reply":"Please login first."
        })



    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)



    user_id = session["user_id"]



    data = request.get_json() or {}

    user_message = data.get("message")
    requested_company = (data.get("company") or "").strip()



    try:


        # ===============================
        # Get Student Performance
        # ===============================


        cursor.execute("""
            SELECT

                COUNT(*) AS total_tests,

                AVG(percentage) AS average_score,

                MAX(percentage) AS best_score


            FROM results

            WHERE user_id=%s

        """,(user_id,))



        performance = cursor.fetchone()



        total_tests = performance["total_tests"]



        average_score = round(
            performance["average_score"],2
        ) if performance["average_score"] else 0



        best_score = round(
            performance["best_score"],2
        ) if performance["best_score"] else 0






        # ===============================
        # Category Wise Performance
        # ===============================


        cursor.execute("""
            SELECT

                c.category_name,

                AVG(r.percentage) AS score


            FROM results r


            JOIN categories c

            ON r.category_id=c.id


            WHERE r.user_id=%s
              AND r.category_id IS NOT NULL


            GROUP BY c.category_name

        """,(user_id,))



        categories = cursor.fetchall()



        category_report = ""


        for item in categories:


            category_report += f"""

{item['category_name']} :
{round(item['score'],2)}%

"""

        adaptive = get_student_adaptive_context(cursor, user_id)

        target_company = requested_company or session.get("target_company")

        if not target_company:
            cursor.execute(
                """
                SELECT company_name
                FROM results
                WHERE user_id=%s
                  AND company_name IS NOT NULL
                  AND company_name != ''
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            if row:
                target_company = row["company_name"]

        company_report = ""
        if target_company:
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS attempts,
                    AVG(percentage) AS avg_score,
                    MAX(percentage) AS best_score
                FROM results
                WHERE user_id=%s
                  AND company_name=%s
                """,
                (user_id, target_company),
            )
            cperf = cursor.fetchone() or {}
            company_report = f"""
Target Company: {target_company}
Company attempts: {cperf.get('attempts') or 0}
Company average: {round(cperf.get('avg_score') or 0, 2)}%
Company best: {round(cperf.get('best_score') or 0, 2)}%
"""
            if (
                session.get("target_company") == target_company
                and session.get("company_pattern")
            ):
                company_report += (
                    "\nKnown placement pattern notes:\n"
                    f"{session.get('company_pattern')[:1200]}\n"
                )




        # ===============================
        # Gemini AI
        # ===============================


        response = client.models.generate_content(


            model=GEMINI_MODEL,



            contents=f"""


You are an AI Placement Coach for an Aptitude Exam Preparation Platform.



Student Performance:



Total Tests Attempted:

{total_tests}



Average Score:

{average_score}%



Best Score:

{best_score}%



Category Performance:

{category_report or 'No category history yet'}



Strengths:
{', '.join(adaptive['strong_topics']) or 'Not enough data'}

Weak topics:
{', '.join(adaptive['weak_topics']) or 'Not enough data'}

{company_report or 'No target company selected yet.'}



Student Question:

{user_message}




Instructions:


- Analyze student performance before answering.
- If the student asks about a company (any company name), give company-pattern based preparation advice.
- Use target company context when available.
- Mention strengths and weak areas clearly.
- Recommend a concrete preparation strategy (topics + order + difficulty).
- Keep answers simple and student friendly.
- Do not give generic advice.
- Example tone: "Based on IBM placement pattern and your previous performance..."


"""

        )



        return jsonify({


            "reply": response.text


        })




    except Exception as e:


        print("AI ERROR:",e)



        return jsonify({


            "reply":"AI service unavailable."


        })



    finally:


        conn.close()

# ==========================================================
# RESULTS HISTORY
# ==========================================================

@app.route("/results")
def results():

    if "user_id" not in session:
        return redirect("/login")


    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)


    user_id = session["user_id"]



    # ===============================
    # Exam History
    # ===============================

    cursor.execute("""
        SELECT
            r.*,
            c.category_name

        FROM results r

        LEFT JOIN categories c
        ON r.category_id = c.id

        WHERE r.user_id=%s

        ORDER BY r.id DESC

    """,(user_id,))


    results = cursor.fetchall()

    # ===============================
    # Summary
    # ===============================


    cursor.execute("""
        SELECT

            COUNT(*) AS total,

            AVG(percentage) AS average,

            MAX(percentage) AS best


        FROM results

        WHERE user_id=%s

    """,(user_id,))


    summary = cursor.fetchone()



    total_attempts = summary["total"]


    average_score = round(
        summary["average"],2
    ) if summary["average"] else 0



    best_score = round(
        summary["best"],2
    ) if summary["best"] else 0





    conn.close()



    return render_template(

        "results.html",

        results=results,

        total_attempts=total_attempts,

        average_score=average_score,

        best_score=best_score

    )

# ==========================================================
# PROFILE
# ==========================================================

@app.route("/profile")
def profile():

    if "user_id" not in session:
        return redirect("/login")


    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)


    user_id = session["user_id"]



    # ===============================
    # User Information
    # ===============================

    cursor.execute("""
        SELECT *
        FROM users
        WHERE id=%s
    """,(user_id,))


    user = cursor.fetchone()



    # ===============================
    # User Statistics
    # ===============================

    cursor.execute("""
        SELECT

            COUNT(*) AS total_tests,

            AVG(percentage) AS average_score,

            MAX(percentage) AS best_score


        FROM results

        WHERE user_id=%s

    """,(user_id,))


    stats = cursor.fetchone()



    total_tests = stats["total_tests"]


    average_score = round(
        stats["average_score"],2
    ) if stats["average_score"] else 0



    best_score = round(
        stats["best_score"],2
    ) if stats["best_score"] else 0




    conn.close()



    return render_template(

        "profile.html",

        user=user,

        total_tests=total_tests,

        average_score=average_score,

        best_score=best_score

    )

# ==========================================================
# EDIT PROFILE
# ==========================================================

@app.route("/edit_profile", methods=["GET","POST"])
def edit_profile():


    if "user_id" not in session:
        return redirect("/login")



    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)



    user_id = session["user_id"]



    if request.method == "POST":


        fullname = request.form["fullname"]

        email = request.form["email"]

        mobile = request.form["mobile"]

        college = request.form["college"]



        cursor.execute("""

            UPDATE users

            SET

            fullname=%s,

            email=%s,

            mobile=%s,

            college=%s


            WHERE id=%s


        """,
        (
            fullname,

            email,

            mobile,

            college,

            user_id
        ))



        conn.commit()



        # ===============================
        # Update Session Data
        # ===============================

        session["fullname"] = fullname

        session["email"] = email



        conn.close()



        return redirect("/profile")





    # ===============================
    # Load User Data
    # ===============================

    cursor.execute("""

        SELECT *

        FROM users

        WHERE id=%s


    """,
    (user_id,))



    user = cursor.fetchone()



    conn.close()



    return render_template(

        "edit_profile.html",

        user=user

    )

# ==========================================================
# LOGOUT
# ==========================================================

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ==========================================================
# RUN APP
# ==========================================================

if __name__ == "__main__":
    print("Starting Flask server...")
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )