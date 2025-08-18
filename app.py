import os
import json
import random
import string
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore
import gspread

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
        print("Firebase 환경 변수에서 초기화 성공")
    else:
        print("Firebase 환경 변수를 찾지 못했습니다. 로컬 파일 'firebase_credentials.json'을 시도합니다.")
        cred = credentials.Certificate('firebase_credentials.json')
        print("Firebase 파일에서 초기화 성공")

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
except Exception as e:
    print(f"Firebase 초기화 실패: {e}")

# Google Sheets 초기화
try:
    google_creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS_JSON')
    SHEET_NAME = "독서력 진단 결과"

    if google_creds_json:
        creds_dict = json.loads(google_creds_json)
        gc = gspread.service_account_from_dict(creds_dict)
        print("Google Sheets 환경 변수에서 초기화 성공")
    else:
        print("Google Sheets 환경 변수를 찾지 못했습니다. 로컬 파일 'google_sheets_credentials.json'을 시도합니다.")
        gc = gspread.service_account(filename='google_sheets_credentials.json')
        print("Google Sheets 파일에서 초기화 성공")
        
    sheet = gc.open(SHEET_NAME).sheet1
    print(f"'{SHEET_NAME}' 시트 열기 성공")
except gspread.exceptions.SpreadsheetNotFound:
    print(f"Google Sheets 초기화 실패: '{SHEET_NAME}' 시트를 찾을 수 없습니다.")
    print("🚨 중요: 시트 이름이 정확한지, 서비스 계정에 '편집자'로 공유되었는지 확인해주세요.")
except Exception as e:
    # ✨ 해결책 2: 더 자세한 오류 내용 출력
    print(f"Google Sheets 초기화 실패: 예상치 못한 오류 발생")
    print(f"오류 타입: {type(e).__name__}")
    print(f"오류 내용: {e}")


# --- 3. 라우팅 (API 엔드포인트) ---

@app.route('/')
def serve_index():
    return render_template('index.html')

@app.route('/admin')
def serve_admin():
    return render_template('admin.html')

# ✨ 해결책 1: API 경로를 '/api/...'로 명확하게 분리
@app.route('/api/generate-code', methods=['POST'])
def generate_code():
    if not db: return jsonify({"success": False, "message": "DB 연결 실패"}), 500
    try:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        code_ref = db.collection('access_codes').document(code)
        if code_ref.get().exists: return generate_code()
        code_ref.set({'createdAt': datetime.now(timezone.utc), 'isUsed': False, 'userName': None})
        print(f"새 접근 코드 생성: {code}")
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

@app.route('/api/get-test', methods=['POST'])
def get_test():
    # ... (생략)
    return jsonify([])

@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    # ... (생략)
    return jsonify({"success": True, "report": {"overall_comment": "분석 완료"}})

# --- 4. Flask 앱 실행 ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)



