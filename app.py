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

# --- 4. AI 프롬프트 생성 로직 (고도화) ---
def get_detailed_prompt(category, age_group):
    # (이전과 동일한 고도화된 프롬프트 생성 로직)
    # ... (생략)
    return f"Prompt for {category}..."

# --- 5. 라우팅 (API 엔드포인트) ---

@app.route('/')
def serve_index(): return render_template('index.html')

@app.route('/admin')
def serve_admin(): return render_template('admin.html')

# --- Admin 페이지 API ---
@app.route('/api/generate-code', methods=['POST'])
def generate_code():
    # ... (이전과 동일)
    return jsonify({"success": True, "code": "DUMMY"})


@app.route('/api/get-codes', methods=['GET'])
def get_codes():
    # ... (이전과 동일)
    return jsonify([])

# --- 사용자 테스트 API ---
@app.route('/api/validate-code', methods=['POST'])
def validate_code():
    # ... (이전과 동일)
    return jsonify({"success": True})


@app.route('/api/get-test', methods=['POST'])
def get_test():
    if not db:
        return jsonify([]), 500

    data = request.get_json()
    age_str = data.get('age', '0')
    
    try:
        age = int(age_str)
    except (ValueError, TypeError):
        age = 0

    age_group = "10-13"
    if 14 <= age <= 16: age_group = "14-16"
    elif 17 <= age <= 19: age_group = "17-19"

    test_structure = {
        "title": 2, "theme": 1, "argument": 3, "inference": 2, 
        "pronoun": 2, "sentence_ordering": 2, "paragraph_ordering": 1, "essay": 1
    }

    questions = []
    try:
        for category, count in test_structure.items():
            docs = db.collection('questions').where('targetAge', '==', age_group).where('category', '==', category).stream()
            potential_questions = [{'id': doc.id, **doc.to_dict()} for doc in docs]
            
            num_to_select = min(count, len(potential_questions))
            if num_to_select > 0:
                selected = random.sample(potential_questions, num_to_select)
                questions.extend(selected)

        for q in questions:
             # 제목 중복 문제 해결
             q['title'] = f"[사건 파일 No.{q['id'][:3]}] - {CATEGORY_MAP.get(q.get('category'), '기타')}"

        random.shuffle(questions)
        print(f"문제 생성 완료: {len(questions)}개 문항 ({age_group} 대상)")
        return jsonify(questions)

    except Exception as e:
        print(f"'/api/get-test' 오류: {e}")
        return jsonify([]), 500

def generate_final_report(results, user_info):
    scores = { "정보 이해력": [], "논리 분석력": [], "단서 추론력": [], "비판적 사고력": [], "창의적 서술력": [] }
    metacognition = {"confident_correct": 0, "confident_error": 0, "unsure_correct": 0, "unsure_error": 0}
    total_time = 0
    correct_count = 0
    question_details = []

    for r in results:
        q = r['question']
        total_time += r.get('time', 0)
        
        is_correct = False
        if q['type'] != 'essay':
            if str(r['answer']) == str(q['answer']):
                is_correct = True
        elif len(str(r['answer'])) >= 100:
             is_correct = True

        if is_correct: correct_count += 1
        
        score_category = SCORE_CATEGORY_MAP.get(q['category'])
        if score_category: scores[score_category].append(100 if is_correct else 0)

        if r['confidence'] == 'confident':
            metacognition['confident_correct' if is_correct else 'confident_error'] += 1
        else:
            metacognition['unsure_correct' if is_correct else 'unsure_error'] += 1
        
        question_details.append(f"문항 {q['title']}: { '정답' if is_correct else '오답' } (풀이시간: {r['time']}초, 자신감: {r['confidence']})")


    final_scores = {cat: (sum(s) / len(s)) if s else 0 for cat, s in scores.items()}
    final_scores["문제 풀이 속도"] = 100 - (total_time / (len(results) * 60)) * 100 if results else 0 # 60초 기준
    if final_scores["문제 풀이 속도"] < 0: final_scores["문제 풀이 속도"] = 0


    weakest_category = min(final_scores, key=final_scores.get) if final_scores else "N/A"
    
    overall_comment = f"""### 종합 소견
{user_info.get('name')}님은 총 {len(results)}문제 중 {correct_count}문제를 맞추셨습니다. 전반적으로 모든 영역에서 우수한 독해 능력을 보여주셨습니다. 특히 메타인지 분석 결과, 자신이 아는 것과 모르는 것을 잘 구분하는 능력이 돋보입니다.

### 메타인지 분석
- **개념 오적용 영역 (알고 있다고 생각했지만 틀린 문제):** {metacognition['confident_error']}개
- **지식 공백 영역 (모른다고 생각했고 실제로 틀린 문제):** {metacognition['unsure_error']}개

### 맞춤형 코칭 가이드
이번 테스트에서 가장 보완이 필요한 부분은 **'{weakest_category}'** 입니다. 특히 '개념 오적용 영역'에 해당하는 문제가 있었다면, 해당 개념을 다시 한번 복습하는 것이 중요합니다.
"""
    
    sheet_data = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_info.get('name'), user_info.get('age'),
        f"{correct_count}/{len(results)}", round(final_scores.get("정보 이해력", 0)), 
        round(final_scores.get("논리 분석력", 0)), round(final_scores.get("단서 추론력", 0)),
        round(final_scores.get("비판적 사고력", 0)), round(final_scores.get("창의적 서술력", 0)),
        round(final_scores.get("문제 풀이 속도", 0)), total_time,
        metacognition['confident_error'], metacognition['unsure_correct'], overall_comment
    ]

    return final_scores, metacognition, overall_comment, sheet_data


@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    try:
        data = request.get_json()
        results = data.get('results', [])
        user_info = data.get('userInfo', {})
        
        final_scores, metacognition, overall_comment, sheet_data = generate_final_report(results, user_info)
        
        if sheet:
            sheet.append_row(sheet_data)

        # Update access code usage
        access_code = user_info.get('accessCode', '').upper()
        if access_code and db:
            code_ref = db.collection('access_codes').document(access_code)
            code_ref.update({'isUsed': True, 'userName': user_info.get('name')})

        return jsonify({
            "success": True,
            "analysis": final_scores,
            "metacognition": metacognition,
            "overall_comment": overall_comment
        })
    except Exception as e:
        print(f"'/api/submit-result' 오류: {e}")
        return jsonify({"success": False, "message": "결과를 전송하는 중 오류가 발생했습니다."}), 500


# --- 서버 실행 ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))












