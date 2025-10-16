import os
import json
import random
import string
import time
import logging
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
import gspread
import re
import requests

# --- 1. Flask 앱 초기화 ---
app = Flask(__name__, template_folder='templates')

# --- 2. 외부 서비스 초기화 ---
db = None
sheet = None
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY') 

try:
    google_creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
    cred_dict = {}
    if google_creds_json:
        cred_dict = json.loads(google_creds_json)
        
    if cred_dict:
        firebase_cred = credentials.Certificate(cred_dict)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(firebase_cred)
        db = firestore.client()
        app.logger.info("✅ Firebase 초기화 성공")

        gc = gspread.service_account_from_dict(cred_dict)
        sheet = gc.open("독서력 진단 결과").sheet1
        app.logger.info("✅ Google Sheets ('독서력 진단 결과') 시트 열기 성공")
    else:
        app.logger.warning("🚨 경고: GOOGLE_CREDENTIALS_JSON 환경 변수가 설정되지 않아 DB/Sheet 초기화 실패.")

except Exception as e:
    app.logger.error(f"🚨 외부 서비스 초기화 실패: {e}", exc_info=True)

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

# --- 4. AI 관련 함수 ---
def get_detailed_prompt(category, age_group, text_content=None, difficulty='표준'):
    difficulty_instruction = ""
    if difficulty == '기초':
        difficulty_instruction = "전체적으로 문장의 길이를 짧게 하고, 쉬운 어휘를 사용해줘."
    elif difficulty == '심화':
        difficulty_instruction = "문장의 구조를 복잡하게 만들고, 추상적이거나 전문적인 어휘를 일부 포함해줘."

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
    topics = { "default": ["흥미로운 동물 상식", "일상 속 과학 원리", "역사 속 인물 이야기"], "info": ["환경 보호의 중요성", "새로운 기술 트렌드", "건강한 생활 습관"], "logic": ["사회 현상 분석", "신문 사설", "주장이 담긴 칼럼"], "inference": ["과학 탐사(우주, 해양)", "최신 뉴스 기사의 이면", "미스터리한 사건의 재구성"] }
    
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
2. 언어 및 난이도: {level_instruction} {difficulty_instruction}
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

    if category == "pronoun":
        pronoun_instruction = "7. 질문 생성 시, '밑줄 친' 이라는 표현 대신, 지시어를 괄호로 감싸고 (예: (이것은)) 질문에 '괄호 안의 단어가 가리키는 것은?'과 같이 표현해줘."
        base_prompt = base_prompt.replace('6. JSON 형식 준수:', f'{pronoun_instruction}\n6. JSON 형식 준수:')

    if category in ["sentence_ordering", "paragraph_ordering"]:
        base_prompt = base_prompt.replace('4. 객관식 보기 (options):', '# 객관식 보기 없음').replace('"options": ["보기1", "보기2", "보기3", "보기4"]', '"options": []').replace('"answer": "정답 보기"', '"answer": ""').replace('"distractor_explanation": "매력적인 오답에 대한 해설"', '"distractor_explanation": ""').replace('"type": "multiple_choice"', '"type": "essay"')

    if category == "essay":
        base_prompt = base_prompt.replace('4. 객관식 보기 (options):', '# 객관식 보기 없음').replace('"options": ["보기1", "보기2", "보기3", "보기4"]', '"options": []').replace('"answer": "정답 보기"', '"answer": ""').replace('"distractor_explanation": "매력적인 오답에 대한 해설"', '"distractor_explanation": ""').replace('"type": "multiple_choice"', '"type": "essay"')
    
    return base_prompt

def call_ai_for_json(prompt, model_name="gemini-2.5-pro"):
    if not GEMINI_API_KEY: raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")
    url = f"https://generativelanguage.googleapis.com/v1/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    data = {'contents': [{'parts': [{'text': prompt}]}]}
    response = requests.post(url, headers=headers, data=json.dumps(data), timeout=180)
    response.raise_for_status()
    result = response.json()
    if not result.get('candidates'): raise ValueError(f"AI가 유효한 응답을 생성하지 못했습니다. 응답 내용: {result}")
    raw_text = result['candidates'][0]['content']['parts'][0]['text']
    match = re.search(r'```json\s*([\s\S]+?)\s*```', raw_text)
    if match:
        json_str = match.group(1)
        return json.loads(json_str)
    else:
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            raise ValueError(f"AI가 유효한 JSON을 생성하지 못했습니다: {raw_text}")

