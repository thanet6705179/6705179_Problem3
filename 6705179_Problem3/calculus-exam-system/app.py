import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from google import genai
from google.genai import types

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "calculus-exam-secret-key-2026")

# ค่า Room Code สำหรับเข้าใช้งาน (ค่าเริ่มต้นคือ 1234)
ROOM_CODE = os.environ.get("ROOM_CODE", "1234")

# ตั้งค่า Gemma AI Client
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# หน่วยความจำเก็บคะแนนและคำตอบนักเรียนสำหรับอาจารย์ (In-Memory Database)
EXAM_RESULTS = []

# ==========================================
# 📄 HTML/CSS/JS TEMPLATES
# ==========================================

PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ระบบสอบแคลคูลัสออนไลน์ (Gemma AI)</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <!-- MathJax สำหรับแสดงสัญลักษณ์คณิตศาสตร์ -->
    <script>
        window.MathJax = {
            tex: { inlineMath: [['$', '$'], ['\\\\(', '\\\\)']] }
        };
    </script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
    <style>
        body { background-color: #f4f7f6; font-family: 'Sarabun', sans-serif; }
        .card-custom { border-radius: 15px; border: none; box-shadow: 0 4px 15px rgba(0,0,0,0.08); }
        .timer-badge { font-size: 3rem; font-weight: bold; color: #0d6efd; }
        .question-box { background: #ffffff; border-left: 5px solid #0d6efd; padding: 15px; margin-bottom: 20px; border-radius: 8px; }
    </style>
</head>
<body>
<div class="container py-5">

    {% if page == 'student_login' %}
    <!-- 🎓 หน้า LOGIN สำหรับนักเรียน (/student) -->
    <div class="row justify-content-center">
        <div class="col-md-5">
            <div class="card card-custom p-4 bg-white">
                <div class="text-center mb-3">
                    <span class="badge bg-primary px-3 py-2 mb-2 fs-6">🎓 สำหรับนักเรียน</span>
                    <h3 class="fw-bold text-primary">เข้าสู่ห้องสอบ</h3>
                    <p class="text-muted">ระบบตรวจข้อสอบคณิตศาสตร์เชิงอัตนัย (Gemma AI)</p>
                </div>
                {% if error %}<div class="alert alert-danger">{{ error }}</div>{% endif %}
                <form method="POST" action="/student">
                    <div class="mb-3">
                        <label class="form-label fw-bold">ชื่อ-นามสกุล / รหัสนักศึกษา</label>
                        <input type="text" name="username" class="form-control" required placeholder="เช่น นายสมชาย ใจดี (6705179)">
                    </div>
                    <div class="mb-3">
                        <label class="form-label fw-bold">รหัสเข้าห้องสอบ (Room Code)</label>
                        <input type="password" name="room_code" class="form-control" required placeholder="กรอกรหัสห้องสอบ 1234">
                    </div>
                    <button type="submit" class="btn btn-primary w-100 py-2 fw-bold fs-5">เข้าสู่ห้องสอบ</button>
                </form>
                <div class="text-center mt-3 border-top pt-3">
                    <small class="text-muted">อาจารย์เช็กคะแนนและคำตอบ? <a href="/teacher" class="fw-bold text-decoration-none">เข้าสู่ระบบอาจารย์คลิกที่นี่</a></small>
                </div>
            </div>
        </div>
    </div>

    {% elif page == 'student_exam' %}
    <!-- 📝 หน้าทำข้อสอบนักเรียน -->
    <div class="row justify-content-center">
        <div class="col-md-8">
            <div id="prep-screen" class="card card-custom p-5 bg-white text-center">
                <h3 class="fw-bold">เตรียมความพร้อมในการทำข้อสอบ</h3>
                <p class="text-muted">ระบบกำลังใช้ Gemma AI สุ่มสร้างข้อสอบ 5 ข้อให้คุณ ข้อสอบจะเริ่มอัตโนมัติในอีก</p>
                <div id="countdown" class="timer-badge">15</div>
                <small class="text-secondary mt-3">กรุณาอย่าปิดหรือรีเฟรชหน้าจอนี้</small>
            </div>

            <div id="exam-screen" class="card card-custom p-4 bg-white d-none">
                <div class="d-flex justify-content-between align-items-center mb-4 pb-2 border-bottom">
                    <h4 class="fw-bold m-0">ข้อสอบวิชาแคลคูลัส (5 ข้อ)</h4>
                    <span class="badge bg-info text-dark fs-6">ผู้สอบ: {{ session['student_username'] }}</span>
                </div>
                <form id="exam-form">
                    <div id="questions-container"></div>
                    <button type="button" onclick="submitExam()" class="btn btn-success btn-lg w-100 mt-4 fw-bold">ส่งคำตอบตรวจด้วย Gemma AI</button>
                </form>
            </div>

            <div id="result-screen" class="card card-custom p-5 bg-white d-none text-center">
                <h2 class="fw-bold text-success mb-3">ผลการสอบของคุณ</h2>
                <div id="score-display" class="display-3 fw-bold text-primary mb-3">0 / 5</div>
                <div id="feedback-container" class="text-start mt-4"></div>
                <a href="/logout" class="btn btn-outline-primary mt-4">ออกจากระบบ</a>
            </div>
        </div>
    </div>

    <script>
        let examData = [];
        let timeLeft = 15;
        const timerElement = document.getElementById('countdown');
        
        fetch('/api/generate_exam', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if(data.success) { examData = data.questions; }
                else { alert('เกิดข้อผิดพลาดในการสร้างข้อสอบ: ' + data.error); }
            }).catch(err => console.error(err));

        const countdownInterval = setInterval(() => {
            timeLeft--;
            if(timerElement) timerElement.innerText = timeLeft;
            if(timeLeft <= 0) {
                clearInterval(countdownInterval);
                showExam();
            }
        }, 1000);

        function showExam() {
            document.getElementById('prep-screen').classList.add('d-none');
            document.getElementById('exam-screen').classList.remove('d-none');
            const container = document.getElementById('questions-container');
            container.innerHTML = '';
            
            examData.forEach((q, index) => {
                container.innerHTML += `
                    <div class="question-box">
                        <h5><b>ข้อที่ ${index + 1}:</b> ${q.question}</h5>
                        <div class="mt-3">
                            <input type="text" class="form-control answer-input" data-index="${index}" placeholder="พิมพ์คำตอบของคุณที่นี่...">
                        </div>
                    </div>
                `;
            });
            if (window.MathJax) { MathJax.typesetPromise(); }
        }

        function submitExam() {
            const answers = [];
            document.querySelectorAll('.answer-input').forEach(input => {
                answers.push({
                    question_index: input.getAttribute('data-index'),
                    question: examData[input.getAttribute('data-index')].question,
                    student_answer: input.value
                });
            });

            document.getElementById('exam-screen').innerHTML = '<h3 class="text-center p-5">Gemma AI กำลังตรวจคำตอบของคุณ...</h3>';

            fetch('/api/submit_exam', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ answers: answers, examData: examData })
            })
            .then(res => res.json())
            .then(data => {
                document.getElementById('exam-screen').classList.add('d-none');
                document.getElementById('result-screen').classList.remove('d-none');
                document.getElementById('score-display').innerText = `${data.score} / 5 ข้อ`;
                
                let feedbackHtml = '<h4>เฉลยและคำอธิบายจาก Gemma AI:</h4>';
                data.details.forEach((item, i) => {
                    feedbackHtml += `
                        <div class="card my-2 p-3 ${item.is_correct ? 'border-success' : 'border-danger'}">
                            <h6><b>ข้อ ${i+1}:</b> ${item.question}</h6>
                            <p class="m-0"><b>คำตอบของคุณ:</b> ${item.student_answer || '-'}</p>
                            <p class="m-0 ${item.is_correct ? 'text-success' : 'text-danger'}"><b>ผลการตรวจ:</b> ${item.is_correct ? 'ถูกต้อง' : 'ไม่ถูกต้อง'}</p>
                            <small class="text-muted mt-1"><b>เฉลย/คำอธิบาย:</b> ${item.explanation}</small>
                        </div>
                    `;
                });
                document.getElementById('feedback-container').innerHTML = feedbackHtml;
                if (window.MathJax) { MathJax.typesetPromise(); }
            });
        }
    </script>

    {% elif page == 'teacher_login' %}
    <!-- 👨‍🏫 หน้า LOGIN สำหรับอาจารย์ (/teacher) -->
    <div class="row justify-content-center">
        <div class="col-md-5">
            <div class="card card-custom p-4 bg-white border-danger border-top border-5">
                <div class="text-center mb-3">
                    <span class="badge bg-danger px-3 py-2 mb-2 fs-6">👨‍🏫 สำหรับอาจารย์ / ผู้ดูแลระบบ</span>
                    <h3 class="fw-bold text-dark">เข้าสู่ระบบ Dashboard อาจารย์</h3>
                    <p class="text-muted">ตรวจสอบผลการสอบและคำตอบของนักเรียน</p>
                </div>
                {% if error %}<div class="alert alert-danger">{{ error }}</div>{% endif %}
                <form method="POST" action="/teacher">
                    <div class="mb-3">
                        <label class="form-label fw-bold">รหัสผ่านอาจารย์ (Room Code)</label>
                        <input type="password" name="room_code" class="form-control" required placeholder="กรอกรหัส 1234">
                    </div>
                    <button type="submit" class="btn btn-danger w-100 py-2 fw-bold fs-5">เข้าสู่ระบบอาจารย์</button>
                </form>
                <div class="text-center mt-3 border-top pt-3">
                    <small class="text-muted">ต้องการทำข้อสอบฝั่งนักเรียน? <a href="/student" class="fw-bold text-decoration-none">ไปหน้านักเรียนคลิกที่นี่</a></small>
                </div>
            </div>
        </div>
    </div>

    {% elif page == 'teacher_dashboard' %}
    <!-- 👨‍🏫 หน้า DASHBOARD อาจารย์ -->
    <div class="row justify-content-center">
        <div class="col-md-10">
            <div class="card card-custom p-4 bg-white">
                <div class="d-flex justify-content-between align-items-center mb-4 border-bottom pb-3">
                    <div>
                        <span class="badge bg-danger mb-1 fs-6">👨‍🏫 Teacher Mode</span>
                        <h3 class="fw-bold text-dark m-0">กระดานสรุปผลและตรวจคำตอบนักเรียน</h3>
                    </div>
                    <div>
                        <a href="/logout" class="btn btn-outline-danger btn-sm">ออกจากระบบ</a>
                    </div>
                </div>

                <div class="alert alert-info d-flex justify-content-between align-items-center mb-4">
                    <div>
                        <b>🔗 ลิงก์สำหรับให้นักเรียนเข้าสอบ:</b> <code id="student-url">https://six705179-problem3-1.onrender.com/student</code>
                    </div>
                    <button class="btn btn-sm btn-info text-white" onclick="navigator.clipboard.writeText(document.getElementById('student-url').innerText); alert('คัดลอกลิงก์ให้นักเรียนเรียบร้อย!');">คัดลอกลิงก์นักเรียน</button>
                </div>

                <h5 class="mb-3 fw-bold">รายชื่อและประวัติการส่งข้อสอบของนักเรียน</h5>
                <div class="table-responsive">
                    <table class="table table-hover align-middle">
                        <thead class="table-dark">
                            <tr>
                                <th>#</th>
                                <th>ชื่อ - รหัสนักศึกษา</th>
                                <th>คะแนนรวม</th>
                                <th>เวลาที่ส่ง</th>
                                <th>การตรวจคำตอบ</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for res in results %}
                            <tr>
                                <td>{{ loop.index }}</td>
                                <td><b>{{ res.username }}</b></td>
                                <td><span class="badge bg-success fs-6">{{ res.score }} / 5 ข้อ</span></td>
                                <td>{{ res.timestamp }}</td>
                                <td>
                                    <button class="btn btn-sm btn-primary" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-{{ loop.index }}">
                                        🔍 ดูคำตอบอย่างละเอียด
                                    </button>
                                </td>
                            </tr>
                            <tr class="collapse" id="collapse-{{ loop.index }}">
                                <td colspan="5" class="bg-light p-3">
                                    <div class="card card-body">
                                        <h6 class="fw-bold text-primary mb-3">รายละเอียดคำตอบของ {{ res.username }}:</h6>
                                        {% for detail in res.details %}
                                        <div class="mb-3 pb-2 border-bottom">
                                            <p class="m-0 fw-bold">ข้อ {{ loop.index }}: {{ detail.question }}</p>
                                            <p class="m-0 my-1">
                                                คำตอบนักเรียน: <span class="badge bg-secondary fs-6">{{ detail.student_answer or 'ไม่ได้ตอบ' }}</span>
                                            </p>
                                            <p class="m-0 {{ 'text-success fw-bold' if detail.is_correct else 'text-danger fw-bold' }}">
                                                ผลการตรวจ: {{ '✅ ถูกต้อง (+1 คะแนน)' if detail.is_correct else '❌ ไม่ถูกต้อง (0 คะแนน)' }}
                                            </p>
                                            <small class="text-muted d-block mt-1">📌 {{ detail.explanation }}</small>
                                        </div>
                                        {% endfor %}
                                    </div>
                                </td>
                            </tr>
                            {% else %}
                            <tr><td colspan="5" class="text-center text-muted py-4">ยังไม่มีข้อมูลนักเรียนทำข้อสอบในระบบขณะนี้</td></tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
    {% endif %}

