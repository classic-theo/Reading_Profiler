import os
import json
import random
import string
import time
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore
import gspread
import re

# Vertex AI SDK 및 Google 인증 라이브러리
import vertexai
from vertexai.generative_models import GenerativeModel
from google.oauth2 import service_account

# --- 1. Flask 앱 초기화 ---
app = Flask(__name__, template_folder='templates')

# --- 2. 외부 서비스 초기화 (통합 인증 방식) ---
db = None
sheet = None
creds = None
cred_dict = None

try:
    google_creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
    
    if google_creds_json:
        cred_dict = json.loads(google_creds_json)
        creds = service_account.Credentials.from_service_account_info(cred_dict)
        print("✅ 통합 인증 정보(GOOGLE_CREDENTIALS_JSON) 로드 성공")
    else:
        # 로컬 개발 환경용 fallback
        creds = service_account.Credentials.from_service_account_file('credentials.json')
        with open('credentials.json', 'r') as f:
            cred_dict = json.load(f)
        print("✅ 통합 인증 정보(로컬 credentials.json) 로드 성공")

    PROJECT_ID = cred_dict.get('project_id')
    LOCATION = "us-central1"
    vertexai.init(project=PROJECT_ID, location=LOCATION, credentials=creds)
    print(f"✅ Vertex AI SDK 초기화 성공 (Project: {PROJECT_ID})")

    firebase_cred = credentials.Certificate(cred_dict)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(firebase_cred)
    db = firestore.client()
    print("✅ Firebase 초기화 성공")

    gc = gspread.service_account_from_dict(cred_dict)
    sheet = gc.open("독서력 진단 결과").sheet1
    print("✅ Google Sheets ('독서력 진단 결과') 시트 열기 성공")

except Exception as e:
    print(f"🚨 외부 서비스 초기화 실패: {e}")

# --- 3. 핵심 데이터 및 설정 ---
CATEGORY_MAP = {
    "title": "제목 찾기", "theme": "주제 찾기", "argument": "주장 파악",
    "inference": "의미 추론", "pronoun": "지시어 찾기", "sentence_ordering": "문장 순서 맞추기",
    "paragraph_ordering": "단락 순서 맞추기", "essay": "창의적 서술력"
}

SCORE_CATEGORY_MAP = {
    "title": "정보 이해력", "theme": "정보 이해력", 
    "argument": "비판적 사고력",
    "inference": "단서 추론력", "pronoun": "단서 추론력",
    "sentence_ordering": "논리 분석력", "paragraph_ordering": "논리 분석력",
    "essay": "창의적 서술력"
}

