import os
import json
import string
import random
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, render_template, jsonify, request

# --- 초기 설정 ---
app = Flask(__name__, template_folder='templates')

# --- 지능형 문제 은행 (Ultimate Question Bank) ---
# (이전과 동일한 21개 샘플 문항)
QUESTION_BANK = [
    {'id': 101, 'age_group': 'low', 'category': 'non-literature', 'skill': 'comprehension', 'genre': 'science', 'difficulty': 'easy', 'expected_time': 15, 'passage': '개미는 더듬이로 서로 대화하고 냄새를 맡습니다. 땅속에 집을 짓고 여왕개미를 중심으로 함께 살아갑니다.', 'question': '개미가 대화할 때 사용하는 몸의 부분은 어디인가요?', 'options': [{'text': '입', 'feedback': '개미는 입으로 먹이를 먹지만, 대화는 더듬이로 해요.'}, {'text': '다리', 'feedback': '다리로는 열심히 걸어다니죠!'}, {'text': '더듬이', 'feedback': None}, {'text': '눈', 'feedback': '눈으로는 앞을 보지만, 대화는 더듬이의 역할이에요.'}], 'answer': '더듬이'},
    {'id': 104, 'age_group': 'low', 'category': 'non-literature', 'skill': 'vocabulary', 'genre': 'essay', 'difficulty': 'easy', 'expected_time': 20, 'passage': "어머니는 시장에서 사과 세 '개'와 연필 한 '자루'를 사 오셨다.", 'question': "물건을 세는 단위가 바르게 짝지어지지 않은 것은 무엇인가요?", 'options': [{'text': '신발 한 켤레', 'feedback': '신발은 두 짝이 모여 한 켤레가 맞아요.'}, {'text': '나무 한 그루', 'feedback': '나무는 한 그루, 두 그루 하고 세는 것이 맞아요.'}, {'text': '집 한 자루', 'feedback': None}, {'text': '종이 한 장', 'feedback': '종이는 한 장, 두 장 하고 세는 것이 맞아요.'}], 'answer': '집 한 자루'},
    {'id': 201, 'age_group': 'mid', 'category': 'non-literature', 'skill': 'title', 'genre': 'history', 'difficulty': 'medium', 'expected_time': 30, 'passage': '훈민정음은 "백성을 가르치는 바른 소리"라는 뜻이다. 세종대왕은 글자를 몰라 억울한 일을 당하는 백성들을 위해, 배우기 쉽고 쓰기 편한 우리만의 글자를 만들었다. 집현전 학자들의 반대에도 불구하고, 그는 자신의 뜻을 굽히지 않았다. 훈민정음 창제는 지식과 정보가 특정 계층의 전유물이 아닌, 모든 백성의 것이 되어야 한다는 위대한 민본주의 정신의 발현이었다.', 'question': '위 글의 제목으로 가장 적절한 것을 고르시오.', 'options': [{'text': '세종대왕의 위대한 업적', 'feedback': "맞는 말이지만, 글의 핵심 내용인 '훈민정음'을 구체적으로 담지 못해 너무 포괄적인 제목입니다."}, {'text': '집현전 학자들의 역할', 'feedback': '학자들의 반대가 언급되긴 했지만, 글의 중심 내용은 아닙니다.'}, {'text': '백성을 위한 글자, 훈민정음', 'feedback': None}, {'text': '한글의 과학적 원리와 우수성', 'feedback': '글에서 한글의 과학적 원리는 다루지 않았습니다. 내용을 벗어난 제목입니다.'}], 'answer': '백성을 위한 글자, 훈민정음'},
    {'id': 205, 'age_group': 'mid', 'category': 'non-literature', 'skill': 'vocabulary', 'genre': 'social', 'difficulty': 'medium', 'expected_time': 25, 'passage': "그 선수는 부상에도 불구하고 경기를 끝까지 뛰는 '투혼'을 보여주었다.", 'question': "문맥상 '투혼'의 의미로 가장 적절한 것은?", 'options': [{'text': '싸우려는 의지', 'feedback': '단순히 싸우려는 의지를 넘어, 어려운 상황을 극복하는 정신력을 의미합니다.'}, {'text': '포기하지 않는 강한 정신력', 'feedback': None}, {'text': '뛰어난 운동 신경', 'feedback': '투혼은 신체적 능력보다는 정신적 태도를 의미하는 단어입니다.'}, {'text': '동료를 아끼는 마음', 'feedback': '동료애와는 다른, 개인의 의지를 나타내는 말입니다.'}], 'answer': '포기하지 않는 강한 정신력'},
    {'id': 301, 'age_group': 'high', 'category': 'non-literature', 'skill': 'critical_thinking', 'genre': 'social', 'difficulty': 'hard', 'expected_time': 40, 'passage': 'SNS는 개인의 일상을 공유하고 타인과 소통하는 긍정적 기능을 하지만, 한편으로는 끊임없이 타인의 삶과 자신의 삶을 비교하게 만들어 상대적 박탈감을 유발하기도 한다. 편집되고 이상화된 타인의 모습을 보며, 많은 이들이 자신의 현실에 대해 불만족을 느끼거나 우울감에 빠지기도 한다. SNS의 화려함 이면에 있는 그림자를 직시할 필요가 있다.', 'question': '위 글의 관점에서 SNS 사용자가 가져야 할 가장 바람직한 태도는?', 'options': [{'text': '다양한 사람들과 적극적으로 교류한다.', 'feedback': '글쓴이는 SNS의 긍정적 기능도 인정하지만, 문제의 핵심 해결책으로 제시하지는 않았습니다.'}, {'text': '자신의 일상을 꾸밈없이 솔직하게 공유한다.', 'feedback': "좋은 태도일 수 있지만, 글의 핵심 주장인 '비판적 수용'과는 거리가 있습니다."}, {'text': 'SNS에 보이는 모습이 현실의 전부가 아님을 인지하고 비판적으로 수용한다.', 'feedback': None}, {'text': "타인의 게시물에 '좋아요'를 누르며 긍정적으로 반응한다.", 'feedback': '이는 SNS의 순기능일 뿐, 글쓴이가 경고하는 문제점을 해결하는 태도는 아닙니다.'}], 'answer': 'SNS에 보이는 모습이 현실의 전부가 아님을 인지하고 비판적으로 수용한다.'},
    {'id': 302, 'age_group': 'high', 'category': 'literature', 'skill': 'creativity', 'type': 'text_input', 'genre': 'sf', 'difficulty': 'hard', 'expected_time': 60, 'passage': '당신은 100년 뒤 미래로 시간 여행을 떠날 수 있는 티켓 한 장을 얻었습니다.', 'question': '가장 먼저 무엇을 확인하고 싶으며, 그 이유는 무엇인지 짧게 서술하시오. (최소 100자 이상)', 'options': [], 'answer': ''},
]

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
    questions = assemble_test_for_age(age, 15)
    return jsonify(questions)

