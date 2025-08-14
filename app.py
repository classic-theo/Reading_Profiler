import os
import json
import random
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_from_directory
import firebase_admin
from firebase_admin import credentials, firestore
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. Flask 앱 및 외부 서비스 초기화 ---
app = Flask(__name__, static_folder='.', static_url_path='')

# Firebase 초기화
# 'firebase_credentials.json' 파일이 프로젝트 폴더에 있어야 합니다.
try:
    cred = credentials.Certificate('firebase_credentials.json')
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase 초기화 성공")
except Exception as e:
    print(f"Firebase 초기화 실패: {e}")
    db = None

# Google Sheets 초기화
# 'google_sheets_credentials.json' 파일과 API 권한 설정이 필요합니다.
try:
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('google_sheets_credentials.json', scope)
    client = gspread.authorize(creds)
    # "CSI 독서 프로파일러 결과" 라는 이름의 구글 시트가 있어야 합니다.
    sheet = client.open("CSI 독서 프로파일러 결과").sheet1
    print("Google Sheets 초기화 성공")
except Exception as e:
    print(f"Google Sheets 초기화 실패: {e}")
    sheet = None

# --- 2. 라우팅 (API 엔드포인트) ---

@app.route('/')
def serve_index():
    """
    기본 접속 시 index.html 파일을 렌더링합니다.
    """
    return send_from_directory('.', 'index.html')

@app.route('/get-test', methods=['POST'])
def get_test():
    """
    사용자 연령에 맞는 테스트 문항을 데이터베이스에서 가져옵니다.
    (현재는 Mock 데이터를 사용합니다)
    """
    # 실제 구현 시에는 Firestore에서 연령(age)에 맞는 문제를 필터링하여 가져옵니다.
    # 예: questions_ref = db.collection('questions').where('target_age', '==', age).stream()
    mock_questions = [
        { 'id': 'q1', 'type': 'multiple_choice', 'title': '[사건 파일 No.301] - 선호하는 정보 유형', 'passage': '새로운 사건 정보를 접할 때, 당신의 본능은 어떤 자료로 가장 먼저 향합니까? 사건의 전체적인 그림을 보는 것을 선호하나요, 아니면 핵심 인물이나 구체적인 증거에 집중하는 편인가요?', 'options': ['사건 개요 및 요약 보고서', '관련 인물들의 상세 프로필', '사건 현장 사진 및 증거물 목록', '과거 유사 사건 기록'], 'category': 'non-literature' },
        { 'id': 'q2', 'type': 'multiple_choice', 'title': '[사건 파일 No.302] - 분석 환경', 'passage': '복잡하고 민감한 사건을 분석해야 할 때, 당신의 집중력이 가장 높아지는 환경은 어떤 모습입니까?', 'options': ['완벽하게 조용한 개인 분석실', '동료들과 토론할 수 있는 회의실', '음악이 흐르는 편안한 공간', '정보가 계속 업데이트되는 상황실'], 'category': 'non-literature' },
        { 'id': 'q3', 'type': 'essay', 'title': '[사건 파일 No.303] - 당신의 분석 방식', 'passage': '당신에게 풀리지 않는 미제 사건 파일이 주어졌습니다. 어떤 방식으로 접근하여 해결의 실마리를 찾아나갈 것인지 구체적으로 서술하시오.', 'minChars': 100, 'category': 'non-literature' },
        { 'id': 'q4', 'type': 'multiple_choice', 'title': '[사건 파일 No.304] - 결정적 증거', 'passage': '네 가지의 결정적인 증거가 눈앞에 있습니다. 당신의 직관과 논리가 가리키는 가장 신뢰도 높은 증거는 무엇입니까?', 'options': ['범인의 자백 영상', '범행 도구에서 발견된 지문', '피해자의 다잉 메시지', '신뢰할 수 있는 목격자의 증언'], 'category': 'literature' },
        { 'id': 'q5', 'type': 'essay', 'title': '[사건 파일 No.305] - 미래 여행', 'passage': '당신은 100년 뒤 미래로 시간 여행을 떠날 수 있는 티켓 한 장을 얻었습니다. 프로파일러로서, 미래 사회의 어떤 점을 가장 먼저 확인하여 현재의 범죄 예방에 활용하시겠습니까? 그 이유와 함께 서술하시오.', 'minChars': 100, 'category': 'literature' },
    ]
    # 실제 구현에서는 DB에서 가져온 문제들을 반환합니다.
    return jsonify(mock_questions)