def call_ai_for_text(prompt, model_name="gemini-2.5-pro"):
    if not GEMINI_API_KEY: raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")
    url = f"https://generativelanguage.googleapis.com/v1/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    data = {'contents': [{'parts': [{'text': prompt}]}]}
    response = requests.post(url, headers=headers, data=json.dumps(data), timeout=180)
    response.raise_for_status()
    result = response.json()
    if not result.get('candidates'): raise ValueError(f"AI가 유효한 응답을 생성하지 못했습니다. 응답 내용: {result}")
    return result['candidates'][0]['content']['parts'][0]['text']

# --- 5. 라우팅 (API 엔드포인트) ---
@app.route('/')
def serve_index(): return render_template('index.html')

@app.route('/admin')
def serve_admin(): return render_template('admin.html')

# --- 관리자 페이지 API ---
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
            dt_object = c['createdAt']
            kst = timezone(timedelta(hours=9))
            c['createdAt'] = dt_object.astimezone(kst).strftime('%Y-%m-%d %H:%M:%S')
            c['code'] = doc.id
            codes.append(c)
        return jsonify(codes)
    except Exception as e:
        app.logger.error(f"코드 조회 오류: {e}", exc_info=True)
        return jsonify([]), 500

@app.route('/api/generate-question-set', methods=['POST'])
def generate_question_set():
    if not db: return jsonify({"success": False, "message": "DB 연결 실패"}), 500
    data = request.get_json()
    if not data or 'ageGroup' not in data or 'difficulty' not in data:
        return jsonify({"success": False, "message": "ageGroup과 difficulty는 필수 항목입니다."}), 400

    age_group = data.get('ageGroup')
    difficulty = data.get('difficulty')
    text_content = data.get('textContent', None)
    
    categories_to_generate = ["title", "theme", "argument", "inference", "pronoun", "sentence_ordering", "paragraph_ordering"]
    
    results = []
    for category in categories_to_generate:
        try:
            app.logger.info(f"일괄 생성 중: Category: {category}, Age: {age_group}, Difficulty: {difficulty}")
            prompt = get_detailed_prompt(category, age_group, text_content, difficulty)
            question_data = call_ai_for_json(prompt)
            question_data['difficulty'] = difficulty # 난이도 정보 추가

            required_keys = ['passage', 'question']
            if question_data.get('type') == 'multiple_choice':
                required_keys.extend(['options', 'answer'])
            if not all(key in question_data for key in required_keys):
                 raise ValueError("AI 생성 데이터에 필수 키 누락")

            db.collection('questions').add(question_data)
            results.append({"category": CATEGORY_MAP.get(category), "status": "성공"})
        except Exception as e:
            app.logger.error(f"'{category}' 유형 생성 실패: {e}")
            results.append({"category": CATEGORY_MAP.get(category), "status": "실패", "reason": str(e)})

    return jsonify({"success": True, "message": "문제 일괄 생성이 완료되었습니다.", "results": results})

@app.route('/api/get-questions', methods=['GET'])
def get_questions():
    if not db: return jsonify([]), 500
    try:
        questions_ref = db.collection('questions').stream()
        questions = []
        for doc in questions_ref:
            q = doc.to_dict()
            q['id'] = doc.id
            questions.append(q)
        return jsonify(questions)
    except Exception as e:
        app.logger.error(f"문제 목록 조회 오류: {e}", exc_info=True)
        return jsonify([]), 500

@app.route('/api/delete-questions', methods=['POST'])
def delete_questions():
    if not db: return jsonify({"success": False, "message": "DB 연결 실패"}), 500
    data = request.get_json()
    ids_to_delete = data.get('ids', [])
    if not ids_to_delete:
        return jsonify({"success": False, "message": "삭제할 ID 목록이 없습니다."}), 400
    
    try:
        for q_id in ids_to_delete:
            db.collection('questions').document(q_id).delete()
        app.logger.info(f"{len(ids_to_delete)}개 문제 삭제 성공.")
        return jsonify({"success": True, "message": f"{len(ids_to_delete)}개 문제를 삭제했습니다."})
    except Exception as e:
        app.logger.error(f"문제 삭제 중 오류 발생: {e}", exc_info=True)
        return jsonify({"success": False, "message": "문제 삭제 중 오류가 발생했습니다."}), 500