@app.route('/submit-result', methods=['POST'])
def submit_result():
    data = request.get_json()
    user_info = data.get('userInfo')
    answers = data.get('answers')
    solving_times = data.get('solvingTimes')
    questions = data.get('questions')
    
    analysis_result = analyze_answers(questions, answers)
    genre_bias_result = analyze_genre_bias(questions, answers)
    time_analysis_result = analyze_solving_time(questions, solving_times, answers)
    
    analysis_result['genre_bias'] = genre_bias_result
    analysis_result['time_analysis'] = time_analysis_result
    
    coaching_guide = generate_coaching_guide(analysis_result, questions, answers)
    theoretical_basis = "본 테스트는 블룸의 교육 목표 분류학, 인지 부하 이론, 스키마 이론, 메타인지 전략 등을 종합적으로 고려하여 설계된 다차원 독서력 진단 프로그램입니다."

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
        'coaching_guide': coaching_guide,
        'theoretical_basis': theoretical_basis
    })

# --- Helper Functions ---
def assemble_test_for_age(age, num_questions):
    """나이에 맞춰 다양한 장르와 카테고리의 문제를 동적으로 조립합니다. (안정화 버전)"""
    if age <= 12: age_group = 'low'
    elif age <= 16: age_group = 'mid'
    else: age_group = 'high'
    
    candidate_questions = [q for q in QUESTION_BANK if q['age_group'] == age_group]
    
    # [안정화 로직] 요청된 문항 수보다 전체 문항 수가 적으면, 있는 문항만 모두 반환합니다.
    if len(candidate_questions) < num_questions:
        random.shuffle(candidate_questions)
        return candidate_questions

    # 문항 수가 충분하면, 문학/비문학을 균형 있게 섞어서 15개를 추출합니다.
    questions_by_category = {
        'literature': [q for q in candidate_questions if q['category'] == 'literature'],
        'non-literature': [q for q in candidate_questions if q['category'] == 'non-literature']
    }

    final_test = []
    num_lit = num_questions // 2
    num_non_lit = num_questions - num_lit

    if questions_by_category['literature']:
        final_test.extend(random.sample(questions_by_category['literature'], min(num_lit, len(questions_by_category['literature']))))
    if questions_by_category['non-literature']:
        final_test.extend(random.sample(questions_by_category['non-literature'], min(num_non_lit, len(questions_by_category['non-literature']))))

    remaining = num_questions - len(final_test)
    if remaining > 0:
        remaining_pool = [q for q in candidate_questions if q not in final_test]
        if remaining_pool:
             final_test.extend(random.sample(remaining_pool, min(remaining, len(remaining_pool))))

    random.shuffle(final_test)
    return final_test


