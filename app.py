import os
import json
import string
import random
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, render_template, jsonify, request, session, redirect, url_for

# --- 초기 설정 ---
app = Flask(__name__, template_folder='templates')
app.secret_key = 'csi-profiler-secret-key-!@#$'
# ADMIN_PASSWORD는 이제 사용되지 않습니다.
# ADMIN_PASSWORD = "change_this_password" 

# --- 구글 시트 연동 ---
try:
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_json_str = os.environ.get('GOOGLE_CREDENTIALS')
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

active_codes = {}

# --- 관리자 페이지 ---
@app.route('/admin')
def admin_dashboard():
    return render_template('admin.html')

@app.route('/admin/generate-code', methods=['POST'])
def admin_generate_code():
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    active_codes[code] = {'status': 'active', 'created_at': datetime.now().isoformat()}
    print(f"관리자가 새로운 접속 코드 생성: {code}")
    return jsonify({'access_code': code})

# --- 사용자 페이지 ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/validate-code', methods=['POST'])
def validate_code():
    user_code = request.get_json().get('code')
    if user_code in active_codes:
        del active_codes[user_code]
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': '유효하지 않은 코드입니다.'})

@app.route('/get-test', methods=['POST'])
def get_test():
    age = int(request.get_json().get('age', 0))
    questions = get_questions_by_age(age)
    return jsonify(questions)

@app.route('/submit-result', methods=['POST'])
def submit_result():
    data = request.get_json()
    user_info = data.get('userInfo')
    answers = data.get('answers')
    questions = get_questions_by_age(int(user_info.get('age')))
    
    analysis_result = analyze_answers(questions, answers)
    
    improvement_message = ""
    if sheet:
        previous_result_data = find_previous_result(user_info.get('phone'))
        if previous_result_data:
            improvement_message = calculate_improvement(previous_result_data, analysis_result)

    coaching_guide = generate_coaching_guide(analysis_result, questions, answers)

    if sheet:
        try:
            row_to_insert = [
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                user_info.get('name'),
                user_info.get('age'),
                user_info.get('phone'),
                json.dumps(analysis_result, ensure_ascii=False),
                coaching_guide
            ]
            sheet.append_row(row_to_insert, value_input_option='USER_ENTERED')
        except Exception as e:
            print(f"Google Sheets 저장 오류: {e}")
    
    return jsonify({
        'success': True, 
        'analysis': analysis_result,
        'improvement_message': improvement_message,
        'coaching_guide': coaching_guide
    })

# --- Helper Functions ---
def find_previous_result(phone_number):
    try:
        cell_list = sheet.findall(phone_number, in_column=4)
        if cell_list:
            latest_record_row = max(cell.row for cell in cell_list)
            previous_result_str = sheet.cell(latest_record_row, 5).value
            return json.loads(previous_result_str)
    except Exception as e:
        print(f"과거 기록 조회 중 오류 발생: {e}")
    return None

def calculate_improvement(previous, current):
    message = "🎉 **성장 리포트** 🎉<br>"
    has_improvement = False
    for skill, current_score in current.items():
        previous_score = previous.get(skill)
        if previous_score is not None and current_score > previous_score:
            improvement = round(((current_score - previous_score) / previous_score) * 100) if previous_score > 0 else 100
            message += f"지난 테스트 대비 **'{skill_to_korean(skill)}'** 능력이 **{improvement}%** 향상되었습니다. 정말 대단해요!<br>"
            has_improvement = True
    if not has_improvement: return ""
    return message

def analyze_answers(questions, answers):
    score = { 'comprehension': 0, 'logic': 0, 'inference': 0, 'critical_thinking': 0 }
    skill_counts = { 'comprehension': 0, 'logic': 0, 'inference': 0, 'critical_thinking': 0 }
    for i, question in enumerate(questions):
        skill = question.get('skill')
        if skill in skill_counts:
            skill_counts[skill] += 1
            if i < len(answers) and answers[i] == question.get('answer'):
                score[skill] += 1
    final_scores = {}
    for skill, count in skill_counts.items():
        final_scores[skill] = round((score[skill] / count) * 100) if count > 0 else 0
    return final_scores

