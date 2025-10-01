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
import re

# --- 1. Flask 앱 초기화 ---
app = Flask(__name__, template_folder='templates')

# --- 2. 외부 서비스 초기화 ---
db = None
sheet = None
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

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

# --- 3. 핵심 데이터 및 설정 ---
CATEGORY_MAP = {
    "title": "제목 찾기", "theme": "주제 찾기", "argument": "주장 파악",
    "inference": "의미 추론", "pronoun": "지시어 찾기", "sentence_ordering": "문장 순서 맞추기",
    "paragraph_ordering": "단락 순서 맞추기", "essay": "창의적 서술력"
}

SCORE_CATEGORY_MAP = {
    "title": "정보 이해력", "theme": "정보 이해력", 
    "argument": "비판적 사고력",
    "inference": "단서 추론력", "pronoun": "단서 추론력",
    "sentence_ordering": "논리 분석력", "paragraph_ordering": "논리 분석력",
    "essay": "창의적 서술력"
}

# --- 4. 라우팅 (API 엔드포인트) ---
@app.route('/')
def serve_index(): return render_template('index.html')
@app.route('/admin')
def serve_admin(): return render_template('admin.html')

# (Admin 페이지 API들은 생략 - 이전 버전과 동일)
# ...

# --- 사용자 테스트 API ---
@app.route('/api/get-test', methods=['POST'])
def get_test():
    if not db: return jsonify([]), 500

    data = request.get_json()
    age = int(data.get('age', 0))

    age_group = "10-13"
    if 14 <= age <= 16: age_group = "14-16"
    elif 17 <= age <= 19: age_group = "17-19"

    # '7+1 유형 x 2문항' 구조 정의 (총 15문제)
    test_structure = {
        "title": 2,
        "theme": 2,
        "argument": 2,
        "inference": 2,
        "pronoun": 2,
        "sentence_ordering": 2,
        "paragraph_ordering": 2,
        "essay": 1
    }
    
    questions = []
    
    try:
        for category, needed_count in test_structure.items():
            # DB에서 해당 연령대, 해당 카테고리의 모든 문제를 가져옴
            docs = db.collection('questions').where('targetAge', '==', age_group).where('category', '==', category).stream()
            
            potential_questions = []
            for doc in docs:
                q_data = doc.to_dict()
                q_data['id'] = doc.id
                potential_questions.append(q_data)

            # 필요한 수만큼 랜덤으로 선택 (만약 문제가 부족하면 있는 만큼만)
            num_to_select = min(needed_count, len(potential_questions))
            if num_to_select > 0:
                selected = random.sample(potential_questions, num_to_select)
                questions.extend(selected)

        for q in questions:
             # 제목을 일관된 형식으로 새로 생성
             q['title'] = f"[사건 파일 No.{q['id'][:3]}] - {CATEGORY_MAP.get(q.get('category'), '기타')}"
             # 프론트엔드에서 사용할 한글 카테고리명 추가
             q['category_kr'] = CATEGORY_MAP.get(q.get('category'), '기타')


        random.shuffle(questions)

        print(f"문제 생성 완료: {len(questions)}개 문항 ({age_group} 대상)")
        return jsonify(questions)

    except Exception as e:
        print(f"'/api/get-test' 오류: {e}")
        return jsonify([]), 500

# (AI 동적 리포트 생성 함수 및 최종 분석 로직은 이전과 동일)
def generate_dynamic_report_from_ai(user_name, scores, metacognition):
    # ...
    return "AI 생성 리포트"

def generate_final_report(user_name, results):
    # ...
    final_report_text = generate_dynamic_report_from_ai(user_name, final_scores, metacognition)
    # ...
    return final_scores, metacognition, final_report_text, recommendations

@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    # ...
    final_scores, metacognition, final_report, recommendations = generate_final_report(user_info.get('name'), results)
    # ...
    return jsonify({
        "success": True,
        "analysis": final_scores,
        "metacognition": metacognition,
        "overall_comment": final_report,
        "recommendations": recommendations
    })

# --- 서버 실행 ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
