@app.route('/api/regenerate-question', methods=['POST'])
def regenerate_question():
    if not db: return jsonify({"success": False, "message": "DB 연결 실패"}), 500
    data = request.get_json()
    question_id = data.get('id')
    if not question_id:
        return jsonify({"success": False, "message": "ID가 필요합니다."}), 400
    
    try:
        doc_ref = db.collection('questions').document(question_id)
        old_doc = doc_ref.get()
        if not old_doc.exists:
            return jsonify({"success": False, "message": "문서를 찾을 수 없습니다."}), 404
        
        old_data = old_doc.to_dict()
        category = old_data.get('category')
        age_group = old_data.get('targetAge')
        difficulty = old_data.get('difficulty', '표준') # 기존 난이도 유지

        prompt = get_detailed_prompt(category, age_group, None, difficulty)
        new_question_data = call_ai_for_json(prompt)
        new_question_data['difficulty'] = difficulty

        doc_ref.update(new_question_data)
        app.logger.info(f"문제 재성공 성공: ID {question_id}")
        return jsonify({"success": True, "message": "문제를 성공적으로 다시 생성했습니다."})

    except Exception as e:
        app.logger.error(f"문제 재성성 중 오류: {e}", exc_info=True)
        return jsonify({"success": False, "message": "문제 재성성 중 오류가 발생했습니다."})

# --- 사용자 페이지 API ---
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

        test_structure = { "title": 2, "theme": 2, "argument": 2, "inference": 2, "pronoun": 2, "sentence_ordering": 2, "paragraph_ordering": 2, "essay": 1 }
        questions = []
        for category, needed_count in test_structure.items():
            query = db.collection('questions').where(filter=FieldFilter('targetAge', '==', age_group)).where(filter=FieldFilter('category', '==', category))
            docs = query.stream()
            potential_questions = []
            for doc in docs:
                q = doc.to_dict()
                q['id'] = doc.id
                potential_questions.append(q)
            
            num_to_select = min(needed_count, len(potential_questions))
            if num_to_select > 0:
                questions.extend(random.sample(potential_questions, num_to_select))
        
        question_number = 1
        for q in questions:
             q['title'] = f"{question_number}. {CATEGORY_MAP.get(q.get('category'), '기타')}"
             q['category_kr'] = CATEGORY_MAP.get(q.get('category'), '기타')
             question_number += 1
        
        random.shuffle(questions)
        app.logger.info(f"문제 생성 완료: {len(questions)}개 문항 ({age_group} 대상)")
        return jsonify(questions)
    except Exception as e:
        app.logger.error(f"'/api/get-test' 오류: {e}", exc_info=True)
        return jsonify([]), 500

