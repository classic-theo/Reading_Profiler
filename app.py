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

# --- 지능형 문제 은행 (Intelligent Question Bank) ---
# 실제 서비스에서는 이 부분을 별도의 DB로 분리하는 것이 이상적입니다.
QUESTION_BANK = [
    # --- 초등 저학년 (age_group: 'low') ---
    {'id': 101, 'age_group': 'low', 'skill': 'comprehension', 'length': 'short', 'passage': '호랑이는 고양이과 동물 중에서 가장 큽니다. 줄무늬가 특징이며, 주로 숲에 삽니다.', 'question': '이 글에서 호랑이의 특징으로 언급된 것은 무엇인가요?', 'options': ['점박이 무늬', '가장 빠르다', '줄무늬', '물에 산다'], 'answer': '줄무늬'},
    {'id': 102, 'age_group': 'low', 'skill': 'vocabulary', 'length': 'short', 'passage': '사과, 배, 포도는 모두 달콤한 과일입니다.', 'question': "'과일'과 비슷한 의미를 가진 단어는 무엇일까요?", 'options': ['채소', '과실', '곡식', '장난감'], 'answer': '과실'},
    {'id': 103, 'age_group': 'low', 'skill': 'inference', 'length': 'medium', 'passage': '하늘에 먹구름이 잔뜩 끼었다. 바람이 세게 불기 시작했고, 사람들은 서둘러 집으로 향했다.', 'question': '곧 어떤 일이 일어날 가능성이 가장 높을까요?', 'options': ['해가 뜬다', '눈이 온다', '비가 온다', '조용해진다'], 'answer': '비가 온다'},

    # --- 초등 고학년 (age_group: 'mid') ---
    {'id': 201, 'age_group': 'mid', 'skill': 'comprehension', 'length': 'medium', 'passage': '조선 시대의 왕, 세종대왕은 백성을 위해 한글을 창제했습니다. 이전에는 어려운 한자를 사용해야 했기 때문에, 글을 읽고 쓰지 못하는 백성이 많았습니다. 한글 덕분에 더 많은 사람이 지식과 정보를 나눌 수 있게 되었습니다.', 'question': '세종대왕이 한글을 만든 가장 중요한 이유는 무엇인가요?', 'options': ['중국과의 교류를 위해', '글을 모르는 백성을 위해', '왕의 권위를 높이기 위해', '아름다운 글자를 갖고 싶어서'], 'answer': '글을 모르는 백성을 위해'},
    {'id': 202, 'age_group': 'mid', 'skill': 'logic', 'length': 'medium', 'passage': '광합성은 식물이 빛 에너지를 이용해 스스로 양분을 만드는 과정입니다. 이 과정에는 물과 이산화탄소가 필요하며, 결과물로 산소가 배출됩니다.', 'question': '광합성의 필수 요소가 아닌 것은 무엇인가요?', 'options': ['빛', '물', '산소', '이산화탄소'], 'answer': '산소'},
    {'id': 203, 'age_group': 'mid', 'skill': 'theme', 'length': 'long', 'passage': '어린 왕자는 자기 별에 혼자 남겨진 장미를 그리워했다. 사막여우는 어린 왕자에게 "네 장미꽃을 그토록 소중하게 만든 건, 그 꽃을 위해 네가 길들인 시간이야"라고 말했다. 관계란 서로에게 시간을 쏟고 마음을 쓰며 유일한 존재가 되어가는 과정이다.', 'question': '이 글의 전체 주제로 가장 알맞은 것은?', 'options': ['우정의 중요성', '소유의 기쁨', '관계의 본질', '여행의 즐거움'], 'answer': '관계의 본질'},

    # --- 중/고등학생 (age_group: 'high') ---
    {'id': 301, 'age_group': 'high', 'skill': 'critical_thinking', 'length': 'long', 'passage': '인공지능(AI)의 발전은 인간의 삶을 편리하게 만들지만, 동시에 AI가 인간의 일자리를 대체할 것이라는 우려도 커지고 있다. 일각에서는 AI로 인해 사라지는 일자리보다 새로운 형태의 일자리가 더 많이 생겨날 것이라고 주장한다.', 'question': 'AI와 일자리에 대한 필자의 태도는 무엇인가요?', 'options': ['무조건적 긍정', '절대적 비판', '중립적 관점 제시', '기술 발전 반대'], 'answer': '중립적 관점 제시'},
    {'id': 302, 'age_group': 'high', 'skill': 'title', 'length': 'long', 'passage': '민주주의 사회에서 시민의 정치 참여는 매우 중요하다. 투표는 가장 기본적인 참여 방법이며, 정책 제안이나 공청회 참석, 시민 단체 활동 등 다양한 방식으로 사회 발전에 기여할 수 있다. 시민들의 지속적인 관심과 참여가 없다면, 민주주의는 형식적인 제도로 전락할 위험이 있다.', 'question': '위 글에 가장 어울리는 제목을 만드시오.', 'options': ['투표의 역사', '시민 단체의 종류', '민주주의를 지키는 힘, 시민 참여', '정치인의 역할'], 'answer': '민주주의를 지키는 힘, 시민 참여'},
    {'id': 303, 'age_group': 'high', 'skill': 'creativity', 'length': 'short', 'passage': '당신은 100년 뒤 미래로 시간 여행을 떠날 수 있는 티켓 한 장을 얻었습니다.', 'question': '가장 먼저 무엇을 확인하고 싶으며, 그 이유는 무엇인지 짧게 서술하시오.', 'options': [], 'answer': ''}, # 주관식 문제
]

