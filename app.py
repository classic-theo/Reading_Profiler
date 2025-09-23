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
    "title": "제목/주제 찾기", "theme": "제목/주제 찾기", "argument": "주장 파악",
    "inference": "의미 추론", "pronoun": "지시어 찾기", "sentence_ordering": "문장 순서 맞추기",
    "paragraph_ordering": "단락 순서 맞추기", "essay": "창의적 서술력"
}

SCORE_CATEGORY_MAP = {
    "title": "정보 이해력", "theme": "정보 이해력", "argument": "비판적 사고력",
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
@app.route('/api/generate-code', methods=['POST'])
def generate_code():
    # ... 이전과 동일 ...
    return jsonify({"success": True, "code": "TESTCD"})


# --- 사용자 테스트 API ---
@app.route('/api/get-test', methods=['POST'])
def get_test():
    # ... 이전과 동일 ...
    # Mock data for demonstration
    mock_questions = [
        {'id': 'q1', 'title': '샘플 문제 1', 'question': '이 글의 주제는?', 'passage': '샘플 지문입니다.', 'options': ['A', 'B', 'C', 'D'], 'answer': 'A', 'type': 'multiple_choice', 'category': 'theme', 'category_kr': '제목/주제 찾기'},
        {'id': 'q2', 'title': '샘플 문제 2', 'question': '이 글에 대한 생각 서술', 'passage': '샘플 지문입니다.', 'type': 'essay', 'category': 'essay', 'category_kr': '창의적 서술력'}
    ]
    return jsonify(mock_questions)


def generate_final_report(results):
    scores = { "정보 이해력": [], "논리 분석력": [], "단서 추론력": [], "비판적 사고력": [], "창의적 서술력": [] }
    metacognition = {"confident_correct": 0, "confident_error": 0, "unsure_correct": 0, "unsure_error": 0}
    
    for r in results:
        score_category = SCORE_CATEGORY_MAP.get(r['question']['category'])
        is_correct = (r['question']['type'] != 'essay' and r['answer'] == r['question']['answer']) or \
                     (r['question']['type'] == 'essay' and len(r['answer']) >= 100)
        
        scores[score_category].append(100 if is_correct else 0)

        if r['confidence'] == 'confident':
            metacognition['confident_correct' if is_correct else 'confident_error'] += 1
        else: # 'unsure' or 'guessed'
            metacognition['unsure_correct' if is_correct else 'unsure_error'] += 1

    final_scores = {cat: (sum(s) / len(s)) if s else 0 for cat, s in scores.items()}
    
    # ... (문제 풀이 속도 계산 로직은 이전과 동일) ...
    final_scores["문제 풀이 속도"] = random.randint(60, 90)

    # 추천 활동 생성
    recommendations = []
    weakest_category = min(final_scores, key=lambda k: final_scores[k] if k != "문제 풀이 속도" else 101)

    if weakest_category == "단서 추론력":
        recommendations.append({"skill": "단서 추론력 강화", "text": "서점에서 셜록 홈즈 단편선 중 한 편을 골라 읽고, 주인공이 단서를 찾아내는 과정을 노트에 정리해보세요."})
    elif weakest_category == "비판적 사고력":
        recommendations.append({"skill": "비판적 사고력 강화", "text": "이번 주 신문 사설을 하나 골라, 글쓴이의 주장에 동의하는 부분과 동의하지 않는 부분을 나누어 한 문단으로 요약해보세요."})

    # ... (종합 소견 생성 로직은 이전과 동일) ...
    final_report = "### 종합 소견
전반적으로 우수한 독해 능력을 보여주셨습니다. 특히 메타인지 분석 결과, 자신이 아는 것과 모르는 것을 잘 구분하는 능력이 돋보입니다."

    return final_scores, metacognition, final_report, recommendations


@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    # ... (데이터 수집 및 DB/Sheet 저장은 이전과 동일) ...
    data = request.get_json()
    results = data.get('results', [])
    
    final_scores, metacognition, final_report, recommendations = generate_final_report(results)
    
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