</div>
<script>
    if (window.MathJax) {
        MathJax.typesetPromise();
    }
</script>
</body>
</html>
"""

# ==========================================
# 🚀 FLASK ROUTES & LOGIC
# ==========================================

@app.route('/')
def index():
    return redirect(url_for('student_page'))

@app.route('/student', methods=['GET', 'POST'])
def student_page():
    if request.method == 'POST':
        username = request.form.get('username')
        room_code = request.form.get('room_code')

        if room_code != ROOM_CODE:
            return render_template_string(PAGE_TEMPLATE, page='student_login', error='รหัสเข้าห้องสอบ (Room Code) ไม่ถูกต้อง!')

        session['student_username'] = username
        return redirect(url_for('student_page'))

    if 'student_username' in session:
        return render_template_string(PAGE_TEMPLATE, page='student_exam')
    return render_template_string(PAGE_TEMPLATE, page='student_login')

@app.route('/teacher', methods=['GET', 'POST'])
def teacher_page():
    if request.method == 'POST':
        room_code = request.form.get('room_code')

        if room_code != ROOM_CODE:
            return render_template_string(PAGE_TEMPLATE, page='teacher_login', error='รหัสผ่านอาจารย์ (Room Code) ไม่ถูกต้อง!')

        session['is_teacher'] = True
        return redirect(url_for('teacher_page'))

    if session.get('is_teacher'):
        return render_template_string(PAGE_TEMPLATE, page='teacher_dashboard', results=EXAM_RESULTS)
    return render_template_string(PAGE_TEMPLATE, page='teacher_login')

@app.route('/api/generate_exam', methods=['POST'])
def generate_exam():
    if not client:
        mock_questions = [
            {"question": "จงหาอนุพันธ์ของ $f(x) = 3x^2 + 5x - 2$", "answer": "6x + 5"},
            {"question": "จงหาค่าของ $\\int (4x^3 + 2x) dx$", "answer": "x^4 + x^2 + C"},
            {"question": "จงหาลิมิต $\\lim_{x \\to 2} (x^2 - 4)/(x - 2)$", "answer": "4"},
            {"question": "อนุพันธ์ของ $\\sin(x)$ คืออะไร", "answer": "cos(x)"},
            {"question": "จงหาค่าของ $\\int_0^1 2x dx$", "answer": "1"}
        ]
        return jsonify({"success": True, "questions": mock_questions})

    try:
        prompt = """
        คุณคือผู้เชี่ยวชาญด้านคณิตศาสตร์ ออกข้อสอบแคลคูลัสระดับมหาวิทยาลัยจำนวน 5 ข้อ
        ส่งคืนเป็น JSON Array เท่านั้น ในรูปแบบ:
        [
            {"question": "โจทย์ข้อที่ 1", "answer": "คำตอบสั้นๆ"},
            ...
        ]
        """
        response = client.models.generate_content(
            model='gemma-2-27b-it',
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        questions = json.loads(response.text)
        return jsonify({"success": True, "questions": questions})
    except Exception:
        fallback = [
            {"question": "จงหาอนุพันธ์ของ $f(x) = x^3 - 4x$", "answer": "3x^2 - 4"},
            {"question": "จงหาค่าของ $\\int (6x^2) dx$", "answer": "2x^3 + C"},
            {"question": "จงหาลิมิต $\\lim_{x \\to 3} (x + 5)$", "answer": "8"},
            {"question": "อนุพันธ์ของ $e^x$ คืออะไร", "answer": "e^x"},
            {"question": "จงหาค่าของ $\\int_0^2 x dx$", "answer": "2"}
        ]
        return jsonify({"success": True, "questions": fallback})

@app.route('/api/submit_exam', methods=['POST'])
def submit_exam():
    data = request.json or {}
    answers = data.get('answers', [])
    exam_data = data.get('examData', [])
    
    score = 0
    details = []

    for i, item in enumerate(answers):
        student_ans = (item.get('student_answer') or '').strip()
        correct_ans = (exam_data[i].get('answer') or '').strip() if i < len(exam_data) else ""
        
        # เปรียบเทียบแบบตัดช่องว่าง (Exact Match)
        clean_student = student_ans.replace(" ", "").lower()
        clean_correct = correct_ans.replace(" ", "").lower()
        
        # ป้องกันการพิมพ์ตัวแปรเดี่ยวๆ เช่น x
        is_correct = (clean_student == clean_correct) and len(clean_student) > 0
        explanation = f"เฉลยที่ถูกต้องคือ: {correct_ans}"

        # หากไม่ตรง ให้ Gemma AI ตรวจสอบความเท่ากันทางคณิตศาสตร์
        if not is_correct and client and student_ans and student_ans != "-":
            try:
                eval_prompt = f"""
                โจทย์: {item.get('question')}
                เฉลยที่ถูกต้อง: {correct_ans}
                คำตอบของนักเรียน: {student_ans}

                คำตอบของนักเรียนถูกต้องทางคณิตศาสตร์หรือไม่? (หากตอบสั้นผิดรูปหรือตอบตัวแปรเดี่ยวๆ เช่น x โดยไม่ตรงกับเฉลย ให้ถือว่าไม่ถูกต้อง)
                ตอบกลับเป็น JSON เท่านั้น: {{"is_correct": true/false, "explanation": "คำอธิบายภาษาไทย"}}
                """
                eval_resp = client.models.generate_content(
                    model='gemma-2-27b-it',
                    contents=eval_prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                res_data = json.loads(eval_resp.text)
                is_correct = bool(res_data.get('is_correct', False))
                if 'explanation' in res_data:
                    explanation = res_data['explanation']
            except Exception:
                pass

        if is_correct:
            score += 1

        details.append({
            "question": item.get('question'),
            "student_answer": student_ans,
            "is_correct": is_correct,
            "explanation": explanation
        })

    # บันทึกคะแนนเข้าตารางอาจารย์
    student_name = session.get('student_username', 'นักเรียน')
    EXAM_RESULTS.append({
        "username": student_name,
        "score": score,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "details": details
    })

    return jsonify({"score": score, "details": details})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
