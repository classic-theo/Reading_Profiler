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
@app.route('/api/generate-question-from-url', methods=['POST'])
def generate_from_url():
    data = request.get_json()
    url = data.get('url')
    age = data.get('age', '15')
    category_en = data.get('category', 'comprehension')
    category_kr = CATEGORY_MAP.get(category_en, "정보 이해력")

    if not url:
        return jsonify({"success": False, "message": "URL이 제공되지 않았습니다."}), 400

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        for element in soup(['header', 'footer', 'nav', 'aside', 'script', 'style', 'a', 'form']):
            element.decompose()
        text_content = ' '.join(soup.body.stripped_strings)
        text_content = ' '.join(text_content.split())
        
        if len(text_content) < 200:
            return jsonify({"success": False, "message": f"URL에서 충분한 텍스트(200자 이상)를 추출하지 못했습니다. (추출된 글자 수: {len(text_content)})"}), 400
        
        prompt = f"""
        주어진 텍스트를 분석하여 독서력 평가 문제를 만드는 AI 전문가입니다.
        아래 "지문"을 바탕으로, 다음 조건에 맞는 객관식 문제를 1개 생성해주세요.
        **지문:**
        ---
        {text_content[:3000]} 
        ---
        **생성 조건:**
        1. 대상 연령: {age}세
        2. 측정 능력: {category_kr}
        3. 문제 (title): 지문의 내용을 바탕으로 한 객관식 질문.
        4. 선택지 (options): 4개의 선택지를 배열 형태로, 그 중 하나는 명확한 정답.
        5. 정답 (answer): 4개의 선택지 중 정답 문장.
        6. 출력 형식: 반드시 아래의 JSON 스키마를 준수.
        {{
          "title": "string", "passage": "{text_content[:500].replace('"', "'")}...", "type": "multiple_choice",
          "options": ["string", "string", "string", "string"], "answer": "string",
          "category": "{category_en}", "targetAge": "{age}"
        }}
        """
        question_data = call_gemini_api(prompt)
        if db:
            db.collection('questions').add(question_data)
            return jsonify({"success": True, "message": f"URL 기반 '{category_kr}' 문제 1개를 DB에 추가했습니다."})
        else:
            return jsonify({"success": False, "message": "DB 연결 실패"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"URL 문제 생성 오류: {e}"}), 500

@app.route('/api/generate-question', methods=['POST'])
def generate_question():
    data = request.get_json()
    age = data.get('age', '15')
    category_en = data.get('category', 'logic')
    category_kr = CATEGORY_MAP.get(category_en, "논리 분석력")
    
    prompt = f"""
    '{age}세' 학생들의 눈높이에 맞는 독서력 평가 문제를 출제하는 교육 전문가로서, 다음 조건에 맞춰 객관식 문제를 생성해주세요.
    1. 측정 능력: {category_kr}
    2. 지문 (passage): {category_kr} 능력을 평가할 수 있는 흥미로운 2~3문단 길이의 지문을 직접 창작.
    3. 문제 (title): 지문을 바탕으로 한 질문. 제목은 '[사건 파일 No.XXX] - {category_kr}' 형식.
    4. 선택지 (options): 4개의 선택지를 배열 형태로, 하나는 명확한 정답.
    5. 정답 (answer): 4개의 선택지 중 정답 문장.
    6. 출력 형식: 반드시 아래의 JSON 스키마를 준수.
    {{
      "title": "string", "passage": "string", "type": "multiple_choice",
      "options": ["string", "string", "string", "string"], "answer": "string",
      "category": "{category_en}", "targetAge": "{age}"
    }}
    """
    try:
        question_data = call_gemini_api(prompt)
        if db:
            db.collection('questions').add(question_data)
            return jsonify({"success": True, "message": f"AI가 새로운 '{category_kr}' 문제를 생성하여 DB에 추가했습니다."})
        else:
            return jsonify({"success": False, "message": "DB 연결 실패"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"AI 문제 생성 오류: {e}"}), 500

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
    # 채점 로직 구현 필요
    # ...

    report = { 
        "skill_scores": skill_scores, 
        "overall_comment": f"**{user_info.get('name')}님, 분석이 완료되었습니다.**\n\n상세 보고서는 관리자에게 전달됩니다."
    }
    
    try:
        if sheet:
            # 시트 저장 로직 구현 필요
            pass
    except Exception as e:
        print(f"Google Sheets 저장 오류: {e}")

    return jsonify({"success": True, "report": report})

# --- 관리자 기능 API ---
@app.route('/api/generate-code', methods=['POST'])
def generate_code():
    if not db: return jsonify({"success": False, "message": "DB 연결 실패"}), 500
    try:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        code_ref = db.collection('access_codes').document(code)
        if code_ref.get().exists: return generate_code()
        code_ref.set({'createdAt': datetime.now(timezone.utc), 'isUsed': False, 'userName': None})
        return jsonify({"success": True, "code": code})
    except Exception as e:
        return jsonify({"success": False, "message": f"코드 생성 오류: {e}"}), 500

@app.route('/api/get-codes', methods=['GET'])
def get_codes():
    if not db: return jsonify([]), 500
    try:
        codes_ref = db.collection('access_codes').order_by('createdAt', direction=firestore.Query.DESCENDING).stream()
        codes = []
        for doc in codes_ref:
            code_data = code.to_dict()
            code_data['code'] = doc.id
            code_data['createdAt'] = code_data['createdAt'].strftime('%Y-%m-%d %H:%M:%S')
            codes.append(code_data)
        return jsonify(codes)
    except Exception as e:
        return jsonify([]), 500

@app.route('/api/validate-code', methods=['POST'])
def validate_code():
    if not db: return jsonify({"success": False, "message": "DB 연결 실패"}), 500
    code = request.get_json().get('code', '').upper()
    code_doc = db.collection('access_codes').document(code).get()
    if not code_doc.exists: return jsonify({"success": False, "message": "유효하지 않은 코드입니다."})
    if code_doc.to_dict().get('isUsed'): return jsonify({"success": False, "message": "이미 사용된 코드입니다."})
    return jsonify({"success": True})


# --- 4. Flask 앱 실행 ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)











