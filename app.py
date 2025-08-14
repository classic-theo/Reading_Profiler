import os
import json
import random
from datetime import datetime
from flask import Flask, render_template, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore
import gspread
# oauth2client는 더 이상 사용하지 않으므로 삭제합니다.

# --- 1. Flask 앱 초기화 ---
app = Flask(__name__, template_folder='templates')

# --- 2. 외부 서비스 초기화 ---

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

    # 이미 초기화되었는지 확인하여 중복 초기화 방지
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
except Exception as e:
    print(f"Firebase 초기화 실패: {e}")
    db = None

# Google Sheets 초기화
try:
    # ✨ 해결책: gspread의 최신 인증 방식으로 변경
    google_creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS_JSON')
    if google_creds_json:
        creds_dict = json.loads(google_creds_json)
        # 딕셔너리에서 직접 서비스 계정 클라이언트 생성
        gc = gspread.service_account_from_dict(creds_dict)
        print("Google Sheets 환경 변수에서 초기화 성공")
    else:
        print("Google Sheets 환경 변수를 찾지 못했습니다. 로컬 파일 'google_sheets_credentials.json'을 시도합니다.")
        # 파일에서 직접 서비스 계정 클라이언트 생성
        gc = gspread.service_account(filename='google_sheets_credentials.json')
        print("Google Sheets 파일에서 초기화 성공")
        
    # "CSI 독서 프로파일러 결과" 라는 이름의 구글 시트 열기
    sheet = gc.open("CSI 독서 프로파일러 결과").sheet1
    print("Google Sheets 시트 열기 성공")
except Exception as e:
    print(f"Google Sheets 초기화 실패: {e}")
    sheet = None

# --- 3. 라우팅 (API 엔드포인트) ---

@app.route('/')
def serve_index():
    return render_template('index.html')

@app.route('/admin')
def serve_admin():
    return render_template('admin.html')

@app.route('/validate-code', methods=['POST'])
def validate_code():
    data = request.get_json()
    code = data.get('code')
    if code: 
        print(f"Access code received and validated: {code}")
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "유효하지 않은 코드입니다."})


@app.route('/get-test', methods=['POST'])
def get_test():
    mock_questions = [
        { 'id': 'q1', 'type': 'multiple_choice', 'title': '[사건 파일 No.301] - 선호하는 정보 유형', 'passage': '새로운 사건 정보를 접할 때, 당신의 본능은 어떤 자료로 가장 먼저 향합니까? 사건의 전체적인 그림을 보는 것을 선호하나요, 아니면 핵심 인물이나 구체적인 증거에 집중하는 편인가요?', 'options': ['사건 개요 및 요약 보고서', '관련 인물들의 상세 프로필', '사건 현장 사진 및 증거물 목록', '과거 유사 사건 기록'], 'category': 'non-literature' },
        { 'id': 'q2', 'type': 'multiple_choice', 'title': '[사건 파일 No.302] - 분석 환경', 'passage': '복잡하고 민감한 사건을 분석해야 할 때, 당신의 집중력이 가장 높아지는 환경은 어떤 모습입니까?', 'options': ['완벽하게 조용한 개인 분석실', '동료들과 토론할 수 있는 회의실', '음악이 흐르는 편안한 공간', '정보가 계속 업데이트되는 상황실'], 'category': 'non-literature' },
        { 'id': 'q3', 'type': 'essay', 'title': '[사건 파일 No.303] - 당신의 분석 방식', 'passage': '당신에게 풀리지 않는 미제 사건 파일이 주어졌습니다. 어떤 방식으로 접근하여 해결의 실마리를 찾아나갈 것인지 구체적으로 서술하시오.', 'minChars': 100, 'category': 'non-literature' },
        { 'id': 'q4', 'type': 'multiple_choice', 'title': '[사건 파일 No.304] - 결정적 증거', 'passage': '네 가지의 결정적인 증거가 눈앞에 있습니다. 당신의 직관과 논리가 가리키는 가장 신뢰도 높은 증거는 무엇입니까?', 'options': ['범인의 자백 영상', '범행 도구에서 발견된 지문', '피해자의 다잉 메시지', '신뢰할 수 있는 목격자의 증언'], 'category': 'literature' },
        { 'id': 'q5', 'type': 'essay', 'title': '[사건 파일 No.305] - 미래 여행', 'passage': '당신은 100년 뒤 미래로 시간 여행을 떠날 수 있는 티켓 한 장을 얻었습니다. 프로파일러로서, 미래 사회의 어떤 점을 가장 먼저 확인하여 현재의 범죄 예방에 활용하시겠습니까? 그 이유와 함께 서술하시오.', 'minChars': 100, 'category': 'literature' },
    ]
    return jsonify(mock_questions)


