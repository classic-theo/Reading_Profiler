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
        gc = gspread.service_account(filename='google_sheets_credentials.json')
        print("Google Sheets 파일에서 초기화 성공")
        
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

@app.route('/api/get-test', methods=['POST'])
def get_test():
    mock_questions = [
        { 'id': 'q1', 'type': 'multiple_choice', 'title': '[사건 파일 No.301] - 정보 이해력', 'passage': '다음 지문을 읽고 내용과 일치하는 것을 고르시오.', 'options': ['옵션1', '옵션2', '정답 옵션', '옵션4'], 'category': 'comprehension', 'answer': '정답 옵션'},
        { 'id': 'q2', 'type': 'essay', 'title': '[사건 파일 No.302] - 창의적 서술력', 'passage': '주어진 상황에 대해 창의적인 해결책을 서술하시오.', 'minChars': 100, 'category': 'creativity'},
        { 'id': 'q3', 'type': 'multiple_choice', 'title': '[사건 파일 No.303] - 논리 분석력', 'passage': '다음 주장의 논리적 오류를 찾아내시오.', 'options': ['옵션1', '정답 옵션', '옵션3', '옵션4'], 'category': 'logic', 'answer': '정답 옵션'},
        { 'id': 'q4', 'type': 'multiple_choice', 'title': '[사건 파일 No.304] - 단서 추론력', 'passage': '다음 단서들을 종합하여 범인을 추론하시오.', 'options': ['용의자 A', '용의자 B', '용의자 C', '정답 용의자'], 'category': 'inference', 'answer': '정답 용의자'},
    ]
    return jsonify(mock_questions)


@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    if not db: return jsonify({"success": False, "error": "DB 연결 실패"}), 500
    
    data = request.get_json()
    user_info = data.get('userInfo', {})
    answers = data.get('answers', [])
    access_code = user_info.get('accessCode', '').upper()

    # ✨ 1. 상세 분석 데이터 생성
    # 실제 문제 데이터를 불러와서 채점해야 함 (현재는 Mock 데이터 기준)
    questions_data = get_test().get_json()
    
    # 능력치별 점수 계산
    skill_scores = {
        'comprehension': 0, 'logic': 0, 'inference': 0, 
        'creativity': 0, 'critical_thinking': 0
    }
    
    # 카테고리별 정답률 계산
    category_performance = {'comprehension': {'correct': 0, 'total': 0}, 'logic': {'correct': 0, 'total': 0}, 'inference': {'correct': 0, 'total': 0}}

    total_response_length = 0

    for ans in answers:
        question = next((q for q in questions_data if q['id'] == ans['questionId']), None)
        if not question: continue
        
        category = question.get('category')
        
        if question['type'] == 'multiple_choice':
            if category in category_performance:
                category_performance[category]['total'] += 1
            if ans['answer'] == question.get('answer'):
                if category in skill_scores:
                    skill_scores[category] += random.randint(80, 95) # 정답일 경우 높은 점수
                if category in category_performance:
                    category_performance[category]['correct'] += 1
            else:
                if category in skill_scores:
                    skill_scores[category] += random.randint(40, 60) # 오답일 경우 낮은 점수
        
        elif question['type'] == 'essay':
            # 서술형은 글자 수에 따라 점수 부여 (예시)
            length = len(ans['answer'])
            total_response_length += length
            if length > 150:
                skill_scores['creativity'] = random.randint(85, 100)
            elif length > 100:
                skill_scores['creativity'] = random.randint(70, 85)
            else:
                skill_scores['creativity'] = random.randint(50, 70)

    # 비판적 사고력은 종합 점수로 계산 (예시)
    total_correct = sum(cat['correct'] for cat in category_performance.values())
    total_q = sum(cat['total'] for cat in category_performance.values())
    if total_q > 0:
        skill_scores['critical_thinking'] = int((total_correct / total_q) * 100)

    # 최종 분석 보고서 생성
    report = {
        "skill_scores": skill_scores,
        "overall_comment": f"**{user_info.get('name')}님, 분석이 완료되었습니다.**\n\n- **정보 이해력:** 지문의 핵심 내용을 정확히 파악하는 능력을 보여주었습니다.\n- **논리 분석력:** 제시된 정보 간의 관계를 논리적으로 분석하는 데 강점을 보입니다.\n- **창의적 서술력:** 자신의 생각을 풍부하고 독창적으로 표현하는 능력이 돋보입니다.\n\n상세한 코칭 가이드는 관리자에게 전달됩니다."
    }

    # 접근 코드 사용 처리
    if access_code:
        try:
            db.collection('access_codes').document(access_code).update({'isUsed': True, 'userName': user_info.get('name')})
        except Exception as e:
            print(f"접근 코드 업데이트 오류: {e}")
    
    # 구글 시트에 결과 저장
    try:
        if sheet:
            row = [datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), user_info.get('name', 'N/A'), user_info.get('age', 'N/A')] + list(skill_scores.values())
            sheet.append_row(row)
            print("Google Sheets에 결과 저장 성공")
    except Exception as e:
        print(f"Google Sheets 저장 오류: {e}")

    return jsonify({"success": True, "report": report})

# --- 4. Flask 앱 실행 ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)
