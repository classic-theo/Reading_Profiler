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
import re

# --- 1. Flask 앱 초기화 ---
app = Flask(__name__, template_folder='templates')

# --- 2. 외부 서비스 초기화 ---
db = None
sheet = None

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
    print("🚨 중요: 시트 이름이 정확한지, 서비스 계정에 '편집자'로 공유되었는지 확인해주세요.")

# --- 3. 핵심 데이터 및 설정 ---
CATEGORY_MAP = {
    "title": "제목/주제 찾기",
    "theme": "제목/주제 찾기",
    "argument": "주장 파악",
    "inference": "의미 추론",
    "pronoun": "지시어 찾기",
    "sentence_ordering": "문장 순서 맞추기",
    "paragraph_ordering": "단락 순서 맞추기",
    "essay": "창의적 서술력",
    "comprehension": "정보 이해력",
    "logic": "논리 분석력",
    "critical_thinking": "비판적 사고력"
}

SCORE_CATEGORY_MAP = {
    "title": "정보 이해력", "theme": "정보 이해력", "argument": "비판적 사고력",
    "inference": "단서 추론력", "pronoun": "단서 추론력",
    "sentence_ordering": "논리 분석력", "paragraph_ordering": "논리 분석력",
    "essay": "창의적 서술력", "comprehension": "정보 이해력", "logic": "논리 분석력",
    "critical_thinking": "비판적 사고력"
}


# --- 4. 라우팅 (API 엔드포인트) ---

@app.route('/')
def serve_index():
    return render_template('index.html')

@app.route('/admin')
def serve_admin():
    return render_template('admin.html')

# --- Admin 페이지 API ---
@app.route('/api/generate-code', methods=['POST'])
def generate_code():
    if not db: return jsonify({"success": False, "message": "DB 연결 실패"}), 500
    try:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        code_ref = db.collection('access_codes').document(code)
        
        if code_ref.get().exists: return generate_code()

        code_ref.set({
            'createdAt': datetime.now(timezone.utc),
            'isUsed': False, 'userName': None
        })
        return jsonify({"success": True, "code": code})
    except Exception as e:
        return jsonify({"success": False, "message": f"코드 생성 오류: {e}"}), 500

@app.route('/api/get-codes', methods=['GET'])
def get_codes():
    if not db: return jsonify([]), 500
    try:
        codes_ref = db.collection('access_codes').order_by('createdAt', direction=firestore.Query.DESCENDING).stream()
        codes = []
        for code in codes_ref:
            c = code.to_dict()
            c['createdAt'] = c['createdAt'].strftime('%Y-%m-%d %H:%M:%S')
            c['code'] = code.id
            codes.append(c)
        return jsonify(codes)
    except Exception as e:
        print(f"코드 조회 오류: {e}")
        return jsonify([]), 500

def call_gemini_api(prompt):
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return {"error": "GEMINI_API_KEY가 설정되지 않았습니다."}

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(api_url, headers=headers, json=data, timeout=120)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 429:
                wait_time = (2 ** attempt) + random.random()
                print(f"429 Too Many Requests. {wait_time:.2f}초 후 재시도...")
                time.sleep(wait_time)
            else:
                return {"error": f"API 요청 실패: {err}"}
        except requests.exceptions.RequestException as err:
            return {"error": f"네트워크 오류: {err}"}
    return {"error": "API 요청 재시도 횟수 초과"}


