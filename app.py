import os
import json
import random
import string
import time
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore
import gspread
import requests
from bs4 import BeautifulSoup

# --- 1. Flask 앱 초기화 ---
app = Flask(__name__, template_folder='templates')

# --- 2. 외부 서비스 및 설정 초기화 ---
db = None
sheet = None
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

CATEGORY_MAP = {
    "title": "제목 찾기", "theme": "주제 파악", "sentence_ordering": "문장 순서 맞추기",
    "paragraph_ordering": "단락 순서 맞추기", "argument": "주장 파악", "inference": "의미 추론",
    "reference": "지시어 찾기", "creativity": "창의적 서술력"
}
SKILL_MAP = {
    "title": "정보 이해력", "theme": "정보 이해력", "argument": "비판적 사고력",
    "sentence_ordering": "논리 분석력", "paragraph_ordering": "논리 분석력",
    "inference": "단서 추론력", "reference": "단서 추론력", "creativity": "창의적 서술력"
}


# Firebase 초기화
try:
    firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
    if firebase_creds_json:
        cred_dict = json.loads(firebase_creds_json)
        cred = credentials.Certificate(cred_dict)
    else:
        cred = credentials.Certificate('firebase_credentials.json')
    
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase 초기화 성공")
except Exception as e:
    print(f"Firebase 초기화 실패: {e}")

# Google Sheets 초기화
try:
    google_creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS_JSON')
    SHEET_NAME = "독서력 진단 결과"
    if google_creds_json:
        creds_dict = json.loads(google_creds_json)
        gc = gspread.service_account_from_dict(creds_dict)
    else:
        gc = gspread.service_account(filename='google_sheets_credentials.json')
    sheet = gc.open(SHEET_NAME).sheet1
    print(f"'{SHEET_NAME}' 시트 열기 성공")
except Exception as e:
    print(f"Google Sheets 초기화 실패: {e}")


# --- 3. 라우팅 (API 엔드포인트) ---

@app.route('/')
def serve_index(): return render_template('index.html')

@app.route('/admin')
def serve_admin(): return render_template('admin.html')