# --- 4. AI 관련 함수 (Vertex AI SDK 방식) ---
def get_detailed_prompt(category, age_group, text_content=None):
    if age_group == "10-13":
        level_instruction = "대한민국 초등학교 4~6학년 국어 교과서 수준의 어휘와 문장 구조를 사용해줘. '야기하다', '고찰하다' 같은 어려운 한자어는 '일으킨다', '살펴본다'처럼 쉬운 말로 풀어 써줘."
        passage_length = "최소 2개 문단, 150자 이상"
    elif age_group == "14-16":
        level_instruction = "대한민국 중학교 1~3학년 국어 교과서 수준의 어휘와 문장 구조를 사용해줘. 전문 용어는 최소화하고, 필요 시 간단한 설명을 덧붙여줘."
        passage_length = "최소 3개 문단, 250자 이상"
    else: # 17-19
        level_instruction = "대한민국 고등학교 1~3학년 수준의 어휘와 복합적인 문장 구조를 사용해도 좋아. 사회, 과학, 인문 등 다양한 분야의 배경지식을 활용해줘."
        passage_length = "최소 3개 문단, 350자 이상"

    type_instruction = ""
    topics = {
        "default": ["흥미로운 동물 상식", "일상 속 과학 원리", "역사 속 인물 이야기"],
        "info": ["환경 보호의 중요성", "새로운 기술 트렌드", "건강한 생활 습관"],
        "logic": ["사회 현상 분석", "신문 사설", "주장이 담긴 칼럼"],
        "inference": ["과학 탐사(우주, 해양)", "최신 뉴스 기사의 이면", "미스터리한 사건의 재구성"]
    }
    
    if text_content:
        type_instruction = f"주어진 텍스트 '{text_content[:200]}...'를 바탕으로, 지문, 질문, 보기를 모두 창작해줘."
    elif category in ["title", "theme"]:
        topic = random.choice(topics["info"])
        type_instruction = f"'{topic}'에 대한 {passage_length}으로 구성된 완결된 설명문을 창작해줘."
    elif category == "argument":
        topic = random.choice(topics["logic"])
        type_instruction = f"'{topic}'에 대한 필자의 주장이 명확하게 드러나는 {passage_length}의 논설문을 창작해줘. 주장을 뒷받침하는 근거도 1~2개 포함해줘."
    elif category in ["inference", "pronoun"]:
        topic = random.choice(topics["inference"])
        type_instruction = f"'{topic}'에 대한 객관적인 사실을 전달하는 뉴스 기사 형식으로 {passage_length}의 글을 창작해줘."
    elif category == "sentence_ordering":
        topic = random.choice(topics["default"])
        type_instruction = f"'{topic}'에 대해 논리적 순서나 시간의 흐름이 중요한 1개의 완결된 단락을 창작한 후, 그 단락을 5개의 문장으로 분해해서 순서를 뒤섞어 문제로 만들어줘."
    elif category == "paragraph_ordering":
        topic = random.choice(topics["default"])
        type_instruction = f"'{topic}'에 대해 기승전결이나 서론-본론-결론 구조가 뚜렷한 3개의 단락으로 구성된 글을 창작한 후, 단락의 순서를 뒤섞어 문제로 만들어줘."
    else: # essay
        type_instruction = "학생의 창의적인 생각이나 가치관을 엿볼 수 있는 개방적인 질문과, 그에 대한 생각을 유도하는 1~2문장의 짧은 상황을 제시해줘."

    base_prompt = f"""너는 지금부터 '{CATEGORY_MAP.get(category, "일반")}' 유형의 독서력 평가 문제를 출제하는 최고의 교육 전문가야.
다음 규칙을 반드시 지켜서, ```json 과 ``` 로 감싸진 JSON 형식으로 완벽한 문제 1개를 생성해줘.

[규칙]
1. 대상 연령: {age_group}세
2. 언어 및 난이도: {level_instruction}
3. 지문 및 문제 구성: {type_instruction}
4. 객관식 보기 (options):
   - 반드시 4개의 보기를 만들어줘.
   - 정답(answer)은 명확해야 해.
   - 정답 외에, 학생들이 가장 헷갈릴 만한 '매력적인 오답'을 반드시 1개 포함하고, 왜 그것이 오답인지에 대한 간단한 해설(distractor_explanation)을 함께 생성해줘.
5. 질문(question): 지문을 읽고 풀어야 할 명확한 질문을 1개 생성해줘.
6. JSON 형식 준수: 아래의 키(key)를 모두 포함하고, 값(value)은 모두 문자열(string) 또는 리스트(list)로 작성해줘.
   - "title": "[사건 파일 No.XXX] - {CATEGORY_MAP.get(category, "일반")}" (XXX는 임의의 세자리 숫자)
   - "passage": "생성된 지문"
   - "question": "생성된 질문"
   - "options": ["보기1", "보기2", "보기3", "보기4"]
   - "answer": "정답 보기"
   - "distractor_explanation": "매력적인 오답에 대한 해설"
   - "category": "{category}"
   - "targetAge": "{age_group}"
   - "type": "multiple_choice"
"""
    if category == "essay":
        base_prompt = base_prompt.replace('4. 객관식 보기 (options):', '# 객관식 보기 없음').replace('"options": ["보기1", "보기2", "보기3", "보기4"]', '"options": []').replace('"answer": "정답 보기"', '"answer": ""').replace('"distractor_explanation": "매력적인 오답에 대한 해설"', '"distractor_explanation": ""').replace('"type": "multiple_choice"', '"type": "essay"')
    
    return base_prompt

