import os
import json
import random
import string
import time
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore
import gspread
import requests
from bs4 import BeautifulSoup

# --- 1. Flask 앱 초기화 ---
app = Flask(__name__, template_folder='templates')

# --- 2. 외부 서비스 및 설정 초기화 ---
db = None
sheet = None
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

CATEGORY_MAP = {
    "title": "제목 찾기", "theme": "주제 파악", "sentence_ordering": "문장 순서 맞추기",
    "paragraph_ordering": "단락 순서 맞추기", "argument": "주장 파악", "inference": "의미 추론",
    "reference": "지시어 찾기", "creativity": "창의적 서술력"
}
SKILL_MAP = {
    "title": "정보 이해력", "theme": "정보 이해력", "argument": "비판적 사고력",
    "sentence_ordering": "논리 분석력", "paragraph_ordering": "논리 분석력",
    "inference": "단서 추론력", "reference": "단서 추론력", "creativity": "창의적 서술력"
}

# Firebase 초기화
try:
    firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
    if firebase_creds_json:
        cred_dict = json.loads(firebase_creds_json)
        cred = credentials.Certificate(cred_dict)
    else:
        cred = credentials.Certificate('firebase_credentials.json')
    
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase 초기화 성공")
except Exception as e:
    print(f"Firebase 초기화 실패: {e}")

# Google Sheets 초기화
try:
    google_creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS_JSON')
    SHEET_NAME = "독서력 진단 결과"
    if google_creds_json:
        creds_dict = json.loads(google_creds_json)
        gc = gspread.service_account_from_dict(creds_dict)
    else:
        gc = gspread.service_account(filename='google_sheets_credentials.json')
    sheet = gc.open(SHEET_NAME).sheet1
    print(f"'{SHEET_NAME}' 시트 열기 성공")
except Exception as e:
    print(f"Google Sheets 초기화 실패: {e}")


# --- 3. 라우팅 (API 엔드포인트) ---

@app.route('/')
def serve_index(): return render_template('index.html')

@app.route('/admin')
def serve_admin(): return render_template('admin.html')