# --- 구글 시트 연동 ---
# (이전 코드와 동일)
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
# (이전 코드와 동일)
@app.route('/admin')
def admin_dashboard():
    return render_template('admin.html')

@app.route('/admin/generate-code', methods=['POST'])
def admin_generate_code():
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    active_codes[code] = {'status': 'active', 'created_at': datetime.now().isoformat()}
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
    questions = assemble_test_for_age(age) # 지능형 테스트 조립 함수 호출
    return jsonify(questions)

@app.route('/submit-result', methods=['POST'])
def submit_result():
    data = request.get_json()
    user_info = data.get('userInfo')
    answers = data.get('answers')
    questions = get_questions_by_age(int(user_info.get('age'))) # 사용자가 푼 문제 세트
    
    analysis_result = analyze_answers(questions, answers)
    
    improvement_message = ""
    if sheet:
        previous_result_data = find_previous_result(user_info.get('phone'))
        if previous_result_data:
            improvement_message = calculate_improvement(previous_result_data, analysis_result)

    coaching_guide = generate_coaching_guide(analysis_result, questions, answers)

    # 테스트의 과학적 근거 문구 추가
    theoretical_basis = "본 테스트는 블룸의 교육 목표 분류학, 인지 부하 이론, 메타인지 전략 등을 종합적으로 고려하여 설계된 다차원 독서력 진단 프로그램입니다."

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
        'coaching_guide': coaching_guide,
        'theoretical_basis': theoretical_basis # 결과에 근거 문구 포함
    })

# --- Helper Functions ---
def assemble_test_for_age(age):
    """나이에 맞춰 문제 은행에서 테스트를 동적으로 조립합니다."""
    if age <= 10: age_group = 'low'
    elif age <= 16: age_group = 'mid'
    else: age_group = 'high'
    
    # 해당 연령 그룹의 모든 문제를 가져옵니다.
    candidate_questions = [q for q in QUESTION_BANK if q['age_group'] == age_group]
    
    # 실제 서비스에서는 스킬별로 N개씩 랜덤 추출하는 로직이 더 정교합니다.
    # 여기서는 프로토타입으로 해당 그룹의 모든 문제를 반환합니다.
    return candidate_questions

