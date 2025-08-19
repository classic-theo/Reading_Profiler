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
from bs4 import BeautifulSoup # URL 크롤링을 위한 라이브러리

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

# Firebase 초기화
try:
    # ... (기존과 동일, 생략)
except Exception as e:
    print(f"Firebase 초기화 실패: {e}")

# Google Sheets 초기화
try:
    # ... (기존과 동일, 생략)
except Exception as e:
    print(f"Google Sheets 초기화 실패: {e}")


# --- 3. 라우팅 (API 엔드포인트) ---

@app.route('/')
def serve_index(): return render_template('index.html')

@app.route('/admin')
def serve_admin(): return render_template('admin.html')

# --- AI 기반 문제 생성 API ---
def create_ai_prompt(age, category, text=None):
    # ... (AI 프롬프트 생성 로직, 생략)
    pass

@app.route('/api/generate-question-from-url', methods=['POST'])
def generate_from_url():
    # ... (URL 크롤링 및 문제 생성 로직, 생략)
    pass

@app.route('/api/generate-question', methods=['POST'])
def generate_question():
    # ... (기본 AI 문제 생성 로직, 생략)
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
            q['category_kr'] = CATEGORY_MAP.get(q.get('category'), '기타')
            all_questions.append(q)
        
        if not all_questions:
             return jsonify([{'id': 'temp', 'title': '임시 문제', 'passage': '문제 은행에 문제가 없습니다.', 'type': 'multiple_choice', 'options':['확인'], 'answer':'확인'}])
        
        # 15개 문항으로 구성
        return jsonify(random.sample(all_questions, min(len(all_questions), 15)))
    except Exception as e:
        return jsonify([]), 500

@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    if not db: return jsonify({"success": False, "error": "DB 연결 실패"}), 500
    
    data = request.get_json()
    user_info = data.get('userInfo', {})
    answers = data.get('answers', [])
    
    # 상세 분석 데이터 계산
    skill_scores = { "comprehension": 0, "logic": 0, "inference": 0, "creativity": 0, "critical_thinking": 0, "speed": 0 }
    total_time = 0
    total_confidence = 0
    detailed_feedback = []

    for ans in answers:
        # ... (채점, 시간, 자신감 점수 계산 로직, 생략)
        pass

    # 최종 보고서 생성
    report = { "skill_scores": skill_scores, "detailed_feedback": detailed_feedback }
    
    # 구글 시트 저장
    try:
        if sheet:
            # ... (상세 데이터 시트 저장 로직, 생략)
            pass
    except Exception as e:
        print(f"Google Sheets 저장 오류: {e}")

    return jsonify({"success": True, "report": report})

# --- 관리자 기능 API ---
# ... (코드 생성, 코드 목록 조회 등 생략)

# --- 4. Flask 앱 실행 ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)