@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    if not db or not sheet: return jsonify({"success": False, "message": "DB 또는 시트 연결 실패"}), 500
    data = request.get_json()
    user_info = data.get('userInfo', {})
    results = data.get('results', [])
    
    try:
        scores = { "정보 이해력": [], "논리 분석력": [], "단서 추론력": [], "비판적 사고력": [], "창의적 서술력": [] }
        metacognition_details = { 'confident_correct': [], 'confident_error': [], 'unsure_correct': [], 'unsure_error': [] }
        total_time = sum(r.get('time', 0) for r in results)
        correct_count = 0
        
        for r in results:
            score_category = SCORE_CATEGORY_MAP.get(r['question']['category'])
            is_correct = (r['question'].get('type') != 'essay' and r['answer'] == r['question']['answer']) or (r['question'].get('type') == 'essay' and len(r.get('answer', '')) >= 50)
            if is_correct: correct_count += 1
            if score_category: scores[score_category].append(100 if is_correct else 0)
            confidence = r.get('confidence', 'unsure')
            time_spent = r.get('time', 0)
            if confidence == 'confident':
                metacognition_details['confident_correct' if is_correct else 'confident_error'].append(time_spent)
            else:
                metacognition_details['unsure_correct' if is_correct else 'unsure_error'].append(time_spent)

        final_scores = {cat: (sum(s) / len(s)) if s else 0 for cat, s in scores.items()}
        final_scores["문제 풀이 속도"] = max(0, 100 - (total_time / len(results) - 30)) if results else 0
        metacognition_summary = {
            'confident_correct': len(metacognition_details['confident_correct']), 'confident_error': len(metacognition_details['confident_error']),
            'unsure_correct': len(metacognition_details['unsure_correct']), 'unsure_error': len(metacognition_details['unsure_error']),
            'avg_time_cc': sum(metacognition_details['confident_correct']) / len(metacognition_details['confident_correct']) if metacognition_details['confident_correct'] else 0,
            'avg_time_ce': sum(metacognition_details['confident_error']) / len(metacognition_details['confident_error']) if metacognition_details['confident_error'] else 0,
            'avg_time_uc': sum(metacognition_details['unsure_correct']) / len(metacognition_details['unsure_correct']) if metacognition_details['unsure_correct'] else 0,
            'avg_time_ue': sum(metacognition_details['unsure_error']) / len(metacognition_details['unsure_error']) if metacognition_details['unsure_error'] else 0,
        }

        final_report_text = "결과 분석 중..."
        try:
            final_report_text = generate_dynamic_report_from_ai(user_info.get('name'), final_scores, metacognition_summary, len(results), correct_count)
        except Exception as ai_e:
            app.logger.error(f"AI 동적 리포트 생성 실패: {ai_e}", exc_info=True)
            final_report_text = "AI 리포트 생성에 실패했습니다. 기본 리포트를 표시합니다."

        recommendations = []
        sorted_scores = sorted([(score, cat) for cat, score in final_scores.items() if cat != "문제 풀이 속도"])
        if sorted_scores:
            weakest_category = sorted_scores[0][1]
            if weakest_category == "단서 추론력": recommendations.append({"skill": "단서 추론력 강화", "text": "서점에서 셜록 홈즈 단편선 중 한 편을 골라 읽고, 주인공이 단서를 찾아내는 과정을 노트에 정리해보세요."})
            elif weakest_category == "비판적 사고력": recommendations.append({"skill": "비판적 사고력 강화", "text": "이번 주 신문 사설을 하나 골라, 글쓴이의 주장에 동의하는 부분과 동의하지 않는 부분을 나누어 한 문단으로 요약해보세요."})
            elif weakest_category == "논리 분석력": recommendations.append({"skill": "논리 분석력 강화", "text": "글의 순서나 구조를 파악하는 연습을 해보세요. 짧은 뉴스 기사를 읽고 문단별로 핵심 내용을 요약하는 훈련이 도움이 될 것입니다."})

        timestamp = datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')
        report_data = { "userInfo": user_info, "results": results, "scores": final_scores, "metacognition": metacognition_summary, "reportText": final_report_text, "recommendations": recommendations, "timestamp": timestamp }
        db.collection('reports').add(report_data)

        sheet_row = [ timestamp, user_info.get('name'), user_info.get('age'), user_info.get('code'), final_scores.get('정보 이해력', 0), final_scores.get('논리 분석력', 0), final_scores.get('단서 추론력', 0), final_scores.get('비판적 사고력', 0), final_scores.get('창의적 서술력', 0), final_scores.get('문제 풀이 속도', 0), correct_count, len(results), total_time ]
        sheet.append_row(sheet_row)
        
        return jsonify({ "success": True, "analysis": final_scores, "metacognition": metacognition_summary, "overall_comment": final_report_text, "recommendations": recommendations })
    except Exception as e:
        app.logger.error(f"결과 처리 중 오류: {e}", exc_info=True)
        return jsonify({"success": False, "message": f"결과를 전송하는 중 오류가 발생했습니다: {e}"}), 500