def call_vertex_ai_sdk(prompt):
    model = GenerativeModel("gemini-1.5-pro-001")
    response = model.generate_content([prompt])
    
    raw_text = response.text
    match = re.search(r'```json\s*([\s\S]+?)\s*```', raw_text)
    if match:
        json_str = match.group(1)
        return json.loads(json_str)
    else:
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
             raise ValueError(f"AI가 유효한 JSON을 생성하지 못했습니다: {raw_text}")


# --- 5. 라우팅 (API 엔드포인트) ---
@app.route('/')
def serve_index(): return render_template('index.html')

@app.route('/admin')
def serve_admin(): return render_template('admin.html')

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
        return jsonify({"success": False, "message": f"서버 오류: {e}"}), 500

@app.route('/api/get-codes', methods=['GET'])
def get_codes():
    if not db: return jsonify([]), 500
    try:
        codes_ref = db.collection('access_codes').order_by('createdAt', direction=firestore.Query.DESCENDING).stream()
        codes = []
        for doc in codes_ref:
            c = doc.to_dict()
            # Firestore 타임스탬프를 Python datetime 객체로 변환
            dt_object = c['createdAt']
            # KST (UTC+9)로 변환
            kst = timezone(timedelta(hours=9))
            c['createdAt'] = dt_object.astimezone(kst).strftime('%Y-%m-%d %H:%M:%S')
            c['code'] = doc.id
            codes.append(c)
        return jsonify(codes)
    except Exception as e:
        print(f"코드 조회 오류: {e}")
        return jsonify([]), 500

@app.route('/api/generate-question', methods=['POST'])
def generate_question_from_ai():
    if not db: return jsonify({"success": False, "message": "DB 연결 실패"}), 500
    try:
        data = request.get_json()
        prompt = get_detailed_prompt(data.get('category'), data.get('ageGroup'))
        question_data = call_vertex_ai_sdk(prompt)
        db.collection('questions').add(question_data)
        return jsonify({"success": True, "message": f"성공: AI가 '{question_data.get('title', '새로운')}' 문제를 생성했습니다."})
    except Exception as e:
        print(f"AI 문제 생성 중 오류: {e}")
        return jsonify({"success": False, "message": f"AI 문제 생성 중 오류 발생: {e}"}), 500

@app.route('/api/generate-question-from-text', methods=['POST'])
def generate_question_from_text():
    if not db: return jsonify({"success": False, "message": "DB 연결 실패"}), 500
    try:
        data = request.get_json()
        prompt = get_detailed_prompt(data.get('category'), data.get('ageGroup'), data.get('textContent'))
        question_data = call_vertex_ai_sdk(prompt)
        db.collection('questions').add(question_data)
        return jsonify({"success": True, "message": f"성공: AI가 텍스트 기반으로 '{question_data.get('title', '새로운')}' 문제를 생성했습니다."})
    except Exception as e:
        print(f"텍스트 기반 문제 생성 중 오류: {e}")
        return jsonify({"success": False, "message": f"텍스트 기반 문제 생성 중 오류 발생: {e}"}), 500

@app.route('/api/validate-code', methods=['POST'])
def validate_code():
    if not db: return jsonify({"success": False, "message": "DB 연결 실패"}), 500
    code = request.get_json().get('code', '').upper()
    code_ref = db.collection('access_codes').document(code)
    code_doc = code_ref.get()
    if not code_doc.exists: return jsonify({"success": False, "message": "유효하지 않은 코드입니다."})
    if code_doc.to_dict().get('isUsed'): return jsonify({"success": False, "message": "이미 사용된 코드입니다."})
    return jsonify({"success": True})

