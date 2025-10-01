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
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

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

# --- 4. AI 동적 리포트 생성 함수 (신규) ---
def generate_dynamic_report_from_ai(user_name, scores, metacognition):
    if not GEMINI_API_KEY:
        return "AI 리포트 생성에 실패했습니다. (API 키 부재)"

    try:
        # AI에게 전달할 학생 데이터 요약
        strongest_score = 0
        strongest_category = "없음"
        weakest_score = 100
        weakest_category = "없음"
        for category, score in scores.items():
            if category != "문제 풀이 속도":
                if score > strongest_score:
                    strongest_score = score
                    strongest_category = category
                if score < weakest_score:
                    weakest_score = score
                    weakest_category = category
        
        student_data_summary = f"""
        - 학생 이름: {user_name}
        - 가장 뛰어난 능력: {strongest_category} ({strongest_score:.0f}점)
        - 가장 보완이 필요한 능력: {weakest_category} ({weakest_score:.0f}점)
        - 메타인지 분석: '자신만만하게 정답을 맞힌 문항' {metacognition['confident_correct']}개, '자신만만하게 틀린 문항(개념 오적용)' {metacognition['confident_error']}개.
        """

        # AI를 위한 상세 지시서 (프롬프트)
        prompt = f"""
        당신은 학생의 독서력 테스트 결과를 분석하고, 따뜻하고 격려하는 어조로 맞춤형 종합 소견을 작성하는 최고의 교육 컨설턴트입니다.
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
        
        headers = {'Content-Type': 'application/json'}
        data = {'contents': [{'parts': [{'text': prompt}]}]}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
        
        response = requests.post(url, headers=headers, data=json.dumps(data), timeout=60)
        response.raise_for_status()
        
        result = response.json()
        
        if 'candidates' in result and result['candidates'][0]['content']['parts'][0]['text']:
            return result['candidates'][0]['content']['parts'][0]['text']
        else:
            # AI가 안전 등의 이유로 답변을 거부했을 경우
            print(f"Gemini API 응답 형식 오류: {result}")
            return "AI가 종합 소견을 생성하는 데 실패했습니다. 일반 리포트를 표시합니다."

    except requests.exceptions.RequestException as e:
        print(f"Gemini API 네트워크 오류: {e}")
        return "AI 서버와 통신 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
    except Exception as e:
        print(f"AI 리포트 생성 중 알 수 없는 오류: {e}")
        return "AI 리포트를 생성하는 중 예상치 못한 오류가 발생했습니다."


# --- 5. 최종 분석 보고서 생성 로직 ---
def generate_final_report(user_name, results):
    # (능력치 점수 및 메타인지 계산 로직은 이전과 동일)
    scores = { "정보 이해력": [], "논리 분석력": [], "단서 추론력": [], "비판적 사고력": [], "창의적 서술력": [] }
    metacognition = {"confident_correct": 0, "confident_error": 0, "unsure_correct": 0, "unsure_error": 0}
    
    for r in results:
        # ... (채점 및 메타인지 집계) ...

    final_scores = {cat: (sum(s) / len(s)) if s else 0 for cat, s in scores.items()}
    final_scores["문제 풀이 속도"] = random.randint(60, 90) # 임시

    # AI를 호출하여 동적 리포트 생성 (핵심 변경 사항)
    final_report_text = generate_dynamic_report_from_ai(user_name, final_scores, metacognition)

    # (추천 활동 생성 로직은 이전과 동일)
    recommendations = []
    # ...

    return final_scores, metacognition, final_report_text, recommendations


@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    data = request.get_json()
    user_info = data.get('userInfo', {})
    results = data.get('results', [])
    
    # ... (DB 및 Sheet 저장 로직) ...

    final_scores, metacognition, final_report, recommendations = generate_final_report(user_info.get('name'), results)
    
    return jsonify({
        "success": True,
        "analysis": final_scores,
        "metacognition": metacognition,
        "overall_comment": final_report,
        "recommendations": recommendations
    })

# (이하 다른 모든 API 함수 및 서버 실행 코드는 이전 최종본과 동일)
@app.route('/')
def serve_index(): return render_template('index.html')

@app.route('/admin')
def serve_admin(): return render_template('admin.html')