def generate_coaching_guide(result, questions, answers):
    guide = "### 💡 AI 코칭 가이드 (오답 노트)\n"
    has_wrong_answer = False
    for i, question in enumerate(questions):
        if i >= len(answers) or answers[i] != question.get('answer'):
            has_wrong_answer = True
            user_answer = answers[i] if i < len(answers) else "미답변"
            guide += f"- **{i+1}번 문제({skill_to_korean(question['skill'])}) 분석:**\n"
            guide += f"  - '{user_answer}'를 선택하셨군요. 정답은 '{question['answer']}'입니다. 이 문제를 통해 **{get_feedback_by_skill(question['skill'])}** 능력을 기를 수 있습니다.\n"
    if not has_wrong_answer:
        guide += "- 모든 문제를 완벽하게 해결하셨습니다! 훌륭한 프로파일러입니다.\n"
    guide += "\n### 📋 종합 소견\n"
    if result['critical_thinking'] < 70:
        guide += "- **비판적 사고력 강화:** 글을 읽은 후 '작가의 주장에 동의하는가?', '나라면 어떻게 다르게 썼을까?'와 같은 질문을 통해 자신만의 생각을 정리하는 연습이 필요합니다.\n"
    if result['inference'] < 70:
        guide += "- **추론 능력 향상:** 소설을 읽을 때, 다음 장면을 미리 예측해보거나 등장인물의 숨겨진 의도를 파악하는 토론을 해보는 것이 좋습니다.\n"
    guide += "- **추천 활동:** 다양한 주제의 비문학 도서를 주 2회 이상 꾸준히 읽는 것을 권장합니다.\n"
    return guide

def get_feedback_by_skill(skill):
    return {
        'comprehension': "글에 명시적으로 드러난 정보를 정확히 찾아내는",
        'logic': "문장과 문장 사이의 논리적 관계를 파악하는",
        'inference': "숨겨진 의미나 의도를 파악하는",
        'critical_thinking': "주장의 타당성을 검토하고 대안을 생각해보는"
    }.get(skill, "글을 종합적으로 이해하는")

def skill_to_korean(skill):
    return {
        'comprehension': '정보 이해력', 'logic': '논리 분석력',
        'inference': '단서 추론력', 'critical_thinking': '비판적 사고력',
    }.get(skill, skill)

def get_questions_by_age(age):
    if age <= 13:
        return [
            {'id': 1, 'skill': 'comprehension', 'passage': '펭귄은 추운 남극에 사는 새지만 날지 못합니다. 대신 물속에서 물고기처럼 빠르게 헤엄쳐 사냥을 합니다.', 'question': '이 글의 내용과 일치하는 것은?', 'options': ['펭귄은 날 수 있다', '펭귄은 더운 곳에 산다', '펭귄은 헤엄을 잘 친다', '펭귄은 채식을 한다'], 'answer': '펭귄은 헤엄을 잘 친다'},
            {'id': 2, 'skill': 'inference', 'passage': '민수는 아침부터 하늘만 쳐다보며 한숨을 쉬었다. 오늘은 친구들과 함께하는 소풍날이었기 때문이다. 창밖에는 굵은 빗방울이 떨어지고 있었다.', 'question': '민수가 한숨을 쉰 이유는 무엇일까요?', 'options': ['잠을 못 자서', '소풍을 못 갈 것 같아서', '배가 고파서', '숙제를 안 해서'], 'answer': '소풍을 못 갈 것 같아서'}
        ]
    else:
        return [
            {'id': 3, 'skill': 'logic', 'passage': '모든 포유류는 척추동물이다. 고래는 포유류이다. 따라서 고래는 척추동물이다.', 'question': '위 글의 논리 구조로 가장 적절한 것은?', 'options': ['유추', '귀납', '연역', '변증법'], 'answer': '연역'},
            {'id': 4, 'skill': 'critical_thinking', 'passage': '한 연구에 따르면, 아침 식사를 거르는 학생들의 학업 성취도가 더 낮게 나타났다. 따라서 모든 학생은 아침을 꼭 먹어야 성적이 오른다.', 'question': '위 주장에 대해 제기할 수 있는 가장 합리적인 의문은?', 'options': ['아침 식사의 메뉴는 무엇인가?', '성적과 아침 식사 외에 다른 변수는 없는가?', '연구는 얼마나 오래 진행되었는가?', '왜 아침 식사가 중요한가?'], 'answer': '성적과 아침 식사 외에 다른 변수는 없는가?'}
        ]

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)), debug=False)