@app.route('/submit-result', methods=['POST'])
def submit_result():
    if not db:
        return jsonify({"success": False, "error": "Database connection failed"}), 500

    data = request.get_json()
    user_info = data.get('userInfo', {})
    answers = data.get('answers', [])
    
    score = 0
    correct_answers = 0
    total_questions = len(answers)
    incorrect_notes = []
    total_response_length = 0
    
    category_performance = {'literature': {'correct': 0, 'total': 0}, 'non-literature': {'correct': 0, 'total': 0}}

    for i, ans_data in enumerate(answers):
        question_id = ans_data.get('questionId')
        user_answer = ans_data.get('answer')
        
        question_data = next((q for q in get_test().get_json() if q['id'] == question_id), None)
        if not question_data:
            continue

        category = question_data.get('category', 'unknown')
        question_type = question_data.get('type')
        
        if category in category_performance:
            category_performance[category]['total'] += 1

        if question_type == 'essay':
            total_response_length += len(user_answer)
        
        is_correct = (i % 2 != 0)
        
        if is_correct:
            score += 20
            correct_answers += 1
            if category in category_performance:
                category_performance[category]['correct'] += 1
        else:
            incorrect_notes.append({
                'question': question_data.get('title'),
                'user_answer': user_answer,
                'correct_answer': '정답 예시 (DB에서 가져와야 함)',
                'explanation': '상세 해설 (DB에서 가져와야 함)'
            })

    final_report = generate_detailed_report(
        score, total_questions, correct_answers, 
        category_performance, total_response_length, incorrect_notes
    )

    try:
        if sheet:
            row = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                user_info.get('name', 'N/A'), 
                user_info.get('age', 'N/A'), 
                score, 
                final_report['overall_comment'].replace('\n\n', ' ').replace('\n', ' ')
            ]
            sheet.append_row(row)
    except Exception as e:
        print(f"Google Sheets 저장 오류: {e}")

    return jsonify({"success": True, "report": final_report})


def generate_detailed_report(score, total_questions, correct_answers, category_performance, total_response_length, incorrect_notes):
    report = {}
    
    essay_questions_count = sum(1 for q in get_test().get_json() if q['type'] == 'essay')
    agility_score = (total_response_length / essay_questions_count) if essay_questions_count > 0 else 0
    agility_comment = ""
    if agility_score > 150:
        agility_comment = "사고의 폭이 넓고, 주어진 문제에 대해 풍부하고 구체적으로 생각을 확장하는 능력이 뛰어납니다."
    elif agility_score > 80:
        agility_comment = "문제의 핵심을 파악하고 간결하게 표현하는 능력을 갖추고 있습니다."
    else:
        agility_comment = "문제에 대해 신중하게 접근하는 경향이 있습니다."

    lit_perf = category_performance['literature']
    nonlit_perf = category_performance['non-literature']
    lit_rate = (lit_perf['correct'] / lit_perf['total']) * 100 if lit_perf['total'] > 0 else -1
    nonlit_rate = (nonlit_perf['correct'] / nonlit_perf['total']) * 100 if nonlit_perf['total'] > 0 else -1
    
    bias_comment = ""
    if lit_rate == -1 or nonlit_rate == -1:
        bias_comment = "문학/비문학 데이터가 충분하지 않아 분석이 어렵습니다."
    elif abs(lit_rate - nonlit_rate) < 15:
        bias_comment = "문학과 비문학 영역 모두에서 균형 잡힌 독해 능력을 보여주고 있습니다."
    elif lit_rate > nonlit_rate:
        bias_comment = "문학 작품에 대한 이해도가 특히 뛰어납니다."
    else:
        bias_comment = "비문학 텍스트의 정보를 정확하고 논리적으로 파악하는 능력이 뛰어납니다."

    overall_comment = (
        f"총 {total_questions}문제 중 {correct_answers}문제를 맞추셨습니다. 전체 점수는 {score}점입니다.\n\n"
        f"**[독서 편향성 분석]**\n{bias_comment}\n\n"
        f"**[인지 민첩성 분석]**\n{agility_comment}\n\n"
        "위 분석 결과를 바탕으로 약점을 보완하시길 바랍니다."
    )

    report['score'] = score
    report['overall_comment'] = overall_comment
    report['cognitive_agility'] = agility_comment
    report['reading_bias'] = bias_comment
    report['incorrect_notes'] = incorrect_notes

    return report

# --- 4. Flask 앱 실행 ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)


