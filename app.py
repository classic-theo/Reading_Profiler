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
# difficulty, expected_time, 매력적인 오답(feedback) 필드 추가
QUESTION_BANK = [
    # === 초등 (age_group: 'low') ===
    {'id': 101, 'age_group': 'low', 'category': 'non-literature', 'skill': 'comprehension', 'genre': 'science', 'difficulty': 'easy', 'expected_time': 15, 'passage': '개미는 더듬이로 서로 대화하고 냄새를 맡습니다. 땅속에 집을 짓고 여왕개미를 중심으로 함께 살아갑니다.', 'question': '개미가 대화할 때 사용하는 몸의 부분은 어디인가요?', 
     'options': [
         {'text': '입', 'feedback': '개미는 입으로 먹이를 먹지만, 대화는 더듬이로 해요.'}, 
         {'text': '다리', 'feedback': '다리로는 열심히 걸어다니죠!'}, 
         {'text': '더듬이', 'feedback': None}, 
         {'text': '눈', 'feedback': '눈으로는 앞을 보지만, 대화는 더듬이의 역할이에요.'}
     ], 'answer': '더듬이'},
    {'id': 104, 'age_group': 'low', 'category': 'non-literature', 'skill': 'vocabulary', 'genre': 'essay', 'difficulty': 'easy', 'expected_time': 20, 'passage': "어머니는 시장에서 사과 세 '개'와 연필 한 '자루'를 사 오셨다.", 'question': "물건을 세는 단위가 바르게 짝지어지지 않은 것은 무엇인가요?", 
     'options': [
         {'text': '신발 한 켤레', 'feedback': '신발은 두 짝이 모여 한 켤레가 맞아요.'}, 
         {'text': '나무 한 그루', 'feedback': '나무는 한 그루, 두 그루 하고 세는 것이 맞아요.'}, 
         {'text': '집 한 자루', 'feedback': None}, 
         {'text': '종이 한 장', 'feedback': '종이는 한 장, 두 장 하고 세는 것이 맞아요.'}
     ], 'answer': '집 한 자루'},

    # === 중등 (age_group: 'mid') ===
    {'id': 201, 'age_group': 'mid', 'category': 'non-literature', 'skill': 'title', 'genre': 'history', 'difficulty': 'medium', 'expected_time': 30, 'passage': '훈민정음은 "백성을 가르치는 바른 소리"라는 뜻이다. 세종대왕은 글자를 몰라 억울한 일을 당하는 백성들을 위해, 배우기 쉽고 쓰기 편한 우리만의 글자를 만들었다. 집현전 학자들의 반대에도 불구하고, 그는 자신의 뜻을 굽히지 않았다. 훈민정음 창제는 지식과 정보가 특정 계층의 전유물이 아닌, 모든 백성의 것이 되어야 한다는 위대한 민본주의 정신의 발현이었다.', 'question': '위 글의 제목으로 가장 적절한 것을 고르시오.', 
     'options': [
         {'text': '세종대왕의 위대한 업적', 'feedback': '맞는 말이지만, 글의 핵심 내용인 '훈민정음'을 구체적으로 담지 못해 너무 포괄적인 제목입니다.'}, 
         {'text': '집현전 학자들의 역할', 'feedback': '학자들의 반대가 언급되긴 했지만, 글의 중심 내용은 아닙니다.'}, 
         {'text': '백성을 위한 글자, 훈민정음', 'feedback': None}, 
         {'text': '한글의 과학적 원리와 우수성', 'feedback': '글에서 한글의 과학적 원리는 다루지 않았습니다. 내용을 벗어난 제목입니다.'}
     ], 'answer': '백성을 위한 글자, 훈민정음'},
    {'id': 205, 'age_group': 'mid', 'category': 'non-literature', 'skill': 'vocabulary', 'genre': 'social', 'difficulty': 'medium', 'expected_time': 25, 'passage': "그 선수는 부상에도 불구하고 경기를 끝까지 뛰는 '투혼'을 보여주었다.", 'question': "문맥상 '투혼'의 의미로 가장 적절한 것은?", 
     'options': [
         {'text': '싸우려는 의지', 'feedback': '단순히 싸우려는 의지를 넘어, 어려운 상황을 극복하는 정신력을 의미합니다.'}, 
         {'text': '포기하지 않는 강한 정신력', 'feedback': None}, 
         {'text': '뛰어난 운동 신경', 'feedback': '투혼은 신체적 능력보다는 정신적 태도를 의미하는 단어입니다.'}, 
         {'text': '동료를 아끼는 마음', 'feedback': '동료애와는 다른, 개인의 의지를 나타내는 말입니다.'}
     ], 'answer': '포기하지 않는 강한 정신력'},

    # === 고등 (age_group: 'high') ===
    {'id': 301, 'age_group': 'high', 'category': 'non-literature', 'skill': 'critical_thinking', 'genre': 'social', 'difficulty': 'hard', 'expected_time': 40, 'passage': 'SNS는 개인의 일상을 공유하고 타인과 소통하는 긍정적 기능을 하지만, 한편으로는 끊임없이 타인의 삶과 자신의 삶을 비교하게 만들어 상대적 박탈감을 유발하기도 한다. 편집되고 이상화된 타인의 모습을 보며, 많은 이들이 자신의 현실에 대해 불만족을 느끼거나 우울감에 빠지기도 한다. SNS의 화려함 이면에 있는 그림자를 직시할 필요가 있다.', 'question': '위 글의 관점에서 SNS 사용자가 가져야 할 가장 바람직한 태도는?', 
     'options': [
         {'text': '다양한 사람들과 적극적으로 교류한다.', 'feedback': '글쓴이는 SNS의 긍정적 기능도 인정하지만, 문제의 핵심 해결책으로 제시하지는 않았습니다.'}, 
         {'text': '자신의 일상을 꾸밈없이 솔직하게 공유한다.', 'feedback': '좋은 태도일 수 있지만, 글의 핵심 주장인 '비판적 수용'과는 거리가 있습니다.'}, 
         {'text': 'SNS에 보이는 모습이 현실의 전부가 아님을 인지하고 비판적으로 수용한다.', 'feedback': None}, 
         {'text': "타인의 게시물에 '좋아요'를 누르며 긍정적으로 반응한다.", 'feedback': '이는 SNS의 순기능일 뿐, 글쓴이가 경고하는 문제점을 해결하는 태도는 아닙니다.'}
     ], 'answer': 'SNS에 보이는 모습이 현실의 전부가 아님을 인지하고 비판적으로 수용한다.'},
    {'id': 302, 'age_group': 'high', 'category': 'literature', 'skill': 'creativity', 'type': 'text_input', 'genre': 'sf', 'difficulty': 'hard', 'expected_time': 60, 'passage': '당신은 100년 뒤 미래로 시간 여행을 떠날 수 있는 티켓 한 장을 얻었습니다.', 'question': '가장 먼저 무엇을 확인하고 싶으며, 그 이유는 무엇인지 짧게 서술하시오. (최소 100자 이상)', 'options': [], 'answer': ''},
    # ... 여기에 더 많은 문항 추가
]

