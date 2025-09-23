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
    print("🚨 중요: 시트 이름이 정확한지, 서비스 계정에 '편집자'로 공유되었는지 확인해주세요.")

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
    if not db: return jsonify({"success": False, "message": "DB 연결 실패"}), 500
    try:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        code_ref = db.collection('access_codes').document(code)
        
        if code_ref.get().exists: return generate_code()

        code_ref.set({
            'createdAt': datetime.now(timezone.utc),
            'isUsed': False, 'userName': None
        })
        return jsonify({"success": True, "code": code})
    except Exception as e:
        return jsonify({"success": False, "message": f"코드 생성 오류: {e}"}), 500

# --- 사용자 테스트 API ---
@app.route('/api/validate-code', methods=['POST'])
def validate_code_route():
    if not db: return jsonify({"success": False, "message": "DB 연결 실패"}), 500
    code = request.get_json().get('code', '').upper()
    code_ref = db.collection('access_codes').document(code)
    code_doc = code_ref.get()
    if not code_doc.exists: return jsonify({"success": False, "message": "유효하지 않은 코드입니다."})
    if code_doc.to_dict().get('isUsed'): return jsonify({"success": False, "message": "이미 사용된 코드입니다."})
    return jsonify({"success": True})

@app.route('/api/get-test', methods=['POST'])
def get_test():
    # ... (이전과 동일한 실제 문제 추출 로직) ...
    # Mock data for demonstration purposes
    mock_questions = [
        {'id': 'q1', 'title': '[사건 파일 No.101]', 'question': '이 글의 핵심 주제로 가장 적절한 것은?', 'passage': '지구 온난화는 전 지구적 기온 및 해수면 상승을 야기하는 현상이다...', 'options': ['지구 온난화의 원인', '해수면 상승의 심각성', '온실가스 감축 방안', '기후 변화의 다양한 양상'], 'answer': '기후 변화의 다양한 양상', 'type': 'multiple_choice', 'category': 'theme'},
        {'id': 'q2', 'title': '[사건 파일 No.102]', 'question': '이 글을 바탕으로 알 수 있는 사실이 아닌 것은?', 'passage': '인공지능 기술은 빠르게 발전하여 우리 삶의 많은 부분을 바꾸고 있다...', 'options': ['인공지능은 일자리를 대체할 수 있다', '인공지능은 의료 분야에서 활용된다', '인공지능의 모든 윤리적 문제는 해결되었다', '인공지능은 데이터 학습이 필수적이다'], 'answer': '인공지능의 모든 윤리적 문제는 해결되었다', 'type': 'multiple_choice', 'category': 'inference'},
        {'id': 'q3', 'title': '[사건 파일 No.103]', 'question': '이 글에 대한 자신의 생각을 100자 이상으로 서술하시오.', 'passage': 'SNS의 발달은 소통의 방식을 혁신적으로 바꾸었지만, 동시에 가짜뉴스 확산과 사생활 침해라는 부작용을 낳았다.', 'type': 'essay', 'category': 'essay'}
    ]
    # 카테고리 한글화
    for q in mock_questions:
        q['category_kr'] = CATEGORY_MAP.get(q.get('category'), '기타')
    return jsonify(mock_questions)


def generate_final_report(results):
    scores = { "정보 이해력": [], "논리 분석력": [], "단서 추론력": [], "비판적 사고력": [], "창의적 서술력": [] }
    metacognition = {"confident_correct": 0, "confident_error": 0, "unsure_correct": 0, "unsure_error": 0}
    
    for r in results:
        question_data = r['question']
        score_category = SCORE_CATEGORY_MAP.get(question_data['category'])
        is_correct = (question_data.get('type') != 'essay' and r['answer'] == question_data.get('answer')) or \
                     (question_data.get('type') == 'essay' and len(r.get('answer', '')) >= 100)
        
        if score_category:
            scores[score_category].append(100 if is_correct else 0)

        confidence = r.get('confidence', 'unsure')
        if confidence == 'confident':
            metacognition['confident_correct' if is_correct else 'confident_error'] += 1
        else:
            metacognition['unsure_correct' if is_correct else 'unsure_error'] += 1

    final_scores = {cat: round((sum(s) / len(s))) if s else 0 for cat, s in scores.items()}
    
    total_time = sum(r.get('time', 0) for r in results)
    avg_time_per_question = total_time / len(results) if results else 0
    speed_score = min(100, max(0, round(100 - (avg_time_per_question - 30) * 2))) # 30초 기준
    final_scores["문제 풀이 속도"] = speed_score

    # ... (추천 활동 및 종합 소견 생성 로직) ...
    weakest_category = "단서 추론력" # Placeholder
    final_report = f"""### 종합 소견
전반적으로 우수한 독해 능력을 보여주셨습니다. 특히 메타인지 분석 결과, 자신이 아는 것과 모르는 것을 잘 구분하는 능력이 돋보입니다.

### 보완점
이번 테스트에서 가장 보완이 필요한 부분은 **'{weakest_category}'** 입니다. '개념 오적용 영역'에 해당하는 문제가 있었다면, 해당 개념을 다시 한번 복습하는 것이 중요합니다.
"""
    recommendations = [{"skill": "단서 추론력 강화", "text": "관련 추천 활동 텍스트입니다."}]

    return final_scores, metacognition, final_report, recommendations


@app.route('/api/submit-result', methods=['POST'])
def submit_result_route():
    # ... (데이터 수집 및 DB/Sheet 저장은 이전과 동일) ...
    data = request.get_json()
    user_info = data.get('userInfo', {})
    results = data.get('results', [])
    
    final_scores, metacognition, final_report, recommendations = generate_final_report(results)
    
    # Google Sheets에 데이터 기록 (예시)
    if sheet:
        try:
            row = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                user_info.get('name'),
                user_info.get('age'),
                final_scores.get('정보 이해력', 0),
                # ... other scores ...
                final_report
            ]
            sheet.append_row(row)
        except Exception as e:
            print(f"Google Sheets 저장 오류: {e}")

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