@app.route('/submit-result', methods=['POST'])
def submit_result():
    """
    사용자의 답변을 받아 채점하고, 상세 분석 리포트를 생성합니다.
    """
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
        
        # Firestore 대신 Mock 데이터에서 문제 정보 가져오기 (실제로는 Firestore 사용)
        question_data = next((q for q in get_test().get_json() if q['id'] == question_id), None)
        if not question_data:
            continue

        category = question_data.get('category', 'unknown')
        question_type = question_data.get('type')
        
        if category in category_performance:
            category_performance[category]['total'] += 1

        if question_type == 'essay':
            total_response_length += len(user_answer)
        
        # --- 채점 로직 (예시) ---
        # 실제 채점 로직은 문제별 정답 데이터를 기반으로 구성해야 합니다.
        # 여기서는 홀수번 문제를 정답으로 간주하는 임시 로직을 사용합니다.
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

    # 결과 저장 (Google Sheets)
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
    """
    채점 결과를 바탕으로 과학적 이론에 근거한 심층 분석 리포트를 생성합니다.
    """
    report = {}
    
    # 인지민첩성 분석
    # 주관식 문항이 있을 경우에만 분석
    essay_questions_count = sum(1 for q in get_test().get_json() if q['type'] == 'essay')
    agility_score = (total_response_length / essay_questions_count) if essay_questions_count > 0 else 0
    agility_comment = ""
    if agility_score > 150:
        agility_comment = "사고의 폭이 넓고, 주어진 문제에 대해 풍부하고 구체적으로 생각을 확장하는 능력이 뛰어납니다. 이는 복잡한 정보를 빠르게 처리하고 다양한 관점을 고려하는 높은 인지 민첩성을 시사합니다."
    elif agility_score > 80:
        agility_comment = "문제의 핵심을 파악하고 간결하게 표현하는 능력을 갖추고 있습니다. 생각을 빠르게 구조화하지만, 때로는 조금 더 깊이 탐색하고 구체화하는 연습을 통해 분석의 깊이를 더할 수 있습니다."
    else:
        agility_comment = "문제에 대해 신중하게 접근하는 경향이 있습니다. 생각을 충분히 발전시키고 구체적인 근거를 들어 표현하는 훈련을 통해, 논리적 사고력과 표현의 명확성을 향상시킬 수 있습니다."

    # 독서편향성 분석
    lit_perf = category_performance['literature']
    nonlit_perf = category_performance['non-literature']
    lit_rate = (lit_perf['correct'] / lit_perf['total']) * 100 if lit_perf['total'] > 0 else -1
    nonlit_rate = (nonlit_perf['correct'] / nonlit_perf['total']) * 100 if nonlit_perf['total'] > 0 else -1
    
    bias_comment = ""
    if lit_rate == -1 or nonlit_rate == -1:
        bias_comment = "문학/비문학 데이터가 충분하지 않아 독서 편향성을 분석하기 어렵습니다."
    elif abs(lit_rate - nonlit_rate) < 15:
        bias_comment = "문학과 비문학 영역 모두에서 균형 잡힌 독해 능력을 보여주고 있습니다. 이는 다양한 유형의 텍스트를 편견 없이 수용하고, 각 글의 특성에 맞는 독해 전략을 효과적으로 사용하는 '통합적 사고'의 결과입니다."
    elif lit_rate > nonlit_rate:
        bias_comment = "문학 작품에 대한 이해도가 특히 뛰어납니다. 감성적 공감 능력과 서사 구조 파악에 강점을 보이지만, 논리적이고 분석적인 사고가 요구되는 비문학 텍스트 독해에도 꾸준한 관심을 기울인다면 통합적 사고력을 더욱 향상시킬 수 있습니다."
    else:
        bias_comment = "비문학 텍스트의 정보를 정확하고 논리적으로 파악하는 능력이 뛰어납니다. 사실 기반의 분석적 독해에 강점을 보이며, 여기에 문학 작품을 통한 감성적, 상징적 의미 파악 훈련을 더한다면 세상을 더 넓고 깊게 이해하는 눈을 갖게 될 것입니다."

    # 종합소견 생성
    overall_comment = (
        f"총 {total_questions}문제 중 {correct_answers}문제를 맞추셨습니다. 전체적인 독해력 점수는 {score}점입니다.\n\n"
        f"**[독서 편향성 분석]**\n{bias_comment}\n\n"
        f"**[인지 민첩성 분석]**\n{agility_comment}\n\n"
        "위 분석 결과를 바탕으로 오답 노트를 꼼꼼히 확인하여 약점을 보완하고, 강점을 더욱 발전시켜 나가시길 바랍니다."
    )

    report['score'] = score
    report['overall_comment'] = overall_comment
    report['cognitive_agility'] = agility_comment
    report['reading_bias'] = bias_comment
    report['incorrect_notes'] = incorrect_notes

    return report

# --- 3. Flask 앱 실행 ---
if __name__ == '__main__':
    # host='0.0.0.0'으로 설정하여 외부에서도 접속 가능하게 할 수 있습니다.
    app.run(debug=True, port=5001)








