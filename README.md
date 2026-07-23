# 🧠 AI Aptitude Exam System

> An AI-powered aptitude examination platform built using Flask, MySQL, and Google's Gemini AI.

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-3.1-black?logo=flask)
![MySQL](https://img.shields.io/badge/MySQL-Database-blue?logo=mysql)
![Gemini](https://img.shields.io/badge/Google-Gemini_AI-orange?logo=google)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 📖 About

AI Aptitude Exam System is an intelligent online aptitude examination platform that allows users to practice and take aptitude exams while receiving AI-powered explanations and guidance using Google's Gemini AI.

The system supports user authentication, category-wise practice, timed examinations, automatic result generation, AI-powered coaching, and performance analysis.

---

## ✨ Features

- 🔐 User Registration & Login
- 👤 User Profile
- 📝 Timed Aptitude Exams
- 📚 Category-wise Practice
- 🤖 AI Coach (Gemini AI)
- 📊 Performance Analysis
- 📈 Result Dashboard
- 📄 Detailed Exam Review
- 💾 MySQL Database
- 🎨 Modern Responsive UI

---

## 🛠️ Tech Stack

| Technology | Used |
|------------|------|
| Python | Backend |
| Flask | Web Framework |
| HTML5 | Frontend |
| CSS3 | Styling |
| JavaScript | Client Side |
| MySQL | Database |
| Gemini AI | AI Explanation |
| Bootstrap | UI Components |

---

## 📂 Project Structure

```text
AI-Aptitude-Exam/
│
├── app.py
├── db.py
├── requirements.txt
├── create_tables.py
├── sql/
├── data/
├── static/
│   ├── css/
│   └── js/
├── templates/
└── README.md
```

---

## ⚙️ Installation

### Clone Repository

```bash
git clone https://github.com/janak1512/AI-Aptitude-Exam.git
```

```bash
cd AI-Aptitude-Exam
```

### Create Virtual Environment

Windows

```bash
python -m venv venv
venv\Scripts\activate
```

Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 🔑 Environment Variables

Create a `.env` file.

```env
SECRET_KEY=your_secret_key

GEMINI_API_KEY=your_gemini_api_key

DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=ai_aptitude_exam
```

---

## 🗄️ Database Setup

Import the SQL file located inside the `sql` folder.

```
sql/ai_aptitude_exam.sql
```

---

## ▶️ Run Project

```bash
python app.py
```

Visit:

```
http://127.0.0.1:5000
```

---

## 📸 Screenshots

> Screenshots will be added soon.

---

## 🚀 Future Enhancements

- Admin Dashboard
- Leaderboard
- Question Difficulty Levels
- Email Verification
- Password Reset
- Certificate Generation
- Cloud Deployment

---

## 👨‍💻 Developer

**Janak**

Computer Science & Engineering Student

---

## 📄 License

This project is licensed under the MIT License.