@app.route('/api/generate-question-from-text', methods=['POST'])
def generate_question_from_text():
    data = request.get_json()
    text = data.get('text', '')
    age_group = data.get('ageGroup', '14-16')
    category = data.get('category', 'comprehension')

    if len(text) < 100:
        return jsonify({"success": False, "message": "분석할 텍스트가 너무 짧습니다. 100자 이상 입력해주세요."}), 400

    prompt = f"""
    당신은 한국 학생들의 독서 능력을 평가하는 전문 AI 문제 출제자입니다. 주어진 텍스트를 바탕으로, 다음 조건에 맞는 객관식 문제 1개를 생성해주세요.

    1.  **대상 연령:** {age_group}세
    2.  **측정 능력:** {CATEGORY_MAP.get(category, category)}
    3.  **출력 형식:** 반드시 아래의 JSON 형식과 키 이름을 정확히 지켜서, JSON 코드 블록만 응답해주세요.
        - `title`: 문제의 제목. `[사건 파일 No.XXX]` 형식은 사용하지 말고, 측정 능력과 관련된 창의적인 제목을 한글로 작성.
        - `question`: 학생에게 제시될 명확한 질문. (예: "이 글의 주제로 가장 적절한 것은?")
        - `passage`: 주어진 텍스트를 그대로 사용.
        - `options`: 4개의 선택지 배열. 정답 1개와 매력적인 오답 3개를 포함. 오답 중 하나는 특히 학생들이 헷갈릴 만한 것이어야 함.
        - `answer`: 정답 선택지의 정확한 텍스트.
        - `explanation`: 정답에 대한 상세한 해설과, 가장 매력적인 오답이 왜 틀렸는지에 대한 설명.
        - `category`: "{category}" (영문 키)

    ---
    **주어진 텍스트:**
    {text}
    ---
    """
    
    response_json = call_gemini_api(prompt)

    if 'error' in response_json:
        return jsonify({"success": False, "message": f"AI 통신 오류: {response_json['error']}"}), 500

    try:
        content = response_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        json_match = re.search(r'```json\n(.*?)```', content, re.DOTALL)
        if not json_match:
            return jsonify({"success": False, "message": "AI가 유효한 JSON 형식으로 응답하지 않았습니다."}), 500
        
        question_data = json.loads(json_match.group(1))
        
        # Firestore에 저장
        if db:
            doc_ref = db.collection('questions').document()
            question_data['id'] = doc_ref.id
            doc_ref.set(question_data)
            return jsonify({"success": True, "message": "텍스트 기반 문제 생성 완료! Firestore에 저장되었습니다."})
        else:
            return jsonify({"success": False, "message": "DB 연결 실패로 문제를 저장할 수 없습니다."}), 500

    except (json.JSONDecodeError, IndexError, KeyError) as e:
        print(f"AI 응답 처리 오류: {e}")
        print(f"원본 응답: {content}")
        return jsonify({"success": False, "message": f"AI 응답 처리 중 오류 발생: {e}"}), 500


# --- 사용자 테스트 API ---
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
    
    test_structure = { "title": 2, "theme": 1, "argument": 2, "inference": 2, "pronoun": 2, "sentence_ordering": 2, "paragraph_ordering": 2, "essay": 1 }
    
    questions = []
    try:
        for category, count in test_structure.items():
            query = db.collection('questions').where('category', '==', category).stream()
            potential_questions = []
            for doc in query:
                q_data = doc.to_dict()
                q_data['id'] = doc.id
                potential_questions.append(q_data)

            num_to_select = min(count, len(potential_questions))
            if num_to_select > 0:
                selected = random.sample(potential_questions, num_to_select)
                for q in selected:
                    q['category_kr'] = CATEGORY_MAP.get(q.get('category'), '기타')
                    questions.append(q)

        random.shuffle(questions)
        return jsonify(questions[:15])
    except Exception as e:
        print(f"문제 가져오기 오류: {e}")
        return jsonify([]), 500

def generate_final_report(results):
    scores = { "정보 이해력": [], "논리 분석력": [], "단서 추론력": [], "비판적 사고력": [], "창의적 서술력": [] }
    total_time = 0
    correct_count = 0
    confident_errors = []
    lucky_guesses = []

    for r in results:
        total_time += r['time']
        score_category = SCORE_CATEGORY_MAP.get(r['question']['category'])
        
        is_correct = False
        if r['question']['type'] != 'essay':
            if r['answer'] == r['question']['answer']:
                is_correct = True
                correct_count += 1
        else: # 서술형은 글자 수로 기본 점수 부여
            if len(r['answer']) >= 100:
                is_correct = True
        
        scores[score_category].append(100 if is_correct else 0)

        if not is_correct and r['confidence'] == 'confident':
            confident_errors.append(r['question']['title'])
        if is_correct and r['confidence'] == 'guessed':
            lucky_guesses.append(r['question']['title'])

    final_scores = {}
    for category, score_list in scores.items():
        if score_list:
            final_scores[category] = sum(score_list) / len(score_list)
        else:
            final_scores[category] = 0

    # 문제 풀이 속도 계산 (평균 문항당 60초 기준)
    avg_time_per_question = total_time / len(results) if results else 0
    speed_score = min(100, (60 / avg_time_per_question) * 80) if avg_time_per_question > 0 else 0
    final_scores["문제 풀이 속도"] = speed_score
    
    # 코칭 가이드 생성
    report = "## 최종 분석 보고서