def analyze_answers(questions, answers):
    score = { 'comprehension': 0, 'logic': 0, 'inference': 0, 'critical_thinking': 0, 'vocabulary': 0, 'theme': 0, 'title': 0, 'creativity': 0, 'sentence_ordering': 0, 'paragraph_ordering': 0 }
    skill_counts = {k: 0 for k in score}
    for i, q in enumerate(questions):
        skill = q.get('skill')
        if skill in skill_counts:
            skill_counts[skill] += 1
            if q.get('type') == 'text_input':
                if i < len(answers) and len(answers[i]) > 10: score[skill] += 1
            elif i < len(answers) and answers[i] == q.get('answer'):
                score[skill] += 1
    final_scores = {}
    for skill, count in skill_counts.items():
        if count > 0:
            final_scores[skill] = round((score[skill] / count) * 100)
    return final_scores

def analyze_genre_bias(questions, answers):
    genre_scores, genre_counts = {}, {}
    for i, q in enumerate(questions):
        genre = q.get('genre', 'etc')
        genre_counts[genre] = genre_counts.get(genre, 0) + 1
        if i < len(answers) and answers[i] == q.get('answer'):
            genre_scores[genre] = genre_scores.get(genre, 0) + 1
    bias_result = {}
    for genre, count in genre_counts.items():
        bias_result[genre] = round((genre_scores.get(genre, 0) / count) * 100)
    return bias_result

def analyze_solving_time(questions, solving_times, answers):
    total_time = sum(solving_times)
    total_expected_time = sum(q.get('expected_time', 30) for q in questions)
    
    fast_correct = 0
    slow_wrong = 0
    
    for i, q in enumerate(questions):
        if i >= len(solving_times): continue
        is_correct = (q.get('type') == 'text_input' and len(answers[i]) > 10) or answers[i] == q.get('answer')
        time_diff = solving_times[i] - q.get('expected_time', 30)
        
        if is_correct and time_diff < 0:
            fast_correct += 1
        elif not is_correct and time_diff > 0:
            slow_wrong += 1

    agility_score = (fast_correct - slow_wrong) / len(questions)
    
    if agility_score > 0.3:
        agility_comment = "어려운 문제도 빠르고 정확하게 푸는 '인지 민첩성'이 뛰어납니다."
    elif agility_score < -0.3:
        agility_comment = "시간을 들여 신중하게 풀었음에도 실수가 잦은 경향이 있어, 기본 개념을 재점검할 필요가 있습니다."
    else:
        agility_comment = "문제 난이도에 따라 안정적인 문제 해결 속도를 보입니다."

    return {
        'total_time': total_time,
        'time_vs_expected': round((total_time / total_expected_time) * 100) if total_expected_time > 0 else 100,
        'agility_comment': agility_comment
    }

