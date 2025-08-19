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
# bs4는 더 이상 사용하지 않으므로 삭제해도 됩니다.

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
    # ... (기존과 동일, 생략)
except Exception as e:
    print(f"Firebase 초기화 실패: {e}")

# Google Sheets 초기화
try:
    # ... (기존과 동일, 생략)
except Exception as e:
    print(f"Google Sheets 초기화 실패: {e}")


# --- 3. 라우팅 (API 엔드포인트) ---

@app.route('/')
def serve_index(): return render_template('index.html')

@app.route('/admin')
def serve_admin(): return render_template('admin.html')

# --- AI 기반 문제 생성 API ---
def call_gemini_api(prompt):
    # ... (기존과 동일, 생략)
    pass

# ✨ 해결책: URL 기반 -> 텍스트 기반 문제 생성 기능으로 변경
@app.route('/api/generate-question-from-text', methods=['POST'])
def generate_from_text():
    data = request.get_json()
    text_content = data.get('text')
    age = data.get('age', '15')
    category_en = data.get('category', 'comprehension')
    category_kr = CATEGORY_MAP.get(category_en, "정보 이해력")

    if not text_content or len(text_content) < 100:
        return jsonify({"success": False, "message": "100자 이상의 텍스트를 입력해주세요."}), 400

    try:
        prompt = f"""
        당신은 주어진 텍스트를 분석하여 독서력 평가 문제를 만드는 AI 전문가입니다.
        아래 "지문"을 바탕으로, 다음 조건에 맞는 객관식 문제를 1개 생성해주세요.

        **지문:**
        ---
        {text_content[:4000]} 
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
        
        question_data = call_gemini_api(prompt)
        
        if db:
            db.collection('questions').add(question_data)
            return jsonify({"success": True, "message": f"텍스트 기반 '{category_kr}' 문제 1개를 DB에 추가했습니다."})
        else:
            return jsonify({"success": False, "message": "DB 연결 실패"}), 500

    except Exception as e:
        return jsonify({"success": False, "message": f"텍스트 기반 문제 생성 오류: {e}"}), 500


@app.route('/api/generate-question', methods=['POST'])
def generate_question():
    # ... (기존 AI 문제 생성 로직, 생략)
    pass

# (이하 다른 API들은 기존과 동일)
# ...

# --- 4. Flask 앱 실행 ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)