# get_questions_by_age는 assemble_test_for_age와 동일한 역할을 하므로 유지 또는 통합 가능
def get_questions_by_age(age):
    return assemble_test_for_age(age)

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
    # (이전 코드와 동일)
    score = { 'comprehension': 0, 'logic': 0, 'inference': 0, 'critical_thinking': 0, 'vocabulary': 0, 'theme': 0, 'title': 0, 'creativity': 0 }
    skill_counts = {k: 0 for k in score}
    for i, question in enumerate(questions):
        skill = question.get('skill')
        if skill in skill_counts:
            skill_counts[skill] += 1
            if question.get('answer') == '': # 주관식 창의력 문제
                if i < len(answers) and len(answers[i]) > 10: # 10자 이상 작성 시 점수 부여
                    score[skill] += 1
            elif i < len(answers) and answers[i] == question.get('answer'):
                score[skill] += 1
    final_scores = {}
    for skill, count in skill_counts.items():
        if count > 0:
            final_scores[skill] = round((score[skill] / count) * 100)
    return {k: v for k, v in final_scores.items() if k in [q['skill'] for q in questions]} # 실제 출제된 스킬만 반환

def generate_coaching_guide(result, questions, answers):
    # (이전 코드와 동일)
    guide = "### 💡 AI 코칭 가이드 (오답 노트)\n"
    has_wrong_answer = False
    for i, question in enumerate(questions):
        # 주관식 문제는 오답노트에서 제외
        if question.get('answer') == '': continue

        if i >= len(answers) or answers[i] != question.get('answer'):
            has_wrong_answer = True
            user_answer = answers[i] if i < len(answers) else "미답변"
            guide += f"- **{i+1}번 문제({skill_to_korean(question['skill'])}) 분석:**\n"
            guide += f"  - '{user_answer}'를 선택하셨군요. 정답은 '{question['answer']}'입니다. 이 문제를 통해 **{get_feedback_by_skill(question['skill'])}** 능력을 기를 수 있습니다.\n"
    if not has_wrong_answer:
        guide += "- 모든 문제를 완벽하게 해결하셨습니다! 훌륭한 프로파일러입니다.\n"
    guide += "\n### 📋 종합 소견\n"
    if result.get('critical_thinking', 100) < 70:
        guide += "- **비판적 사고력 강화:** 글을 읽은 후 '작가의 주장에 동의하는가?', '나라면 어떻게 다르게 썼을까?'와 같은 질문을 통해 자신만의 생각을 정리하는 연습이 필요합니다.\n"
    if result.get('inference', 100) < 70:
        guide += "- **추론 능력 향상:** 소설을 읽을 때, 다음 장면을 미리 예측해보거나 등장인물의 숨겨진 의도를 파악하는 토론을 해보는 것이 좋습니다.\n"
    guide += "- **추천 활동:** 다양한 주제의 비문학 도서를 주 2회 이상 꾸준히 읽는 것을 권장합니다.\n"
    return guide

def get_feedback_by_skill(skill):
    return {
        'comprehension': "글에 명시적으로 드러난 정보를 정확히 찾아내는",
        'logic': "문장과 문장 사이의 논리적 관계를 파악하는",
        'inference': "숨겨진 의미나 의도를 파악하는",
        'critical_thinking': "주장의 타당성을 검토하고 대안을 생각해보는",
        'vocabulary': "문맥에 맞는 어휘의 의미를 파악하는",
        'theme': "글의 중심 생각이나 주제를 파악하는",
        'title': "글 전체 내용을 함축하는 제목을 만드는",
        'creativity': "자신의 생각을 논리적으로 표현하는"
    }.get(skill, "글을 종합적으로 이해하는")

def skill_to_korean(skill):
    return {
        'comprehension': '정보 이해력', 'logic': '논리 분석력',
        'inference': '단서 추론력', 'critical_thinking': '비판적 사고력',
        'vocabulary': '어휘력', 'theme': '주제 파악력', 'title': '제목 생성력', 'creativity': '창의적 서술력'
    }.get(skill, skill)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)), debug=False)
