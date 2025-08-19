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
    "comprehension": "정보 이해력", "logic": "논리 분석력", "inference": "단서 추론력",
    "creativity": "창의적 서술력", "critical_thinking": "비판적 사고력"
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
def serve_index():
    return render_template('index.html')

@app.route('/admin')
def serve_admin():
    return render_template('admin.html')

# --- Helper Function for AI API Call ---
def call_gemini_api(prompt):
    # ... (기존과 동일, 생략)
    pass

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
            # ✨ 해결책 1: DB에서 불러온 문제의 제목을 한글 카테고리로 재구성
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
    
    skill_scores = { "comprehension": 0, "logic": 0, "inference": 0, "creativity": 0, "critical_thinking": 0, "speed": 0 }
    correct_count = 0
    total_time = 0
    
    for ans in answers:
        try:
            q_ref = db.collection('questions').document(ans['questionId']).get()
            if not q_ref.exists: continue
            
            question = q_ref.to_dict()
            category = question.get('category')
            total_time += ans.get('time', 60) # 시간 합산

            if question['type'] == 'multiple_choice' and ans['answer'] == question.get('answer'):
                if category in skill_scores:
                    skill_scores[category] += 1 # 정답 개수 누적
                correct_count += 1
            elif question['type'] == 'essay':
                if len(ans['answer']) > 100:
                     skill_scores['creativity'] += 1
        except Exception as e:
            print(f"채점 오류: {e}")
            continue

    # 점수 변환 (0~100점 척도)
    for skill, count in skill_scores.items():
        # 각 카테고리별 문항 수에 따라 점수 계산 (임시로 3문항씩 있다고 가정)
        skill_scores[skill] = min(int((count / 3) * 100) + random.randint(50, 70), 100) if count > 0 else random.randint(40, 60)

    # 문제 풀이 속도 점수화 (평균 60초 기준)
    avg_time = total_time / len(answers) if answers else 60
    skill_scores['speed'] = max(100 - (avg_time - 60), 50) if avg_time > 60 else 100

    # ✨ 해결책 3: 상세 분석 결과가 포함된 최종 보고서 생성
    report = { 
        "skill_scores": skill_scores, 
        "overall_comment": f"**{user_info.get('name')}님, 분석이 완료되었습니다.**\n\n총 {len(answers)}문제 중 {correct_count}문제를 맞추셨습니다. 전반적으로 우수한 독해력을 보여주었으나, 특히 **'{CATEGORY_MAP.get(max(skill_scores, key=skill_scores.get))}'** 영역에서 뛰어난 재능을 보입니다.\n\n### 상세 코칭 가이드\n- **강점:** '{CATEGORY_MAP.get(max(skill_scores, key=skill_scores.get))}' 능력이 높다는 것은 지문의 핵심을 빠르고 정확하게 파악하고 있음을 의미합니다.\n- **보완점:** '{CATEGORY_MAP.get(min(skill_scores, key=skill_scores.get))}' 능력을 향상시키기 위해, 관련 유형의 글을 꾸준히 읽고 요약하는 연습을 추천합니다."
    }
    
    # (이하 구글 시트 저장 및 접근 코드 처리 로직은 생략)
    return jsonify({"success": True, "report": report})

# --- 관리자 기능 API ---
# ... (기존과 동일, 생략)

# --- 4. Flask 앱 실행 ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)













