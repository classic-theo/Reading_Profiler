import os
import json
import random
import string
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore
import gspread
import requests # Gemini API 호출을 위해 requests 라이브러리 추가

# --- 1. Flask 앱 초기화 ---
app = Flask(__name__, template_folder='templates')

# --- 2. 외부 서비스 초기화 ---
db = None
sheet = None
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY') # Render ac환경 변수에서 Gemini API 키 불러오기

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

# ✨ AI 문제 생성 API
@app.route('/api/generate-question', methods=['POST'])
def generate_question_from_ai():
    if not GEMINI_API_KEY:
        return jsonify({"success": False, "message": "Gemini API 키가 설정되지 않았습니다."}), 500

    data = request.get_json()
    age = data.get('age', '15')
    category = data.get('category', 'logic')
    
    prompt = f"""
    독서력 평가 문제 출제 전문가로서, 다음 조건에 맞는 객관식 문제를 생성해줘.

    1.  **대상 연령:** {age}세
    2.  **측정 능력:** {category} (comprehension, logic, inference, creativity, critical_thinking 중 하나)
    3.  **지문 (passage):** 측정 능력에 맞는 2~3문단 길이의 흥미로운 지문을 직접 창작해줘.
    4.  **문제 (title):** 지문의 내용을 바탕으로 한 객관식 질문을 만들어줘. (예: [사건 파일 No.XXX] - {category})
    5.  **선택지 (options):** 4개의 선택지를 배열(array) 형태로 만들어줘. 그 중 하나는 명확한 정답이어야 해.
    6.  **정답 (answer):** 4개의 선택지 중 정답에 해당하는 문장을 정확히 적어줘.

    **출력 형식은 반드시 아래의 JSON 스키마를 따라야 해:**
    {{
      "title": "string",
      "passage": "string",
      "type": "multiple_choice",
      "options": ["string", "string", "string", "string"],
      "answer": "string",
      "category": "{category}",
      "targetAge": "{age}"
    }}
    """

    # Gemini API 호출
    try:
        # ✨ 해결책: 안정적인 최신 모델 이름(gemini-1.5-pro-latest)으로 변경
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro-latest:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        headers = {'Content-Type': 'application/json'}
        
        response = requests.post(url, json=payload)
        response.raise_for_status() # HTTP 오류 발생 시 예외 처리
        
        result_text = response.json()['candidates'][0]['content']['parts'][0]['text']
        
        if result_text.strip().startswith("```json"):
            result_text = result_text.strip()[7:-3]

        question_data = json.loads(result_text)

        if db:
            doc_ref, doc_id = db.collection('questions').add(question_data)
            print(f"AI 생성 문제 저장 성공. Document ID: {doc_id.id}")
            return jsonify({"success": True, "message": "AI가 새로운 문제를 생성하여 데이터베이스에 추가했습니다."})
        else:
            return jsonify({"success": False, "message": "DB 연결 실패"}), 500

    except Exception as e:
        print(f"AI 문제 생성 오류: {e}")
        return jsonify({"success": False, "message": f"AI 문제 생성 중 오류 발생: {e}"}), 500


# (이하 다른 API들은 기존과 동일)
@app.route('/api/get-test', methods=['POST'])
def get_test():
    if not db: return jsonify([]), 500
    try:
        questions_ref = db.collection('questions').stream()
        all_questions = [doc.to_dict() for doc in questions_ref]
        
        if not all_questions:
             return jsonify([{'id': 'temp', 'title': '임시 문제', 'passage': '현재 문제 은행에 문제가 없습니다. Admin 페이지에서 AI로 문제를 생성해주세요.', 'type': 'multiple_choice', 'options':['확인'], 'answer':'확인'}])
        
        return jsonify(random.sample(all_questions, min(len(all_questions), 7)))
    except Exception as e:
        print(f"문제 불러오기 오류: {e}")
        return jsonify([]), 500

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
        for code in codes_ref:
            code_data = code.to_dict()
            code_data['code'] = code.id
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

@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    # ... (생략)
    pass

# --- 4. Flask 앱 실행 ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)