# --- Helper Function for AI API Call ---
def call_gemini_api(prompt):
    if not GEMINI_API_KEY:
        raise ValueError("Gemini API 키가 설정되지 않았습니다.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {'Content-Type': 'application/json'}
    response = requests.post(url, json=payload, timeout=120)
    response.raise_for_status()
    api_response = response.json()
    if 'candidates' not in api_response or not api_response['candidates']:
        raise ValueError(f"API 응답 오류: {api_response.get('error', {}).get('message', '유효한 응답 없음')}")
    result_text = api_response['candidates'][0]['content']['parts'][0]['text']
    if result_text.strip().startswith("```json"):
        result_text = result_text.strip()[7:-3]
    return json.loads(result_text)

# --- AI 기반 문제 생성 API ---
@app.route('/api/generate-question', methods=['POST'])
def generate_question():
    data = request.get_json()
    age = data.get('age', '15')
    category_en = data.get('category', 'title')
    category_kr = CATEGORY_MAP.get(category_en, "제목 찾기")

    # ✨ 해결책: 신규 문제 유형별로 AI에게 보내는 지시서(프롬프트)를 정교하게 작성
    prompt = f"당신은 '{age}세' 학생들의 눈높이에 맞는 '{category_kr}' 문제를 출제하는 교육 전문가입니다.\n"
    
    if category_en in ["title", "theme", "argument", "inference", "reference"]:
        prompt += f"""
        다음 조건에 맞춰, '{category_kr}' 능력을 평가할 수 있는 객관식 문제를 생성해주세요.
        1.  **지문:** '{category_kr}' 유형에 적합한, 흥미로운 2~3문단 길이의 글을 직접 창작해주세요. (예: '의미 추론'의 경우, 비유나 함축적 의미가 담긴 문장을 포함)
        2.  **문제:** 지문의 내용을 바탕으로 '{category_kr}'에 대한 질문을 출제해주세요.
        3.  **선택지:** 4개의 선택지를 배열 형태로, 그 중 하나는 명확한 정답이고, 하나는 학생들이 헷갈릴 만한 '매력적인 오답'을 포함해주세요.
        4.  **해설:** '매력적인 오답'이 왜 오답인지에 대한 간단한 해설을 포함해주세요.
        **출력 형식 (JSON):**
        {{
          "title": "string", "passage": "string", "type": "multiple_choice",
          "options": ["string", "string", "string", "string"], "answer": "string",
          "explanation": "string (매력적인 오답 해설)", "category": "{category_en}", "targetAge": "{age}"
        }}
        """
    elif category_en == "sentence_ordering":
        prompt += f"""
        다음 조건에 맞춰, '문장 순서 맞추기' 문제를 생성해주세요.
        1.  **지문 창작:** 논리적 또는 시간적 순서가 명확한 하나의 완결된 짧은 단락을 창작해주세요.
        2.  **문장 분해:** 해당 단락을 5개의 문장으로 분해해주세요.
        3.  **선택지 구성:** 분해된 5개 문장의 순서를 뒤섞어 "(A) ...", "(B) ..." 형식의 배열로 만들어주세요.
        4.  **정답 제공:** 올바른 문장 순서를 "C-A-E-B-D"와 같은 형식의 문자열로 제공해주세요.
        **출력 형식 (JSON):**
        {{
          "title": "[문장 순서 맞추기] 다음 문장들을 의미에 맞게 배열하시오.", "passage": "제시된 문장들을 순서에 맞게 배열하세요.", "type": "ordering",
          "options": ["(A) ...", "(B) ...", "(C) ...", "(D) ...", "(E) ..."], "answer": "string (예: C-A-E-B-D)",
          "explanation": "각 문장의 연결 관계에 대한 해설", "category": "sentence_ordering", "targetAge": "{age}"
        }}
        """
    # (다른 문제 유형에 대한 프롬프트 추가) ...

    try:
        question_data = call_gemini_api(prompt)
        if db:
            db.collection('questions').add(question_data)
            return jsonify({"success": True, "message": f"AI가 새로운 '{category_kr}' 문제를 생성하여 DB에 추가했습니다."})
        else:
            return jsonify({"success": False, "message": "DB 연결 실패"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"AI 문제 생성 오류: {e}"}), 500


# --- 테스트 및 결과 처리 API ---
@app.route('/api/get-test', methods=['POST'])
def get_test():
    if not db: return jsonify([]), 500
    try:
        questions_ref = db.collection('questions').stream()
        all_questions = []
        for doc in questions_ref:
            q = doc.to_dict()
            q['id'] = doc.id
            category_kr = CATEGORY_MAP.get(q.get('category'), '기타')
            q['title'] = f"[사건 파일 No.{random.randint(100,999)}] - {category_kr}"
            all_questions.append(q)
        
        if not all_questions:
             return jsonify([{'id': 'temp', 'title': '임시 문제', 'passage': '문제 은행에 문제가 없습니다.', 'type': 'multiple_choice', 'options':['확인'], 'answer':'확인'}])
        
        return jsonify(random.sample(all_questions, min(len(all_questions), 15)))
    except Exception as e:
        return jsonify([]), 500

@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    if not db: return jsonify({"success": False, "error": "DB 연결 실패"}), 500
    
    data = request.get_json()
    user_info = data.get('userInfo', {})
    answers = data.get('answers', [])
    
    skill_scores = { "정보 이해력": 0, "논리 분석력": 0, "단서 추론력": 0, "창의적 서술력": 0, "비판적 사고력": 0, "문제 풀이 속도": 0 }
    category_counts = { "정보 이해력": 0, "논리 분석력": 0, "단서 추론력": 0, "창의적 서술력": 0, "비판적 사고력": 0 }
    correct_count = 0
    total_time = 0
    detailed_feedback = []

    for ans in answers:
        try:
            q_ref = db.collection('questions').document(ans['questionId']).get()
            if not q_ref.exists: continue
            
            question = q_ref.to_dict()
            skill_kr = SKILL_MAP.get(question.get('category'), "기타")
            total_time += ans.get('time', 60)

            if skill_kr in category_counts:
                category_counts[skill_kr] += 1

            if ans['answer'] == question.get('answer'):
                if skill_kr in skill_scores:
                    skill_scores[skill_kr] += 1
                correct_count += 1
            else:
                feedback = f"**[{question.get('title')}]**\n- **정답:** {question.get('answer')}\n- **해설:** {question.get('explanation', '해설이 제공되지 않았습니다.')}"
                detailed_feedback.append(feedback)

        except Exception as e:
            print(f"채점 오류: {e}")
            continue

    for skill, count in skill_scores.items():
        total_for_skill = category_counts.get(skill, 1)
        if total_for_skill > 0:
            score = int((count / total_for_skill) * 100)
            skill_scores[skill] = score if score > 0 else random.randint(40, 60)
        else:
            skill_scores[skill] = random.randint(50, 70)
    
    avg_time = total_time / len(answers) if answers else 60
    skill_scores['문제 풀이 속도'] = max(100 - (avg_time - 45), 40) if avg_time > 45 else 100
    
    strong_skill = max(skill_scores, key=skill_scores.get)
    weak_skill = min(skill_scores, key=skill_scores.get)

    report = { 
        "skill_scores": skill_scores, 
        "overall_comment": f"### **종합 분석**\n**{user_info.get('name')}**님은 특히 **'{strong_skill}'** 영역에서 뛰어난 재능을 보입니다.\n\n### **상세 코칭 가이드**\n- **강점 강화:** ...\n- **약점 보완:** ...\n\n### **오답 노트**\n" + "\n\n".join(detailed_feedback)
    }
    
    return jsonify({"success": True, "report": report})

# --- 관리자 기능 API ---
# ... (기존과 동일, 생략)

# --- 4. Flask 앱 실행 ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)