def generate_dynamic_report_from_ai(user_name, scores, metacognition, total_questions, correct_count):
    strongest_score, strongest_category, weakest_score, weakest_category = 0, "없음", 100, "없음"
    for category, score in scores.items():
        if category != "문제 풀이 속도":
            if score > strongest_score: strongest_score, strongest_category = score, category
            if score < weakest_score: weakest_score, weakest_category = score, category
    
    student_data_summary = f"""- 학생 이름: {user_name}
- 총 문항 수: {total_questions}개
- 정답 수: {correct_count}개
- 강점 능력: {strongest_category} ({strongest_score:.0f}점)
- 보완점: {weakest_category} ({weakest_score:.0f}점)
- 메타인지 상세 분석:
  - 숙달(자신있게 정답): {metacognition['confident_correct']}개 (평균 {metacognition.get('avg_time_cc', 0):.1f}초)
  - 오개념(자신있게 오답): {metacognition['confident_error']}개 (평균 {metacognition.get('avg_time_ce', 0):.1f}초)
  - 성장(고민 후 정답): {metacognition['unsure_correct']}개 (평균 {metacognition.get('avg_time_uc', 0):.1f}초)
  - 부족(고민 후 오답): {metacognition['unsure_error']}개 (평균 {metacognition.get('avg_time_ue', 0):.1f}초)
"""

    prompt = f"""당신은 대한민국 최고의 교육 데이터 분석가이자 학습 코치입니다. 학생의 독서력 테스트 결과를 바탕으로, 학부모와 학생 모두에게 깊은 통찰력과 구체적인 실천 방안을 제공하는 전문적인 분석 보고서를 작성해야 합니다. 따뜻하지만 분석적인 어조를 유지해주세요.

[학생 테스트 결과 데이터]
{student_data_summary}

[보고서 작성 규칙]
1.  **서론: 전체 결과 요약**: 학생의 이름을 부르며 시작하고, 총 문항 수와 정답 수를 바탕으로 전체적인 성취도를 간략히 언급합니다. 학생의 가장 뛰어난 강점 능력을 칭찬하며 긍정적인 분위기를 형성합니다.
2.  **본론 1: 데이터 기반 능력 심층 분석**: '강점 능력'이 왜 뛰어난지 데이터에 근거하여 분석해주세요. (예: "정보 이해력 점수가 높고, 관련 문항을 빠르고 자신있게 풀어낸 것으로 보아, 글의 핵심 내용을 정확하고 신속하게 파악하는 능력이 탁월합니다.") '보완이 필요한 능력'에 대해서는 '성장 기회'로 표현하며, 구체적인 데이터로 원인을 진단해주세요. (예: "비판적 사고력 문항에서 오답이 많고 풀이 시간이 길었던 점은, 글에 숨겨진 의도를 파악하거나 다른 관점에서 생각하는 연습이 더 필요하다는 신호입니다.")
3.  **본론 2: 메타인지 분석 및 학습 전략 코칭**: '메타인지 상세 분석' 데이터를 활용하여 학생의 학습 습관을 진단합니다. **'오개념(자신있게 오답)'** 항목이 1개 이상 있다면, 가장 시급하게 교정해야 할 부분임을 강조하세요. 잘못된 지식이나 습관을 확신하고 있을 가능성이 높으므로, 개념을 다시 꼼꼼히 학습할 것을 조언합니다. **'성장(고민 후 정답)'** 항목은 칭찬의 포인트입니다. 어려운 문제도 포기하지 않고 해결해내는 끈기와 잠재력을 칭찬해주세요.
4.  **결론: 성장을 위한 구체적인 코칭 가이드**: 분석 내용을 종합하여, 학생의 성장을 위한 1~2가지 핵심 조언을 제시합니다. **(독서 추천)** 학생의 '보완점'을 길러줄 수 있는 책의 종류(장르)를 추천하고, 왜 그 책이 도움이 되는지, 어느 정도 분량(예: 200페이지 내외)의 책부터 시작하면 좋을지 구체적으로 제안해주세요. 학생에게 동기를 부여할 수 있는 긍정적인 비전을 제시하며 마무리합니다.
5.  **형식:** 전체 내용은 가독성을 위해 Markdown(#, ##, **)을 사용하여 명확하게 구조화해주세요.
"""
    return call_ai_for_text(prompt, model_name="gemini-2.5-pro")

# --- 서버 실행 ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))