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
try:
    # Render 환경 변수에서 인증 정보 가져오기
    creds_json_str = os.environ.get('GOOGLE_CREDENTIALS')
    if creds_json_str:
        creds_dict = json.loads(creds_json_str)
        cred = credentials.Certificate(creds_dict)
    else: # 로컬 환경
        cred = credentials.Certificate("credentials.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firestore와 성공적으로 연결되었습니다.")
except Exception as e:
    print(f"Firestore 연결 오류: {e}")
    db = None

# --- 구글 시트 연동 ---
try:
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    if 'creds_dict' in locals():
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
active_codes = {}

# --- 관리자 페이지 ---
@app.route('/admin')
def admin_dashboard():
    """관리자 페이지를 렌더링합니다."""
    return render_template('admin.html')

@app.route('/admin/generate-code', methods=['POST'])
def admin_generate_code():
    """새로운 접속 코드를 생성합니다."""
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    active_codes[code] = {'status': 'active', 'created_at': datetime.now().isoformat()}
    return jsonify({'access_code': code})

# --- 사용자 페이지 ---
@app.route('/')
def home():
    """메인 사용자 화면을 렌더링합니다."""
    return render_template('index.html')

@app.route('/validate-code', methods=['POST'])
def validate_code():
    """사용자가 입력한 코드를 검증합니다."""
    user_code = request.get_json().get('code')
    if user_code in active_codes:
        del active_codes[user_code]
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': '유효하지 않은 코드입니다.'})

@app.route('/get-test', methods=['POST'])
def get_test():
    """나이에 맞는 문제를 Firestore에서 가져옵니다."""
    if not db:
        return jsonify({"error": "Database connection failed"}), 500
    
    age = int(request.get_json().get('age', 0))
    questions = assemble_test_for_age(age, 15)
    return jsonify(questions)

@app.route('/submit-result', methods=['POST'])
def submit_result():
    """테스트 결과를 받아 분석하고 저장합니다."""
    data = request.get_json()
    user_info = data.get('userInfo')
    answers = data.get('answers')
    solving_times = data.get('solvingTimes')
    questions = data.get('questions')
    
    # 분석 로직 호출
    analysis_result = analyze_answers(questions, answers)
    genre_bias_result = analyze_genre_bias(questions, answers)
    time_analysis_result = analyze_solving_time(questions, solving_times, answers)
    
    analysis_result['genre_bias'] = genre_bias_result
    analysis_result['time_analysis'] = time_analysis_result
    
    coaching_guide = generate_coaching_guide(analysis_result, questions, answers)
    theoretical_basis = "본 테스트는 블룸의 교육 목표 분류학, 인지 부하 이론, 스키마 이론, 메타인지 전략 등을 종합적으로 고려하여 설계된 다차원 독서력 진단 프로그램입니다."

    # Google Sheets에 저장
    if sheet:
        try:
            row_to_insert = [
                datetime.now().strftime("%Y-%m-%d %H:%M"), user_info.get('name'), user_info.get('age'),
                user_info.get('phone'), json.dumps(analysis_result, ensure_ascii=False), coaching_guide
            ]
            sheet.append_row(row_to_insert, value_input_option='USER_ENTERED')
        except Exception as e:
            print(f"Google Sheets 저장 오류: {e}")
    
    return jsonify({
        'success': True, 
        'analysis': analysis_result,
        'coaching_guide': coaching_guide,
        'theoretical_basis': theoretical_basis
    })

# --- Helper Functions ---
def assemble_test_for_age(age, num_questions):
    """나이에 맞춰 Firestore에서 문제를 가져와 조립합니다."""
    if age <= 12: age_group = 'low'
    elif age <= 16: age_group = 'mid'
    else: age_group = 'high'
    
    try:
        questions_ref = db.collection('questions').where('age_group', '==', age_group).stream()
        candidate_questions = [q.to_dict() for q in questions_ref]
    except Exception as e:
        print(f"Firestore에서 문제 가져오기 오류: {e}")
        return []

    if not candidate_questions: return []
    
    if len(candidate_questions) < num_questions:
        random.shuffle(candidate_questions)
        return candidate_questions

    # (이하 문학/비문학 균형 추출 로직은 이전과 동일)
    # ...
    return random.sample(candidate_questions, num_questions)


def analyze_answers(questions, answers):
    # (이하 모든 분석 및 코칭 가이드 생성 함수는 이전과 동일합니다)
    # ...
    pass

def analyze_genre_bias(questions, answers):
    # ...
    pass

def analyze_solving_time(questions, solving_times, answers):
    # ...
    pass

def generate_coaching_guide(result, questions, answers):
    # ...
    pass

def skill_to_korean(skill):
    # ...
    pass

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)), debug=False)