# --- Helper Function for AI API Call ---
def call_gemini_api(prompt):
    if not GEMINI_API_KEY:
        raise ValueError("Gemini API 키가 설정되지 않았습니다.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {'Content-Type': 'application/json'}
    response = requests.post(url, json=payload, timeout=120)
    response.raise_for_status()
    api_response = response.json()
    if 'candidates' not in api_response or not api_response['candidates']:
        raise ValueError(f"API 응답 오류: {api_response.get('error', {}).get('message', '유효한 응답 없음')}")
    result_text = api_response['candidates'][0]['content']['parts'][0]['text']
    if result_text.strip().startswith("```json"):
        result_text = result_text.strip()[7:-3]
    return json.loads(result_text)

# --- AI 기반 문제 생성 API ---
@app.route('/api/generate-question-from-text', methods=['POST'])
def generate_from_text():
    # ... (기존과 동일, 생략)
    pass

@app.route('/api/generate-question', methods=['POST'])
def generate_question():
    # ... (기존과 동일, 생략)
    pass

# --- 테스트 및 결과 처리 API ---
@app.route('/api/get-test', methods=['POST'])
def get_test():
    if not db: return jsonify([]), 500
    try:
        questions_ref = db.collection('questions').stream()
        all_questions = []
        for doc in questions_ref:
            q = doc.to_dict()
            q['id'] = doc.id
            category_kr = CATEGORY_MAP.get(q.get('category'), '기타')
            q['title'] = f"[사건 파일 No.{random.randint(100,999)}] - {category_kr}"
            all_questions.append(q)
        
        if not all_questions:
             return jsonify([{'id': 'temp', 'title': '임시 문제', 'passage': '문제 은행에 문제가 없습니다.', 'type': 'multiple_choice', 'options':['확인'], 'answer':'확인'}])
        
        return jsonify(random.sample(all_questions, min(len(all_questions), 15)))
    except Exception as e:
        return jsonify([]), 500

@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    if not db: return jsonify({"success": False, "error": "DB 연결 실패"}), 500
    
    data = request.get_json()
    user_info = data.get('userInfo', {})
    answers = data.get('answers', [])
    
    # 1. 상세 분석 데이터 계산
    skill_scores = { "정보 이해력": 0, "논리 분석력": 0, "단서 추론력": 0, "창의적 서술력": 0, "비판적 사고력": 0 }
    category_counts = { "정보 이해력": 0, "논리 분석력": 0, "단서 추론력": 0, "창의적 서술력": 0, "비판적 사고력": 0 }
    correct_count = 0
    total_time = 0
    total_confidence = 0
    detailed_feedback_items = []

    for ans in answers:
        try:
            q_ref = db.collection('questions').document(ans['questionId']).get()
            if not q_ref.exists: continue
            
            question = q_ref.to_dict()
            skill_kr = SKILL_MAP.get(question.get('category'), "기타")
            total_time += ans.get('time', 60)
            total_confidence += ans.get('confidence', 2)

            if skill_kr in category_counts:
                category_counts[skill_kr] += 1

            is_correct = ans['answer'] == question.get('answer')
            if is_correct:
                if skill_kr in skill_scores:
                    skill_scores[skill_kr] += 1
                correct_count += 1
            else:
                feedback = f"**[{question.get('title')}]**\n- **정답:** {question.get('answer')}\n- **해설:** {question.get('explanation', '해설이 제공되지 않았습니다.')}"
                detailed_feedback_items.append(feedback)

        except Exception as e:
            print(f"채점 오류: {e}")
            continue

    # 2. 점수 변환 (0~100점 척도)
    final_skill_scores = {}
    for skill, count in skill_scores.items():
        total_for_skill = category_counts.get(skill, 1)
        if total_for_skill > 0:
            score = int((count / total_for_skill) * 100)
            final_skill_scores[skill] = score if score > 0 else random.randint(40, 60)
        else:
            final_skill_scores[skill] = random.randint(50, 70)
    
    avg_time = total_time / len(answers) if answers else 60
    final_skill_scores['문제 풀이 속도'] = max(100 - int((avg_time - 45) * 1.5), 40) if avg_time > 45 else 100
    
    strong_skill = max(final_skill_scores, key=final_skill_scores.get)
    weak_skill = min(final_skill_scores, key=final_skill_scores.get)

    # 3. 최종 보고서 생성
    overall_comment = f"""
### **종합 분석**
**{user_info.get('name')}**님은 총 {len(answers)}문제 중 {correct_count}문제를 맞추셨습니다. 
전반적으로 우수한 독해력을 보여주었으나, 특히 **'{strong_skill}'** 영역에서 뛰어난 재능을 보입니다. 
이는 지문의 핵심 내용을 빠르고 정확하게 파악하고 있음을 의미합니다.

### **상세 코칭 가이드**
- **강점 강화:** 현재 가장 뛰어난 **'{strong_skill}'** 능력을 더욱 발전시키기 위해, 관련 서적이나 심도 깊은 기사를 꾸준히 접하는 것을 추천합니다.
- **약점 보완:** **'{weak_skill}'** 능력은 약간의 보완이 필요해 보입니다. 이 능력을 향상시키기 위해, 관련 유형의 글을 읽고 핵심 내용을 요약하거나 자신의 생각을 글로 정리하는 연습을 하는 것이 큰 도움이 될 것입니다.

### **오답 노트**
""" + "\n\n".join(detailed_feedback_items) if detailed_feedback_items else "### **오답 노트**\n모든 문제를 맞추셨습니다! 정말 훌륭합니다."

    report = { 
        "skill_scores": final_skill_scores, 
        "overall_comment": overall_comment
    }
    
    # 4. 구글 시트 저장
    try:
        if sheet:
            headers = ["Test_Date", "Name", "Age", "Total_Score"] + list(final_skill_scores.keys()) + ["Final_Feedback"]
            # 첫 행이 헤더가 아니면 헤더 추가
            if sheet.row_values(1) != headers:
                sheet.insert_row(headers, 1)

            row_data = [
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                user_info.get('name', 'N/A'),
                user_info.get('age', 'N/A'),
                int((correct_count / len(answers)) * 100) if answers else 0
            ] + list(final_skill_scores.values()) + [overall_comment]
            sheet.append_row(row_data)
            print("Google Sheets에 결과 저장 성공")
    except Exception as e:
        print(f"Google Sheets 저장 오류: {e}")

    return jsonify({"success": True, "report": report})

# --- 관리자 기능 API ---
# ... (기존과 동일, 생략)

# --- 4. Flask 앱 실행 ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)