def generate_coaching_guide(result, questions, answers):
    """'매력적인 오답' 피드백 및 '종합 소견' 강화"""
    # 오답 노트 생성
    wrong_answers_feedback = []
    for i, q in enumerate(questions):
        if i < len(answers) and answers[i] != q.get('answer'):
            user_answer_text = answers[i]
            # 주관식 문제 오답 처리
            if q.get('type') == 'text_input':
                wrong_answers_feedback.append(f"- **{i+1}번 문제({skill_to_korean(q['skill'])}) 분석:** 서술형 문제는 정해진 답은 없지만, 자신의 생각을 논리적으로 표현하는 연습이 더 필요해 보입니다.")
                continue
            
            # 객관식 문제 오답 처리
            for opt in q.get('options', []):
                if opt['text'] == user_answer_text:
                    feedback = opt.get('feedback', '정확한 개념을 다시 확인해볼 필요가 있습니다.')
                    wrong_answers_feedback.append(f"- **{i+1}번 문제({skill_to_korean(q['skill'])}) 분석:** '{user_answer_text}'를 선택하셨군요. {feedback}")
                    break
    
    # 종합 소견 생성
    strengths = [skill_to_korean(s) for s, score in result.items() if isinstance(score, int) and score >= 80]
    weaknesses = [skill_to_korean(s) for s, score in result.items() if isinstance(score, int) and score < 60]
    
    total_review = "### 📋 종합 소견\n\n"
    if strengths:
        total_review += f"**강점 분석:**\n{', '.join(strengths)} 영역에서 뛰어난 이해도를 보여주셨습니다. 특히 논리적이고 사실적인 정보를 바탕으로 한 문제 해결 능력이 돋보입니다.\n\n"
    if weaknesses:
        total_review += f"**보완점 분석:**\n반면, {', '.join(weaknesses)} 영역에서는 추가적인 학습이 필요해 보입니다. 문학 작품의 함축적 의미를 파악하거나, 여러 정보의 논리적 순서를 재구성하는 훈련이 도움이 될 것입니다.\n\n"
    total_review += f"**성장 전략 제안:**\n강점은 유지하되, 약점을 보완하기 위해 다양한 장르의 글을 꾸준히 접하는 것을 추천합니다. 특히 단편 소설이나 비평문을 읽고 자신의 생각을 정리하는 연습이 효과적일 것입니다."

    guide = "### 💡 오답 노트\n"
    if wrong_answers_feedback:
        guide += "\n".join(wrong_answers_feedback)
    else:
        guide += "- 모든 문제를 완벽하게 해결하셨습니다! 훌륭한 프로파일러입니다.\n"
    
    guide += "\n" + total_review
    return guide

def get_feedback_by_skill(skill):
    return {
        'comprehension': "글에 명시적으로 드러난 정보를 정확히 찾아내는", 'logic': "문장과 문장 사이의 논리적 관계를 파악하는",
        'inference': "숨겨진 의미나 의도를 파악하는", 'critical_thinking': "주장의 타당성을 검토하고 대안을 생각해보는",
        'vocabulary': "문맥에 맞는 어휘의 의미를 파악하는", 'theme': "글의 중심 생각이나 주제를 파악하는",
        'title': "글 전체 내용을 함축하는 제목을 만드는", 'creativity': "자신의 생각을 논리적으로 표현하는",
        'sentence_ordering': "문장 간의 논리적 연결 고리를 파악하는", 'paragraph_ordering': "문단 전체의 구조를 파악하는"
    }.get(skill, "글을 종합적으로 이해하는")

def skill_to_korean(skill):
    return {
        'comprehension': '정보 이해력', 'logic': '논리 분석력', 'inference': '단서 추론력', 'critical_thinking': '비판적 사고력',
        'vocabulary': '어휘력', 'theme': '주제 파악력', 'title': '제목 생성력', 'creativity': '창의적 서술력',
        'sentence_ordering': '문장 배열력', 'paragraph_ordering': '문단 배열력'
    }.get(skill, skill)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)), debug=False)