@app.route('/api/get-test', methods=['POST'])
def get_test():
    if not db: return jsonify([]), 500
    try:
        data = request.get_json()
        age = int(data.get('age', 0))
        age_group = "10-13"
        if 14 <= age <= 16: age_group = "14-16"
        elif 17 <= age <= 19: age_group = "17-19"

        test_structure = {
            "title": 2, "theme": 2, "argument": 2, "inference": 2,
            "pronoun": 2, "sentence_ordering": 2, "paragraph_ordering": 2, "essay": 1
        }
        questions = []
        for category, needed_count in test_structure.items():
            docs = db.collection('questions').where('targetAge', '==', age_group).where('category', '==', category).stream()
            potential_questions = [doc.to_dict() for doc in docs]
            for q, doc in zip(potential_questions, docs): q['id'] = doc.id
            
            num_to_select = min(needed_count, len(potential_questions))
            if num_to_select > 0:
                questions.extend(random.sample(potential_questions, num_to_select))
        
        for q in questions:
             q['title'] = f"[사건 파일 No.{q['id'][:3]}] - {CATEGORY_MAP.get(q.get('category'), '기타')}"
             q['category_kr'] = CATEGORY_MAP.get(q.get('category'), '기타')
        
        random.shuffle(questions)
        print(f"문제 생성 완료: {len(questions)}개 문항 ({age_group} 대상)")
        return jsonify(questions)
    except Exception as e:
        print(f"'/api/get-test' 오류: {e}")
        return jsonify([]), 500

@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    if not db or not sheet: return jsonify({"success": False, "message": "DB 또는 시트 연결 실패"}), 500
    
    data = request.get_json()
    user_info = data.get('userInfo', {})
    results = data.get('results', [])
    
    try:
        # 1. 점수 및 메타인지 계산
        scores = { "정보 이해력": [], "논리 분석력": [], "단서 추론력": [], "비판적 사고력": [], "창의적 서술력": [] }
        metacognition = {"confident_correct": 0, "confident_error": 0, "unsure_correct": 0, "unsure_error": 0}
        total_time = sum(r.get('time', 0) for r in results)
        correct_count = 0
        
        for r in results:
            score_category = SCORE_CATEGORY_MAP.get(r['question']['category'])
            is_correct = (r['question'].get('type') != 'essay' and r['answer'] == r['question']['answer']) or \
                         (r['question'].get('type') == 'essay' and len(r.get('answer', '')) >= 50)
            
            if is_correct: correct_count += 1
            if score_category: scores[score_category].append(100 if is_correct else 0)

            confidence = r.get('confidence', 'unsure')
            if confidence == 'confident':
                metacognition['confident_correct' if is_correct else 'confident_error'] += 1
            else:
                metacognition['unsure_correct' if is_correct else 'unsure_error'] += 1

        final_scores = {cat: (sum(s) / len(s)) if s else 0 for cat, s in scores.items()}
        final_scores["문제 풀이 속도"] = max(0, 100 - (total_time / len(results) - 30)) if results else 0

        # 2. AI 동적 리포트 생성
        final_report_text = "결과 분석 중..." # Placeholder
        try:
            final_report_text = generate_dynamic_report_from_ai(user_info.get('name'), final_scores, metacognition)
        except Exception as ai_e:
            print(f"AI 동적 리포트 생성 실패: {ai_e}")
            final_report_text = "AI 리포트 생성에 실패했습니다. 기본 리포트를 표시합니다."

        # 3. 추천 활동 생성
        recommendations = []
        sorted_scores = sorted([(score, cat) for cat, score in final_scores.items() if cat != "문제 풀이 속도"])
        if sorted_scores:
            weakest_category = sorted_scores[0][1]
            if weakest_category == "단서 추론력": recommendations.append({"skill": "단서 추론력 강화", "text": "서점에서 셜록 홈즈 단편선 중 한 편을 골라 읽고, 주인공이 단서를 찾아내는 과정을 노트에 정리해보세요."})
            elif weakest_category == "비판적 사고력": recommendations.append({"skill": "비판적 사고력 강화", "text": "이번 주 신문 사설을 하나 골라, 글쓴이의 주장에 동의하는 부분과 동의하지 않는 부분을 나누어 한 문단으로 요약해보세요."})
            elif weakest_category == "논리 분석력": recommendations.append({"skill": "논리 분석력 강화", "text": "글의 순서나 구조를 파악하는 연습을 해보세요. 짧은 뉴스 기사를 읽고 문단별로 핵심 내용을 요약하는 훈련이 도움이 될 것입니다."})

        # 4. 데이터 저장 (Firestore & Google Sheets)
        timestamp = datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')
        report_data = {
            "userInfo": user_info, "results": results, "scores": final_scores,
            "metacognition": metacognition, "reportText": final_report_text,
            "recommendations": recommendations, "timestamp": timestamp
        }
        db.collection('reports').add(report_data)

        sheet_row = [
            timestamp, user_info.get('name'), user_info.get('age'), user_info.get('code'),
            final_scores.get('정보 이해력', 0), final_scores.get('논리 분석력', 0),
            final_scores.get('단서 추론력', 0), final_scores.get('비판적 사고력', 0),
            final_scores.get('창의적 서술력', 0), final_scores.get('문제 풀이 속도', 0),
            correct_count, len(results), total_time
        ]
        sheet.append_row(sheet_row)
        
        # 5. 프론트엔드로 결과 전송
        return jsonify({
            "success": True, "analysis": final_scores, "metacognition": metacognition,
            "overall_comment": final_report_text, "recommendations": recommendations
        })
    except Exception as e:
        print(f"결과 처리 중 오류: {e}")
        return jsonify({"success": False, "message": f"결과를 전송하는 중 오류가 발생했습니다: {e}"}), 500

