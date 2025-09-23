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
    "title": "제목 찾기",
    "theme": "주제 찾기",
    "paragraph_ordering": "단락 순서 맞추기",
    "sentence_ordering": "문장 순서 맞추기",
    "pronoun": "대명사 찾기",
    "inference": "의미 추론",
    "argument": "주장 파악"
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
        return jsonify([]), 500

@app.route('/api/generate-question', methods=['POST'])
def generate_question_from_ai():
    # ... AI 문제 생성 로직 (생략) ...
    return jsonify({"success": True, "message": "AI 문제 생성 완료"})

@app.route('/api/generate-question-from-text', methods=['POST'])
def generate_question_from_text():
    # ... 텍스트 기반 문제 생성 로직 (생략) ...
     return jsonify({"success": True, "message": "텍스트 기반 문제 생성 완료"})

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
    
    # 고정된 시험 구조 정의
    test_structure = {
        "title": 2, "theme": 2, "argument": 2, # 정보 이해력 (6)
        "inference": 2, "pronoun": 2,          # 추론 능력 (4)
        "sentence_ordering": 2, "paragraph_ordering": 2, # 논리 분석력 (4)
        "essay": 1                             # 창의적 서술력 (1)
    }
    
    questions = []
    try:
        for category, count in test_structure.items():
            query = db.collection('questions').where('category', '==', category).limit(count * 5).stream()
            
            # Firestore에서 가져온 문서를 리스트로 변환 (랜덤 선택을 위해)
            potential_questions = [doc.to_dict() for doc in query]
            
            # 필요한 수만큼 랜덤으로 선택 (만약 문제가 부족하면 있는 만큼만)
            num_to_select = min(count, len(potential_questions))
            selected = random.sample(potential_questions, num_to_select)
            
            # 카테고리명을 한글로 변환하여 추가
            for q in selected:
                q['category_kr'] = CATEGORY_MAP.get(q.get('category'), '기타')
                questions.append(q)

        random.shuffle(questions) # 전체 문제 순서 섞기
        return jsonify(questions[:15]) # 최종 15문제 반환
    except Exception as e:
        print(f"문제 가져오기 오류: {e}")
        return jsonify([]), 500

@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    # ... 상세 결과 분석 및 저장 로직 (생략) ...
    return jsonify({
        "success": True,
        "analysis": {
            "comprehension": random.randint(70, 100),
            "logic": random.randint(60, 90),
            "inference": random.randint(50, 80),
            "creativity": random.randint(70, 95),
            "critical_thinking": random.randint(65, 85),
            "speed": random.randint(70, 100)
        },
        "overall_comment": "## 최종 분석 보고서
### 종합 소견
전반적으로 모든 영역에서 우수한 독해 능력을 보여주셨습니다. 특히, 지문의 핵심 정보를 빠르게 파악하는 **정보 이해력**이 뛰어납니다. 

### 강점 및 약점 분석
- **강점 (정보 이해력):** 2번, 5번 문항에서 보여주셨듯이, 복잡한 정보 속에서도 주제와 제목을 정확히 찾아내는 능력이 탁월합니다.
- **보완점 (추론 능력):** 8번 문항에서 매력적인 오답을 고르셨습니다. 이는 숨겨진 의미를 파악하기보다 표면적인 정보에 집중하는 경향이 있음을 시사합니다. 다양한 글을 읽으며 '그래서 작가가 하고 싶은 진짜 말은 뭘까?'를 고민하는 연습을 추천합니다.

### 맞춤형 코칭 가이드
앞으로는 신문 사설이나 비평문을 꾸준히 읽으며, 글쓴이의 숨은 의도나 주장의 타당성을 따져보는 **비판적 읽기** 훈련을 병행한다면, 한 단계 더 높은 수준의 독해 전문가로 성장할 수 있을 것입니다."
    })


# --- 5. 서버 실행 ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