# (이하 구글 시트 연동 및 관리자 페이지 코드는 이전과 동일)
# ...

@app.route('/get-test', methods=['POST'])
def get_test():
    age = int(request.get_json().get('age', 0))
    questions = assemble_test_for_age(age, 15)
    return jsonify(questions)

@app.route('/submit-result', methods=['POST'])
def submit_result():
    data = request.get_json()
    user_info, answers, solving_times, questions = data.get('userInfo'), data.get('answers'), data.get('solvingTimes'), data.get('questions')
    
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
                datetime.now().strftime("%Y-%m-%d %H:%M"), user_info.get('name'), user_info.get('age'),
                user_info.get('phone'), json.dumps(analysis_result, ensure_ascii=False), coaching_guide
            ]
            sheet.append_row(row_to_insert, value_input_option='USER_ENTERED')
        except Exception as e:
            print(f"Google Sheets 저장 오류: {e}")
    
    return jsonify({
        'success': True, 'analysis': analysis_result,
        'coaching_guide': coaching_guide, 'theoretical_basis': theoretical_basis
    })

# --- Helper Functions ---
def assemble_test_for_age(age, num_questions):
    # (이전과 동일)
    # ...
    pass

def analyze_answers(questions, answers):
    # (이전과 동일)
    # ...
    pass

