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
    SHEET_NAME = "독서력 진단 결과" # 실제 시트 이름으로 변경

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
    print(f"Google Sheets 초기화 실패: 예상치 못한 오류 발생")
    print(f"오류 타입: {type(e).__name__}, 오류 내용: {e}")


# --- 3. 라우팅 (API 엔드포인트) ---

@app.route('/')
def serve_index():
    return render_template('index.html')

@app.route('/admin')
def serve_admin():
    return render_template('admin.html')

# ✨ API 경로는 '/api/...'로 통일
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
    mock_questions = [
        { 'id': 'q1', 'type': 'multiple_choice', 'title': '[사건 파일 No.301] - 선호하는 정보 유형', 'passage': '새로운 사건 정보를 접할 때, 당신의 본능은 어떤 자료로 가장 먼저 향합니까?', 'options': ['사건 개요 및 요약 보고서', '관련 인물들의 상세 프로필', '사건 현장 사진 및 증거물 목록', '과거 유사 사건 기록']},
        { 'id': 'q2', 'type': 'essay', 'title': '[사건 파일 No.303] - 당신의 분석 방식', 'passage': '당신에게 풀리지 않는 미제 사건 파일이 주어졌습니다. 어떤 방식으로 접근하여 해결의 실마리를 찾아나갈 것인지 구체적으로 서술하시오.', 'minChars': 100},
    ]
    return jsonify(mock_questions)

@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    if not db: return jsonify({"success": False, "error": "데이터베이스 연결 실패"}), 500
    data = request.get_json()
    user_info = data.get('userInfo', {})
    access_code = user_info.get('accessCode', '').upper()

    if access_code:
        try:
            db.collection('access_codes').document(access_code).update({'isUsed': True, 'userName': user_info.get('name')})
            print(f"접근 코드 사용 처리 완료: {access_code}")
        except Exception as e:
            print(f"접근 코드 업데이트 오류: {e}")

    final_report = {"overall_comment": f"**{user_info.get('name')}님, 분석이 완료되었습니다.**\n\n제출된 내용을 바탕으로 한 상세 보고서는 관리자에게 전달됩니다."}
    
    try:
        if sheet:
            row = [datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), user_info.get('name', 'N/A'), user_info.get('age', 'N/A')]
            sheet.append_row(row)
            print("Google Sheets에 결과 저장 성공")
    except Exception as e:
        print(f"Google Sheets 저장 오류: {e}")

    return jsonify({"success": True, "report": final_report})

# --- 4. Flask 앱 실행 ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)