### 종합 소견
"
    if final_scores["정보 이해력"] > 80 and final_scores["논리 분석력"] > 80:
        report += "전반적으로 모든 영역에서 우수한 독해 능력을 보여주셨습니다. 특히, 지문의 핵심 정보를 빠르게 파악하는 **정보 이해력**과 글의 구조를 분석하는 **논리 분석력**이 뛰어납니다.
"
    else:
        report += "독서 능력의 좋은 기반을 갖추고 있으며, 몇 가지 영역을 보완한다면 더 크게 성장할 잠재력이 보입니다.
"
    
    report += "
### 강점 및 약점 분석
"
    strengths = [cat for cat, score in final_scores.items() if score > 80]
    weaknesses = [cat for cat, score in final_scores.items() if score < 60]

    if strengths:
        report += f"- **강점 ({', '.join(strengths)}):** {' '.join(strengths)} 영역에서 높은 점수를 기록했습니다. 이는 복잡한 정보 속에서도 핵심을 놓치지 않고, 논리적인 흐름을 잘 따라간다는 것을 의미합니다.
"
    if weaknesses:
        report += f"- **보완점 ({', '.join(weaknesses)}):** {' '.join(weaknesses)} 영역에서 개선의 여지가 보입니다. 특히 "
        if "단서 추론력" in weaknesses:
            report += "숨겨진 의미를 파악하기보다 표면적인 정보에 집중하는 경향이 있을 수 있습니다. "
        if "비판적 사고력" in weaknesses:
            report += "글쓴이의 주장을 그대로 받아들이기보다, '정말 그럴까?'라고 질문하며 읽는 연습이 필요합니다. "
    
    if confident_errors:
        report += f"
- **메타인지 분석:** 특히 '{confident_errors[0]}'와 같은 문항에서 **'자신만만한 오답'**을 선택했습니다. 이는 특정 개념을 잘못 이해하고 있을 수 있다는 중요한 신호이므로, 관련 해설을 꼼꼼히 확인하는 것이 좋습니다."
    
    report += "
### 맞춤형 코칭 가이드
"
    if "단서 추론력" in weaknesses or "비판적 사고력" in weaknesses:
        report += "앞으로는 신문 사설이나 비평문을 꾸준히 읽으며, 글쓴이의 숨은 의도나 주장의 타당성을 따져보는 **비판적 읽기** 훈련을 병행한다면, 한 단계 더 높은 수준의 독해 전문가로 성장할 수 있을 것입니다."
    else:
        report += "현재의 강점을 유지하면서, 다양한 장르의 책을 꾸준히 읽어 독서의 폭을 넓히는 것을 추천합니다. 이를 통해 어떤 유형의 글을 만나도 자신감 있게 분석할 수 있는 능력을 기를 수 있습니다."

    return final_scores, report

@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    if not db: return jsonify({"success": False, "error": "DB 연결 실패"}), 500

    data = request.get_json()
    user_info = data.get('userInfo', {})
    results = data.get('results', [])
    access_code = user_info.get('accessCode', '').upper()

    if access_code:
        try:
            db.collection('access_codes').document(access_code).update({
                'isUsed': True, 'userName': user_info.get('name')
            })
        except Exception as e:
            print(f"접근 코드 업데이트 오류: {e}")

    final_scores, final_report = generate_final_report(results)

    # Google Sheets에 저장
    if sheet:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row = [
                now, user_info.get('name'), user_info.get('age'),
                final_scores.get("정보 이해력", 0),
                final_scores.get("논리 분석력", 0),
                final_scores.get("단서 추론력", 0),
                final_scores.get("비판적 사고력", 0),
                final_scores.get("창의적 서술력", 0),
                final_scores.get("문제 풀이 속도", 0),
                final_report
            ]
            sheet.append_row(row)
        except Exception as e:
            print(f"Google Sheets 저장 오류: {e}")

    return jsonify({
        "success": True,
        "analysis": final_scores,
        "overall_comment": final_report
    })


# --- 5. 서버 실행 ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