def analyze_genre_bias(questions, answers):
    # (이전과 동일)
    # ...
    pass

def analyze_solving_time(questions, solving_times, answers):
    """'인지 민첩성' 분석 로직 추가"""
    total_time = sum(solving_times)
    total_expected_time = sum(q.get('expected_time', 30) for q in questions)
    
    fast_correct = 0
    slow_wrong = 0
    
    for i, q in enumerate(questions):
        is_correct = answers[i] == q.get('answer')
        time_diff = solving_times[i] - q.get('expected_time', 30)
        
        if is_correct and time_diff < 0:
            fast_correct += 1
        elif not is_correct and time_diff > 0:
            slow_wrong += 1

    agility_score = (fast_correct - slow_wrong) / len(questions)
    
    if agility_score > 0.3:
        agility_comment = "어려운 문제도 빠르고 정확하게 푸는 '인지 민첩성'이 뛰어납니다."
    elif agility_score < -0.3:
        agilit_comment = "시간을 들여 신중하게 풀었음에도 실수가 잦은 경향이 있어, 기본 개념을 재점검할 필요가 있습니다."
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
            for opt in q.get('options', []):
                if opt['text'] == user_answer_text:
                    feedback = opt.get('feedback', '정확한 개념을 다시 확인해볼 필요가 있습니다.')
                    wrong_answers_feedback.append(f"- **{i+1}번 문제({skill_to_korean(q['skill'])}) 분석:** '{user_answer_text}'를 선택하셨군요. {feedback}")
                    break
    
    # 종합 소견 생성
    strengths = [skill_to_korean(s) for s, score in result.items() if isinstance(score, int) and score >= 80]
    weaknesses = [skill_to_korean(s) for s, score in result.items() if isinstance(score, int) and score < 60]
    
    total_review = "### 📋 종합 소견\n"
    if strengths:
        total_review += f"**강점 분석:** **{', '.join(strengths)}** 영역에서 뛰어난 이해도를 보여주셨습니다. 특히 논리적이고 사실적인 정보를 바탕으로 한 문제 해결 능력이 돋보입니다.\n"
    if weaknesses:
        total_review += f"**보완점 분석:** 반면, **{', '.join(weaknesses)}** 영역에서는 추가적인 학습이 필요해 보입니다. 문학 작품의 함축적 의미를 파악하거나, 여러 정보의 논리적 순서를 재구성하는 훈련이 도움이 될 것입니다.\n"
    total_review += f"**성장 전략 제안:** 강점은 유지하되, 약점을 보완하기 위해 다양한 장르의 글을 꾸준히 접하는 것을 추천합니다. 특히 단편 소설이나 비평문을 읽고 자신의 생각을 정리하는 연습이 효과적일 것입니다."

    guide = "### 💡 오답 노트\n"
    if wrong_answers_feedback:
        guide += "\n".join(wrong_answers_feedback)
    else:
        guide += "- 모든 문제를 완벽하게 해결하셨습니다! 훌륭한 프로파일러입니다.\n"
    
    guide += "\n" + total_review
    return guide

# (이하 skill_to_korean 등 나머지 함수는 이전과 동일)
# ...


