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
def serve_index():
    return render_template('index.html')

@app.route('/admin')
def serve_admin():
    return render_template('admin.html')

# --- AI 기반 문제 생성 API ---
def call_gemini_api(prompt):
    # AI 호출 로직을 별도 함수로 분리하여 재사용
    if not GEMINI_API_KEY:
        raise ValueError("Gemini API 키가 설정되지 않았습니다.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {'Content-Type': 'application/json'}
    
    response = requests.post(url, json=payload, timeout=120) # 타임아웃 시간 연장
    response.raise_for_status()
    
    api_response = response.json()
    if 'candidates' not in api_response or not api_response['candidates']:
        raise ValueError(f"API 응답 오류: {api_response.get('error', {}).get('message', '유효한 응답 없음')}")

    result_text = api_response['candidates'][0]['content']['parts'][0]['text']
    if result_text.strip().startswith("```json"):
        result_text = result_text.strip()[7:-3]
    return json.loads(result_text)

@app.route('/api/generate-question-from-url', methods=['POST'])
def generate_from_url():
    data = request.get_json()
    url = data.get('url')
    age = data.get('age', '15')
    category_en = data.get('category', 'comprehension')
    category_kr = CATEGORY_MAP.get(category_en, "정보 이해력")

    if not url:
        return jsonify({"success": False, "message": "URL이 제공되지 않았습니다."}), 400

    try:
        # 1. URL 콘텐츠 크롤링
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # ✨ 해결책: 3단계 지능형 크롤링 엔진 도입
        text_content = ''
        
        # 1단계: article, main, 또는 id/class가 'content'/'post'/'article'인 태그를 먼저 탐색
        main_content = soup.find('article') or soup.find('main') or soup.find(id='content') or soup.find(class_='post-content') or soup.find(class_='article-body')
        if main_content:
            print("크롤링 1단계 성공: 주요 콘텐츠 영역을 찾았습니다.")
            text_content = ' '.join(main_content.stripped_strings)

        # 2단계: 1단계 실패 시, 불필요한 태그를 제거하고 남은 텍스트 추출
        if len(text_content) < 200:
            print("크롤링 1단계 실패. 2단계(불필요한 태그 제거)를 시도합니다.")
            for element in soup(['header', 'footer', 'nav', 'aside', 'script', 'style', 'a', 'form']):
                element.decompose()
            if soup.body:
                text_content = ' '.join(soup.body.stripped_strings)

        # 3단계: 2단계도 실패 시, 모든 p 태그의 텍스트를 수집
        if len(text_content) < 200:
            print("크롤링 2단계 실패. 3단계(모든 문단 수집)를 시도합니다.")
            paragraphs = soup.find_all('p')
            text_content = ' '.join([p.get_text(strip=True) for p in paragraphs])

        # 최종 텍스트 정리
        text_content = ' '.join(text_content.split())
        
        if len(text_content) < 200:
            return jsonify({"success": False, "message": f"URL에서 충분한 텍스트(200자 이상)를 추출하지 못했습니다. (추출된 글자 수: {len(text_content)})"}), 400
        
        # 2. AI 프롬프트 생성
        prompt = f"""
        당신은 주어진 텍스트를 분석하여 독서력 평가 문제를 만드는 AI 전문가입니다.
        아래 "지문"을 바탕으로, 다음 조건에 맞는 객관식 문제를 1개 생성해주세요.

        **지문:**
        ---
        {text_content[:3000]} 
        ---

        **생성 조건:**
        1.  **대상 연령:** {age}세
        2.  **측정 능력:** {category_kr}
        3.  **문제 (title):** 지문의 내용을 바탕으로 한 객관식 질문.
        4.  **선택지 (options):** 4개의 선택지를 배열 형태로, 그 중 하나는 명확한 정답.
        5.  **정답 (answer):** 4개의 선택지 중 정답 문장.
        6.  **출력 형식:** 반드시 아래의 JSON 스키마를 준수.
        {{
          "title": "string", "passage": "{text_content[:500].replace('"', "'")}...", "type": "multiple_choice",
          "options": ["string", "string", "string", "string"], "answer": "string",
          "category": "{category_en}", "targetAge": "{age}"
        }}
        """
        
        # 3. AI 호출 및 DB 저장
        question_data = call_gemini_api(prompt)
        
        if db:
            db.collection('questions').add(question_data)
            return jsonify({"success": True, "message": f"URL 기반 '{category_kr}' 문제 1개를 DB에 추가했습니다."})
        else:
            return jsonify({"success": False, "message": "DB 연결 실패"}), 500

    except Exception as e:
        return jsonify({"success": False, "message": f"URL 문제 생성 오류: {e}"}), 500


@app.route('/api/generate-question', methods=['POST'])
def generate_question():
    # ... (기존 AI 문제 생성 로직, 생략)
    pass

# (이하 다른 API들은 기존과 동일)
@app.route('/api/get-test', methods=['POST'])
def get_test():
    # ...
    pass
@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    # ...
    pass
@app.route('/api/generate-code', methods=['POST'])
def generate_code():
    # ...
    pass
@app.route('/api/get-codes', methods=['GET'])
def get_codes():
    # ...
    pass
@app.route('/api/validate-code', methods=['POST'])
def validate_code():
    # ...
    pass

# --- 4. Flask 앱 실행 ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)