def generate_dynamic_report_from_ai(user_name, scores, metacognition):
    strongest_score, strongest_category, weakest_score, weakest_category = 0, "없음", 100, "없음"
    for category, score in scores.items():
        if category != "문제 풀이 속도":
            if score > strongest_score: strongest_score, strongest_category = score, category
            if score < weakest_score: weakest_score, weakest_category = score, category
    
    student_data_summary = f"- 학생 이름: {user_name}\n- 가장 뛰어난 능력: {strongest_category} ({strongest_score:.0f}점)\n- 가장 보완이 필요한 능력: {weakest_category} ({weakest_score:.0f}점)\n- 메타인지 분석: '자신만만하게 정답을 맞힌 문항' {metacognition['confident_correct']}개, '자신만만하게 틀린 문항(개념 오적용)' {metacognition['confident_error']}개."

    prompt = f"""당신은 학생의 독서력 테스트 결과를 분석하고, 따뜻하고 격려하는 어조로 맞춤형 종합 소견을 작성하는 최고의 교육 컨설턴트입니다.
아래 학생의 테스트 결과 데이터를 바탕으로, 학생만을 위한 특별한 종합 소견을 작성해주세요.
[규칙]
1. 학생의 이름을 부르며 친근하게 시작해주세요.
2. 학생의 가장 뛰어난 능력을 먼저 칭찬하며 자신감을 북돋아주세요.
3. 가장 보완이 필요한 능력에 대해서는, 부정적인 표현 대신 '성장 기회'로 표현하며 구체적인 조언을 한두 문장 덧붙여주세요.
4. 메타인지 분석 결과를 자연스럽게 녹여내어, 학생이 자신의 학습 습관을 돌아볼 수 있도록 유도해주세요. 특히 '자신만만하게 틀린 문항'이 있었다면, 그 점을 부드럽게 지적하며 꼼꼼함의 중요성을 강조해주세요.
5. 전체 내용은 3~4개의 문단으로 구성된, 진심이 담긴 하나의 완결된 글로 작성해주세요.
6. Markdown 형식(#, ##, **)을 사용하여 가독성을 높여주세요.
[학생 테스트 결과 데이터]
{student_data_summary}
[종합 소견 작성 시작]
"""
    model = GenerativeModel("gemini-1.5-pro-001")
    response = model.generate_content([prompt])
    return response.text

# --- 서버 실행 ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))




