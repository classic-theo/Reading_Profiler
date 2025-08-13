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
    # 'creds_dict'가 정의되어 있는지 확인 후 사용
    if 'creds_dict' in locals() and creds_dict:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open("독서력 진단 결과").sheet1
    print("Google Sheets와 성공적으로 연결되었습니다.")
except Exception as e:
    print(f"Google Sheets 연결 오류: {e}")
    sheet = None


app = Flask(__name__, template_folder='templates')
active_codes = {}

# --- 관리자 및 사용자 페이지 라우트 ---
@app.route('/admin')
def admin_dashboard():
    return render_template('admin.html')

@app.route('/admin/generate-code', methods=['POST'])
def admin_generate_code():
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    active_codes[code] = {'status': 'active', 'created_at': datetime.now().isoformat()}
    return jsonify({'access_code': code})

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
    if not db:
        return jsonify({"error": "Database connection failed"}), 500
    
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
    
    # [MODIFIED] 비고츠키 이론 명시적으로 추가
    theoretical_basis = "본 테스트는 블룸의 교육 목표 분류학, 인지 부하 이론, 스키마 이론, 그리고 비고츠키의 근접 발달 영역(ZPD) 이론 등을 종합적으로 고려하여 설계된 다차원 독서력 진단 프로그램입니다."

    if sheet:
        try:
            summary_text = ", ".join([f"{skill_to_korean(s)}: {score}점" for s, score in analysis_result.items() if isinstance(score, int)])
            summary_text += f", 인지 민첩성: {time_analysis_result.get('agility_type')}"
            
            correct_count = sum(1 for i, q in enumerate(questions) if i < len(answers) and answers[i] == q.get('answer'))
            achievement_text = f"정답: {correct_count}/{len(questions)}, 총 시간: {time_analysis_result.get('total_time')}초, 정답률: {round((correct_count/len(questions))*100) if questions else 0}%"

            header = ['테스트일', '이름', '나이', '핸드폰 번호', '결과분석(JSON)', '요약', '성취도', '코칭가이드']
            try:
                if sheet.row_values(1) != header:
                    sheet.insert_row(header, 1)
            except gspread.exceptions.APIError:
                 sheet.insert_row(header, 1)

            row_to_insert = [
                datetime.now().strftime("%Y-%m-%d %H:%M"), user_info.get('name'), user_info.get('age'),
                user_info.get('phone'), json.dumps(analysis_result, ensure_ascii=False),
                summary_text, achievement_text, coaching_guide
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

# --- (이하 모든 Helper 함수는 이전과 동일합니다) ---
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

    questions_by_category = {
        'literature': [q for q in candidate_questions if q.get('category') == 'literature'],
        'non-literature': [q for q in candidate_questions if q.get('category') == 'non-literature']
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
                if i < len(answers) and answers[i] and len(answers[i]) > 10: score[skill] += 1
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
    
    fast_correct, slow_correct, fast_wrong, slow_wrong = 0, 0, 0, 0
    
    for i, q in enumerate(questions):
        if i < len(answers) and i < len(solving_times):
            is_correct = answers[i] == q.get('answer')
            time_diff = solving_times[i] - q.get('expected_time', 30)
            
            if is_correct and time_diff <= 0: fast_correct += 1
            elif is_correct and time_diff > 0: slow_correct += 1
            elif not is_correct and time_diff <= 0: fast_wrong += 1
            elif not is_correct and time_diff > 0: slow_wrong += 1

    total_questions = len(questions) if questions else 1
    
    if (fast_correct / total_questions) > 0.4:
        agility_type = "신속/정확형"
        agility_comment = "빠르고 정확하게 문제를 해결하는 능력이 매우 뛰어납니다. 심화 학습을 통해 더 높은 수준에 도전해보세요."
    elif (fast_wrong / total_questions) > 0.3:
        agility_type = "성급/오답형"
        agility_comment = "빠르게 문제를 푸는 경향이 있으나, 그만큼 실수가 잦습니다. 지문을 더 꼼꼼히 읽고 함정을 피하는 연습이 필요합니다."
    elif (slow_correct / total_questions) > 0.4:
        agility_type = "신중/정확형"
        agility_comment = "시간은 다소 걸리지만, 침착하게 문제를 정확히 해결하는 능력을 갖추었습니다. 시간 단축 훈련을 통해 효율성을 높일 수 있습니다."
    elif (slow_wrong / total_questions) > 0.3:
        agility_type = "지체/오답형"
        agility_comment = "문제 해결에 어려움을 겪고 있습니다. 기본 개념을 다시 한번 점검하고, 쉬운 지문부터 차근차근 독해 연습을 하는 것을 추천합니다."
    else:
        agility_type = "안정형"
        agility_comment = "문제 난이도에 따라 안정적인 문제 해결 패턴을 보입니다."

    return {
        'total_time': total_time,
        'time_vs_expected': round((total_time / total_expected_time) * 100) if total_expected_time > 0 else 100,
        'agility_type': agility_type,
        'agility_comment': agility_comment
    }

def generate_coaching_guide(result, questions, answers):
    wrong_answers_feedback = []
    for i, q in enumerate(questions):
        if i < len(answers) and answers[i] != q.get('answer'):
            user_answer_text = answers[i]
            if q.get('type') == 'text_input':
                wrong_answers_feedback.append(f"- **{i+1}번 문제({skill_to_korean(q['skill'])}) 분석:** 서술형 문제는 정해진 답은 없지만, 자신의 생각을 논리적으로 표현하는 연습이 더 필요해 보입니다.")
                continue
            
            feedback_text = ""
            for opt in q.get('options', []):
                if opt['text'] == user_answer_text:
                    feedback = opt.get('feedback', '정확한 개념을 다시 확인해볼 필요가 있습니다.')
                    feedback_text = f"'{user_answer_text}'를 선택하셨군요. {feedback}"
                    break
            
            explanation = q.get('explanation', f"정답은 '{q.get('answer')}'입니다.")
            wrong_answers_feedback.append(f"- **{i+1}번 문제({skill_to_korean(q['skill'])}) 분석:** {feedback_text}\n  - **해설:** {explanation}")
    
    strengths = [skill_to_korean(s) for s, score in result.items() if isinstance(score, int) and score >= 80]
    weaknesses = [skill_to_korean(s) for s, score in result.items() if isinstance(score, int) and score < 60]
    
    total_review = "### 📋 종합 소견\n\n"
    if strengths:
        total_review += f"**강점 분석:**\n{', '.join(strengths)} 영역에서 뛰어난 이해도를 보여주셨습니다. 특히 논리적이고 사실적인 정보를 바탕으로 한 문제 해결 능력이 돋보입니다.\n\n"
    if weaknesses:
        total_review += f"**보완점 분석:**\n반면, {', '.join(weaknesses)} 영역에서는 추가적인 학습이 필요해 보입니다. 문학 작품의 함축적 의미를 파악하거나, 여러 정보의 논리적 순서를 재구성하는 훈련이 도움이 될 것입니다.\n\n"
    total_review += f"**성장 전략 제안 (ZPD 기반):**\n현재 능력치를 바탕으로 다음 단계로 성장하기 위해, 강점은 유지하되 약점을 보완하는 맞춤형 훈련을 제안합니다. 특히 단편 소설이나 비평문을 읽고 자신의 생각을 한 문단으로 요약하는 연습이 효과적일 것입니다."

    guide = "### 💡 오답 노트\n"
    if wrong_answers_feedback:
        guide += "\n".join(wrong_answers_feedback)
    else:
        guide += "- 모든 문제를 완벽하게 해결하셨습니다! 훌륭한 프로파일러입니다.\n"
    
    guide += "\n" + total_review
    return guide

def skill_to_korean(skill):
    return {
        'comprehension': '정보 이해력', 'logic': '논리 분석력', 'inference': '단서 추론력', 'critical_thinking': '비판적 사고력',
        'vocabulary': '어휘력', 'theme': '주제 파악력', 'title': '제목 생성력', 'creativity': '창의적 서술력',
        'sentence_ordering': '문장 배열력', 'paragraph_ordering': '문단 배열력'
    }.get(skill, skill)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)), debug=False)






