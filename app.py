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

# --- 3. 핵심 데이터 및 설정 ---
CATEGORY_MAP = {
    "title": "제목/주제 찾기", "theme": "제목/주제 찾기", "argument": "주장 파악",
    "inference": "의미 추론", "pronoun": "지시어 찾기", "sentence_ordering": "문장 순서 맞추기",
    "paragraph_ordering": "단락 순서 맞추기", "essay": "창의적 서술력"
}

SCORE_CATEGORY_MAP = {
    "title": "정보 이해력", "theme": "정보 이해력", "argument": "비판적 사고력",
    "inference": "단서 추론력", "pronoun": "단서 추론력",
    "sentence_ordering": "논리 분석력", "paragraph_ordering": "논리 분석력",
    "essay": "창의적 서술력"
}

# --- 4. AI 프롬프트 생성 로직 (고도화) ---
def get_detailed_prompt(category, age_group):
    # 연령대에 따른 구체적인 지시사항 정의
    if age_group == "10-13":
        level_instruction = "대한민국 초등학교 4~6학년 국어 교과서 수준의 어휘와 문장 구조를 사용해줘. '야기하다', '고찰하다' 같은 어려운 한자어는 '일으킨다', '살펴본다'처럼 쉬운 말로 풀어 써줘."
        passage_length = "최소 2개 문단, 150자 이상"
    elif age_group == "14-16":
        level_instruction = "대한민국 중학교 1~3학년 국어 교과서 수준의 어휘와 문장 구조를 사용해줘. 전문 용어는 최소화하고, 필요 시 간단한 설명을 덧붙여줘."
        passage_length = "최소 3개 문단, 250자 이상"
    else: # 17-19
        level_instruction = "대한민국 고등학교 1~3학년 수준의 어휘와 복합적인 문장 구조를 사용해도 좋아. 사회, 과학, 인문 등 다양한 분야의 배경지식을 활용해줘."
        passage_length = "최소 3개 문단, 350자 이상"

    # 문제 유형별 맞춤형 지시사항 정의
    type_instruction = ""
    if category in ["title", "theme"]:
        type_instruction = f"글의 전체 내용을 아우르는 주제나 제목을 찾도록 유도하는, {passage_length}으로 구성된 완결된 설명문을 창작해줘."
    elif category == "argument":
        type_instruction = f"필자의 주장이 명확하게 드러나는 {passage_length}의 논설문을 창작해줘. 주장을 뒷받침하는 근거도 1~2개 포함해줘."
    elif category == "inference":
        type_instruction = f"문맥 속에서 특정 단어나 문장의 숨겨진 의미를 추론해야 하는 {passage_length}의 문학적인 글(소설, 수필 등)을 창작해줘."
    elif category == "pronoun":
        type_instruction = f"밑줄 친 대명사가 가리키는 대상을 앞 문장에서 찾아야 하는, {passage_length}의 설명문을 창작해줘."
    elif category == "sentence_ordering":
        type_instruction = "논리적 순서나 시간의 흐름이 중요한 1개의 완결된 단락을 창작한 후, 그 단락을 5개의 문장으로 분해해서 순서를 뒤섞어 문제로 만들어줘."
    elif category == "paragraph_ordering":
        type_instruction = "기승전결이나 서론-본론-결론 구조가 뚜렷한 3개의 단락으로 구성된 글을 창작한 후, 단락의 순서를 뒤섞어 문제로 만들어줘."
    else: # essay
        type_instruction = "학생의 창의적인 생각이나 가치관을 엿볼 수 있는 개방적인 질문과, 그에 대한 생각을 유도하는 1~2문장의 짧은 상황을 제시해줘."


    base_prompt = f"""
너는 지금부터 '{CATEGORY_MAP[category]}' 유형의 독서력 평가 문제를 출제하는 최고의 교육 전문가야.
다음 규칙을 반드시 지켜서, JSON 형식으로 완벽한 문제 1개를 생성해줘.

[규칙]
1. 대상 연령: {age_group}세
2. 언어 및 난이도: {level_instruction}
3. 지문 및 문제 구성: {type_instruction}
4. 객관식 보기:
   - 반드시 4개의 보기(options)를 만들어줘.
   - 정답(answer)은 명확해야 해.
   - 정답 외에, 학생들이 가장 헷갈릴 만한 '매력적인 오답'을 반드시 1개 포함하고, 왜 그것이 오답인지에 대한 간단한 해설(distractor_explanation)을 함께 생성해줘.
5. 질문(question): 지문을 읽고 풀어야 할 명확한 질문을 1개 생성해줘.
6. JSON 형식 준수: 아래의 키(key)를 모두 포함하고, 값(value)은 모두 문자열(string)로 작성해줘.
   - "title": "[사건 파일 No.XXX] - {CATEGORY_MAP[category]}" (XXX는 임의의 세자리 숫자)
   - "passage": "생성된 지문"
   - "question": "생성된 질문"
   - "options": ["보기1", "보기2", "보기3", "보기4"] (리스트 형식)
   - "answer": "정답 보기"
   - "distractor_explanation": "매력적인 오답에 대한 해설"
   - "category": "{category}"
   - "targetAge": "{age_group}"
"""
    return base_prompt

# --- 5. 라우팅 (API 엔드포인트) ---
# (이하 코드는 이전과 동일)
@app.route('/')
def serve_index(): return render_template('index.html')

@app.route('/admin')
def serve_admin(): return render_template('admin.html')

@app.route('/api/generate-question', methods=['POST'])
def generate_question_from_ai():
    # ... (AI 호출 로직은 get_detailed_prompt를 사용하도록 수정)
    return jsonify({"success": True, "message": "AI 문제 생성 완료"})





