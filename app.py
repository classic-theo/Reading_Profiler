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

# --- 지능형 문제 은행 (Intelligent Question Bank) v2 ---
# 문학/비문학(category) 필드 추가 및 어휘력 문항 강화
QUESTION_BANK = [
    # === 초등 (age_group: 'low') ===
    {'id': 101, 'age_group': 'low', 'category': 'non-literature', 'skill': 'comprehension', 'genre': 'science', 'passage': '개미는 더듬이로 서로 대화하고 냄새를 맡습니다. 땅속에 집을 짓고 여왕개미를 중심으로 함께 살아갑니다.', 'question': '개미가 대화할 때 사용하는 몸의 부분은 어디인가요?', 'options': ['입', '다리', '더듬이', '눈'], 'answer': '더듬이'},
    {'id': 102, 'age_group': 'low', 'category': 'non-literature', 'skill': 'sentence_ordering', 'genre': 'essay', 'question': '다음 문장들을 순서에 맞게 배열한 것은 무엇인가요?', 'sentences': ['(가) 그래서 기분이 좋았다.', '(나) 나는 오늘 아침 일찍 일어났다.', '(다) 엄마가 칭찬을 해주셨다.', '(라) 내 방을 깨끗하게 청소했다.'], 'options': ['나-라-다-가', '가-나-다-라', '라-다-가-나', '나-다-라-가'], 'answer': '나-라-다-가'},
    {'id': 103, 'age_group': 'low', 'category': 'literature', 'skill': 'theme', 'genre': 'fantasy', 'passage': '옛날 옛적에, 구름 위에 떠 있는 성에 마음씨 착한 거인이 살고 있었습니다. 거인은 매일 밤 땅 위의 아이들에게 행복한 꿈을 선물했습니다.', 'question': '이 글의 내용으로 알 수 있는 것은 무엇인가요?', 'options': ['거인은 땅에 산다', '거인은 아이들을 싫어한다', '거인은 나쁜 꿈을 준다', '거인은 착한 마음씨를 가졌다'], 'answer': '거인은 착한 마음씨를 가졌다'},
    {'id': 104, 'age_group': 'low', 'category': 'non-literature', 'skill': 'vocabulary', 'genre': 'essay', 'passage': "어머니는 시장에서 사과 세 '개'와 연필 한 '자루'를 사 오셨다.", 'question': "물건을 세는 단위가 바르게 짝지어지지 않은 것은 무엇인가요?", 'options': ['신발 한 켤레', '나무 한 그루', '집 한 자루', '종이 한 장'], 'answer': '집 한 자루'},
    {'id': 105, 'age_group': 'low', 'category': 'non-literature', 'skill': 'inference', 'genre': 'history', 'passage': '지훈이는 어제부터 목이 아프고 열이 났다. 아침에 일어나니 콧물도 났다. 엄마는 지훈이의 이마를 만져보시더니 학교에 전화하셨다.', 'question': '엄마는 학교에 왜 전화했을까요?', 'options': ['지훈이가 숙제를 안 해서', '지훈이가 아파서 학교에 못 간다고 말하려고', '선생님과 상담하려고', '학교 급식을 물어보려고'], 'answer': '지훈이가 아파서 학교에 못 간다고 말하려고'},
    {'id': 106, 'age_group': 'low', 'category': 'literature', 'skill': 'creativity', 'type': 'text_input', 'genre': 'fantasy', 'passage': '만약 당신에게 투명인간이 될 수 있는 망토가 생긴다면,', 'question': '가장 먼저 무엇을 하고 싶은지 이유와 함께 짧게 써보세요.', 'options': [], 'answer': ''},
    {'id': 107, 'age_group': 'low', 'category': 'literature', 'skill': 'vocabulary', 'genre': 'poem', 'passage': "엄마야 누나야 강변 살자 / 뜰에는 반짝이는 금모래빛 / 뒷문 밖에는 갈잎의 노래", 'question': "이 시에서 '금모래빛'은 무엇을 표현한 말일까요?", 'options': ['금으로 만든 모래', '반짝이는 모래의 아름다운 빛깔', '슬픈 느낌', '강물의 색깔'], 'answer': '반짝이는 모래의 아름다운 빛깔'},

    # === 중등 (age_group: 'mid') ===
    {'id': 201, 'age_group': 'mid', 'category': 'non-literature', 'skill': 'title', 'genre': 'history', 'passage': '훈민정음은 "백성을 가르치는 바른 소리"라는 뜻이다. 세종대왕은 글자를 몰라 억울한 일을 당하는 백성들을 위해, 배우기 쉽고 쓰기 편한 우리만의 글자를 만들었다. 집현전 학자들의 반대에도 불구하고, 그는 자신의 뜻을 굽히지 않았다. 훈민정음 창제는 지식과 정보가 특정 계층의 전유물이 아닌, 모든 백성의 것이 되어야 한다는 위대한 민본주의 정신의 발현이었다.', 'question': '위 글의 제목으로 가장 적절한 것을 고르시오.', 'options': ['세종대왕의 위대한 업적', '집현전 학자들의 역할', '백성을 위한 글자, 훈민정음', '한글의 과학적 원리와 우수성', '훈민정음 반포의 역사적 과정'], 'answer': '백성을 위한 글자, 훈민정음'},
    {'id': 202, 'age_group': 'mid', 'category': 'non-literature', 'skill': 'paragraph_ordering', 'genre': 'science', 'question': '다음 문단들을 논리적 순서에 맞게 배열한 것은 무엇인가요?', 'paragraphs': ['(가) 이 과정에서 식물은 우리에게 꼭 필요한 산소를 내뿜는다. 즉, 숲이 울창해질수록 지구의 공기는 더욱 깨끗해지는 것이다.', '(나) 광합성이란, 식물이 태양의 빛 에너지를 화학 에너지로 바꾸어 스스로 양분을 만드는 놀라운 과정이다.', '(다) 식물은 뿌리에서 흡수한 물과 잎에서 흡수한 이산화탄소를 원료로 하여 엽록체에서 포도당과 같은 양분을 생성한다.'], 'options': ['가-나-다', '나-다-가', '다-가-나', '나-가-다'], 'answer': '나-다-가'},
    {'id': 203, 'age_group': 'mid', 'category': 'non-literature', 'skill': 'theme', 'genre': 'essay', 'passage': '우리가 무심코 버리는 플라스틱 쓰레기는 바다로 흘러가 미세 플라스틱으로 분해된다. 이를 물고기들이 먹고, 결국 그 물고기는 우리 식탁에 오를 수 있다. 결국 우리가 버린 쓰레기가 우리에게 다시 돌아오는 것이다. 환경 보호는 더 이상 남의 이야기가 아닌, 바로 우리 자신을 위한 실천이다.', 'question': '이 글의 요지로 가장 적절한 것은?', 'options': ['해양 생태계의 중요성', '올바른 분리수거 방법', '환경오염의 순환과 환경 보호의 필요성', '미세 플라스틱의 위험성'], 'answer': '환경오염의 순환과 환경 보호의 필요성'},
    {'id': 204, 'age_group': 'mid', 'category': 'literature', 'skill': 'inference', 'genre': 'novel', 'passage': '그의 아내는 "집에 가면 아무도 안 계실걸요." 하고 말했다. 이 말을 듣는 순간, 그는 아내의 표정 없는 얼굴에서 모든 것을 읽었다. 텅 빈 집, 싸늘한 공기, 그리고 다시는 돌아오지 않을 시간들. 그는 아무 말도 하지 못하고 돌아섰다.', 'question': '아내가 한 말에 담긴 숨은 의미로 가장 적절한 것은?', 'options': ['가족들이 모두 외출했다.', '집에 도둑이 들었다.', '남편을 깜짝 놀라게 해주려 한다.', '남편과 헤어지기로 결심했다.'], 'answer': '남편과 헤어지기로 결심했다.'},
    {'id': 205, 'age_group': 'mid', 'category': 'non-literature', 'skill': 'vocabulary', 'genre': 'social', 'passage': '그 선수는 부상에도 불구하고 경기를 끝까지 뛰는 '투혼'을 보여주었다.', 'question': "문맥상 '투혼'의 의미로 가장 적절한 것은?", 'options': ['싸우려는 의지', '포기하지 않는 강한 정신력', '뛰어난 운동 신경', '동료를 아끼는 마음'], 'answer': '포기하지 않는 강한 정신력'},
    {'id': 206, 'age_group': 'mid', 'category': 'literature', 'skill': 'comprehension', 'genre': 'poem', 'passage': '빼앗긴 들에도 봄은 오는가? / 나는 온몸에 햇살을 받고 / 푸른 하늘 푸른 들이 맞붙은 곳으로 / 가르마 같은 논길을 따라 꿈속을 가듯 걸어만 간다.', 'question': '이 시의 화자가 있는 공간적 배경은 어디인가요?', 'options': ['도시의 빌딩 숲', '눈 내리는 겨울 산', '푸른 들판의 논길', '캄캄한 방 안'], 'answer': '푸른 들판의 논길'},
    {'id': 207, 'age_group': 'mid', 'category': 'literature', 'skill': 'creativity', 'type': 'text_input', 'genre': 'essay', 'passage': '당신이 가장 존경하는 인물은 누구이며, 그 이유는 무엇인가요?', 'question': '가장 존경하는 인물과 그 이유를 간략히 서술하시오.', 'options': [], 'answer': ''},

    # === 고등 (age_group: 'high') ===
    {'id': 301, 'age_group': 'high', 'category': 'non-literature', 'skill': 'critical_thinking', 'genre': 'social', 'passage': 'SNS는 개인의 일상을 공유하고 타인과 소통하는 긍정적 기능을 하지만, 한편으로는 끊임없이 타인의 삶과 자신의 삶을 비교하게 만들어 상대적 박탈감을 유발하기도 한다. 편집되고 이상화된 타인의 모습을 보며, 많은 이들이 자신의 현실에 대해 불만족을 느끼거나 우울감에 빠지기도 한다. SNS의 화려함 이면에 있는 그림자를 직시할 필요가 있다.', 'question': '위 글의 관점에서 SNS 사용자가 가져야 할 가장 바람직한 태도는?', 'options': ['다양한 사람들과 적극적으로 교류한다.', '자신의 일상을 꾸밈없이 솔직하게 공유한다.', 'SNS에 보이는 모습이 현실의 전부가 아님을 인지하고 비판적으로 수용한다.', '타인의 게시물에 '좋아요'를 누르며 긍정적으로 반응한다.'], 'answer': 'SNS에 보이는 모습이 현실의 전부가 아님을 인지하고 비판적으로 수용한다.'},
    {'id': 302, 'age_group': 'high', 'category': 'literature', 'skill': 'creativity', 'type': 'text_input', 'genre': 'sf', 'passage': '당신은 100년 뒤 미래로 시간 여행을 떠날 수 있는 티켓 한 장을 얻었습니다.', 'question': '가장 먼저 무엇을 확인하고 싶으며, 그 이유는 무엇인지 짧게 서술하시오.', 'options': [], 'answer': ''},
    {'id': 303, 'age_group': 'high', 'category': 'non-literature', 'skill': 'theme', 'genre': 'social', 'passage': '기본소득제는 모든 국민에게 조건 없이 정기적으로 일정 금액의 소득을 지급하는 제도이다. 찬성 측은 최소한의 인간다운 삶을 보장하고 소비를 진작시켜 경제를 활성화할 수 있다고 주장한다. 반면 반대 측은 막대한 재원 문제와 근로 의욕 저하 문제를 제기하며 실현 가능성에 의문을 표한다.', 'question': '이 글의 핵심 쟁점으로 가장 적절한 것은?', 'options': ['기본소득제의 역사적 배경', '기본소득제 도입의 찬반 논거', '기본소득제와 다른 복지 제도의 비교', '기본소득제 지급액의 적정 수준'], 'answer': '기본소득제 도입의 찬반 논거'},
    {'id': 304, 'age_group': 'high', 'category': 'literature', 'skill': 'inference', 'genre': 'novel', 'passage': '"사랑 손님과 어머니"에서 옥희는 삶은 달걀을 무척 좋아한다. 어느 날 아저씨가 삶은 달걀을 주자, 옥희는 "아저씨, 우리 아빠 하실래요?"라고 묻는다. 당시 사회 분위기상 어머니와 아저씨의 사랑은 이루어지기 어려웠다. 옥희의 이 질문은 순수한 어린아이의 바람이면서 동시에, 두 어른의 관계를 암시하고 앞으로의 비극을 예고하는 복선으로 작용한다.', 'question': '옥희의 질문이 '복선'으로 작용한다는 것의 의미는 무엇인가?', 'options': ['두 어른이 결국 결혼에 성공할 것임을 암시한다.', '옥희가 달걀을 더 먹고 싶어함을 의미한다.', '어머니가 아저씨를 좋아하지 않음을 보여준다.', '두 사람의 사랑이 순탄치 않을 것임을 암시한다.'], 'answer': '두 사람의 사랑이 순탄치 않을 것임을 암시한다.'},
    {'id': 305, 'age_group': 'high', 'category': 'non-literature', 'skill': 'vocabulary', 'genre': 'science', 'passage': '두 현상 사이의 인과 관계를 증명하려면, 두 현상이 함께 발생한다는 '상관관계'만으로는 부족하다. 다른 모든 변수를 통제한 상태에서 오직 한 가지 변수만이 결과에 영향을 미쳤음을 입증해야 한다.', 'question': "'상관관계'와 '인과관계'의 차이를 가장 잘 설명한 것은?", 'options': ["상관관계는 원인과 결과, 인과관계는 두 현상의 관련성을 의미한다.", "상관관계는 두 현상이 관련이 있음을, 인과관계는 하나가 다른 하나의 원인임을 의미한다.", "두 단어는 의미상 아무런 차이가 없다.", "인과관계는 과학에서만, 상관관계는 사회학에서만 사용된다."], 'answer': "상관관계는 두 현상이 관련이 있음을, 인과관계는 하나가 다른 하나의 원인임을 의미한다."},
    {'id': 306, 'age_group': 'high', 'category': 'literature', 'skill': 'vocabulary', 'genre': 'poem', 'passage': '내 마음은 호수요 / 그대 노 저어 오오 / 나는 그대의 흰 그림자를 안고, 옥같이 / 그대의 뱃전에 부서지리다.', 'question': "이 시에서 화자의 사랑을 표현하기 위해 사용된 핵심적인 비유법(은유법)은 무엇인가?", 'options': ['내 마음 = 호수', '그대 = 뱃전', '그림자 = 옥', '마음 = 노'], 'answer': '내 마음 = 호수'},
    {'id': 307, 'age_group': 'high', 'category': 'non-literature', 'skill': 'sentence_ordering', 'genre': 'essay', 'question': '다음 문장들을 논리적 순서에 맞게 배열하시오.', 'sentences': ['(가) 즉, 습관은 의식적인 노력을 거의 들이지 않고도 특정 행동을 자동으로 수행하게 만드는 강력한 힘이다.', '(나) 처음에는 의식적으로 노력해야 했던 양치질이, 나중에는 아무 생각 없이도 자연스럽게 이루어지는 것을 생각해보면 쉽다.', '(다) 새로운 행동을 반복하면 우리 뇌의 특정 신경 회로가 강화된다.', '(라) 이것이 바로 습관이 형성되는 원리이다.'], 'options': ['다-나-라-가', '나-다-가-라', '다-라-나-가', '가-다-나-라'], 'answer': '다-나-라-가'}
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
    time_analysis_result = analyze_solving_time(questions, solving_times)
    
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

def analyze_solving_time(questions, solving_times):
    time_result = {'total_time': sum(solving_times), 'details': []}
    for i, q in enumerate(questions):
        if i < len(solving_times):
            time_result['details'].append({'question_id': q['id'], 'skill': q['skill'], 'time': solving_times[i]})
    return time_result

def generate_coaching_guide(result, questions, answers):
    guide = "### 💡 AI 코칭 가이드 (오답 노트)\n"
    has_wrong_answer = False
    for i, q in enumerate(questions):
        if q.get('type') == 'text_input': continue
        if i >= len(answers) or answers[i] != q.get('answer'):
            has_wrong_answer = True
            user_answer = answers[i] if i < len(answers) else "미답변"
            guide += f"- **{i+1}번 문제({skill_to_korean(q['skill'])}) 분석:**\n"
            guide += f"  - 정답은 '{q['answer']}'입니다. 이 문제를 통해 **{get_feedback_by_skill(q['skill'])}** 능력을 기를 수 있습니다.\n"
    if not has_wrong_answer:
        guide += "- 모든 문제를 완벽하게 해결하셨습니다! 훌륭한 프로파일러입니다.\n"
    guide += "\n### 📋 종합 소견\n"
    if result.get('critical_thinking', 100) < 70:
        guide += "- **비판적 사고력 강화:** 글을 읽은 후 '작가의 주장에 동의하는가?'와 같은 질문을 통해 자신만의 생각을 정리하는 연습이 필요합니다.\n"
    if result.get('inference', 100) < 70:
        guide += "- **추론 능력 향상:** 소설을 읽을 때, 다음 장면을 미리 예측해보거나 등장인물의 숨겨진 의도를 파악하는 토론을 해보는 것이 좋습니다.\n"
    guide += "- **추천 활동:** 다양한 주제의 비문학 도서를 주 2회 이상 꾸준히 읽는 것을 권장합니다.\n"
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
