import os
import json
import string
import random
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, render_template, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore

# --- Firebase 초기화 ---
creds_json_str = os.environ.get('GOOGLE_CREDENTIALS')
try:
    # Render 환경 변수에서 인증 정보 가져오기
    if creds_json_str:
        creds_dict = json.loads(creds_json_str)
        cred = credentials.Certificate(creds_dict)
    else: # 로컬 테스트 환경
        cred = credentials.Certificate("credentials.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firestore와 성공적으로 연결되었습니다.")
except Exception as e:
    print(f"Firestore 연결 오류: {e}")
    db = None

# --- 구글 시트 연동 ---
try:
    # (기존 구글 시트 연동 코드는 그대로 유지)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    if creds_json_str:
        creds_dict = json.loads(creds_json_str)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open("독서력 진단 결과").sheet1
    print("Google Sheets와 성공적으로 연결되었습니다.")
except Exception as e:
    print(f"Google Sheets 연결 오류: {e}")
    sheet = None

# --- 초기 설정 ---
app = Flask(__name__, template_folder='templates')

# --- 라우트 (Routes) ---
@app.route('/')
def home():
    """메인 사용자 화면을 렌더링합니다."""
    return render_template('index.html')

@app.route('/admin')
def admin():
    """관리자 페이지를 렌더링합니다."""
    # 현재 관리자 기능은 코드 생성 -> DB 직접 관리로 변경될 예정
    # 지금은 간단한 안내 페이지만 제공합니다.
    return "<h1>관리자 페이지</h1><p>문제 은행은 이제 Firebase Console에서 직접 관리합니다.</p>"

@app.route('/get-test', methods=['POST'])
def get_test():
    """나이에 맞는 문제를 Firestore에서 가져옵니다."""
    if not db:
        return jsonify({"error": "Database connection failed"}), 500
    
    age = int(request.get_json().get('age', 0))
    
    if age <= 12: age_group = 'low'
    elif age <= 16: age_group = 'mid'
    else: age_group = 'high'
    
    try:
        questions_ref = db.collection('questions').where('age_group', '==', age_group).stream()
        questions = [q.to_dict() for q in questions_ref]
        
        # 15개 문항을 균형있게 추출하는 로직 (이전과 동일)
        if len(questions) < 15:
            random.shuffle(questions)
            return jsonify(questions)
        else:
            # (향후 문항 수가 많아지면 여기에 문학/비문학 균형 추출 로직 추가)
            return jsonify(random.sample(questions, 15))

    except Exception as e:
        print(f"Firestore에서 문제 가져오기 오류: {e}")
        return jsonify({"error": "Could not fetch questions"}), 500

@app.route('/submit-result', methods=['POST'])
def submit_result():
    """테스트 결과를 받아 분석하고 Firestore와 Google Sheets에 저장합니다."""
    data = request.get_json()
    user_info = data.get('userInfo')
    answers = data.get('answers')
    # ...
    
    # Firestore에 결과 저장
    if db:
        try:
            # 사용자별로 결과를 저장하기 위해 user_id (핸드폰 번호)를 사용
            user_id = user_info.get('phone')
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            doc_ref = db.collection('users').document(user_id).collection('results').document(timestamp)
            
            # 저장할 데이터 구성
            result_data = {
                'userInfo': user_info,
                'analysis': {}, # 여기에 분석 결과 삽입
                'coaching_guide': "코칭 가이드 내용",
                'submitted_at': firestore.SERVER_TIMESTAMP
            }
            doc_ref.set(result_data)
            print(f"{user_id} 사용자의 결과를 Firestore에 저장했습니다.")
        except Exception as e:
            print(f"Firestore 저장 오류: {e}")

    # Google Sheets에도 요약본 저장 (기존 로직 유지)
    if sheet:
        # ...
        pass

    return jsonify({'success': True, 'message': '결과가 성공적으로 제출되었습니다.'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)), debug=False)
