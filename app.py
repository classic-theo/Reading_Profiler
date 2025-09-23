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
    if age_group == "10-13":
        level_instruction = "대한민국 초등학교 4~6학년 국어 교과서 수준의 어휘와 문장 구조를 사용해줘. '야기하다', '고찰하다' 같은 어려운 한자어는 '일으킨다', '살펴본다'처럼 쉬운 말로 풀어 써줘."
        passage_length = "최소 2개 문단, 150자 이상"
    elif age_group == "14-16":
        level_instruction = "대한민국 중학교 1~3학년 국어 교과서 수준의 어휘와 문장 구조를 사용해줘. 전문 용어는 최소화하고, 필요 시 간단한 설명을 덧붙여줘."
        passage_length = "최소 3개 문단, 250자 이상"
    else: # 17-19
        level_instruction = "대한민국 고등학교 1~3학년 수준의 어휘와 복합적인 문장 구조를 사용해도 좋아. 사회, 과학, 인문 등 다양한 분야의 배경지식을 활용해줘."
        passage_length = "최소 3개 문단, 350자 이상"

    type_instruction = ""
    if category in ["title", "theme"]:
        type_instruction = f"글의 전체 내용을 아우르는 주제나 제목을 찾도록 유도하는, {passage_length}으로 구성된 완결된 설명문을 창작해줘."
    # ... (다른 유형에 대한 지시사항들) ...
    elif category == "sentence_ordering":
        type_instruction = "논리적 순서나 시간의 흐름이 중요한 1개의 완결된 단락을 창작한 후, 그 단락을 5개의 문장으로 분해해서 순서를 뒤섞어 문제로 만들어줘."
    elif category == "paragraph_ordering":
        type_instruction = "기승전결이나 서론-본론-결론 구조가 뚜렷한 3개의 단락으로 구성된 글을 창작한 후, 단락의 순서를 뒤섞어 문제로 만들어줘."
    else: # essay
        type_instruction = "학생의 창의적인 생각이나 가치관을 엿볼 수 있는 개방적인 질문과, 그에 대한 생각을 유도하는 1~2문장의 짧은 상황을 제시해줘."

    base_prompt = f"""
너는 지금부터 '{CATEGORY_MAP.get(category, category)}' 유형의 독서력 평가 문제를 출제하는 최고의 교육 전문가야.
다음 규칙을 반드시 지켜서, JSON 형식으로 완벽한 문제 1개를 생성해줘.
[규칙]
... (이하 전체 프롬프트 내용) ...
"""
    return base_prompt

# --- 5. 라우팅 (API 엔드포인트) ---

@app.route('/')
def serve_index(): return render_template('index.html')

@app.route('/admin')
def serve_admin(): return render_template('admin.html')

# --- Admin 페이지 API ---
@app.route('/api/generate-code', methods=['POST'])
def generate_code():
    if not db: return jsonify({"success": False, "message": "DB 연결 실패"}), 500
    try:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        code_ref = db.collection('access_codes').document(code)
        if code_ref.get().exists: return generate_code() # 재귀 호출로 중복 방지
        code_ref.set({'createdAt': datetime.now(timezone.utc), 'isUsed': False, 'userName': None})
        return jsonify({"success": True, "code": code})
    except Exception as e:
        return jsonify({"success": False, "message": f"서버 오류: {e}"}), 500

@app.route('/api/get-codes', methods=['GET'])
def get_codes():
    if not db: return jsonify([]), 500
    try:
        codes_ref = db.collection('access_codes').order_by('createdAt', direction=firestore.Query.DESCENDING).stream()
        codes = []
        for doc in codes_ref:
            c = doc.to_dict()
            c['createdAt'] = c['createdAt'].strftime('%Y-%m-%d %H:%M:%S')
            c['code'] = doc.id
            codes.append(c)
        return jsonify(codes)
    except Exception as e:
        print(f"코드 조회 오류: {e}")
        return jsonify([]), 500
        
# --- 사용자 테스트 API ---
@app.route('/api/validate-code', methods=['POST'])
def validate_code():
    if not db: return jsonify({"success": False, "message": "DB 연결 실패"}), 500
    code = request.get_json().get('code', '').upper()
    code_ref = db.collection('access_codes').document(code)
    code_doc = code_ref.get()
    if not code_doc.exists: return jsonify({"success": False, "message": "유효하지 않은 코드입니다."})
    if code_doc.to_dict().get('isUsed'): return jsonify({"success": False, "message": "이미 사용된 코드입니다."})
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
        age = 0 # Handle cases where age is not a valid number

    # Map user age to age group for querying
    age_group = "10-13" # default
    if 14 <= age <= 16:
        age_group = "14-16"
    elif 17 <= age <= 19:
        age_group = "17-19"

    # Standardized test structure (15 questions total)
    test_structure = {
        "title": 2, "theme": 1,             # 정보 이해력 (3)
        "argument": 3,                      # 비판적 사고력 (3)
        "inference": 2, "pronoun": 2,       # 단서 추론력 (4)
        "sentence_ordering": 2, "paragraph_ordering": 1, # 논리 분석력 (3)
        "essay": 1                          # 창의적 서술력 (1)
    }

    questions = []
    try:
        for category, count in test_structure.items():
            docs = db.collection('questions').where('targetAge', '==', age_group).where('category', '==', category).get()
            
            potential_questions = []
            for doc in docs:
                q_data = doc.to_dict()
                q_data['id'] = doc.id
                potential_questions.append(q_data)

            num_to_select = min(count, len(potential_questions))
            if num_to_select > 0:
                selected = random.sample(potential_questions, num_to_select)
                questions.extend(selected)

        for q in questions:
             q['category_kr'] = CATEGORY_MAP.get(q.get('category'), '기타')

        random.shuffle(questions)

        print(f"문제 생성 완료: {len(questions)}개 문항 ({age_group} 대상)")
        return jsonify(questions)

    except Exception as e:
        print(f"'/api/get-test' 오류: {e}")
        return jsonify([]), 500

@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    # ... (이전과 동일) ...
    return jsonify({"success": True, "message": "결과가 제출되었습니다."})


# --- 서버 실행 ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))










