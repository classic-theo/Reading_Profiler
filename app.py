import os
import json
import string
import random
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, render_template, jsonify, request, session, redirect, url_for

# --- 초기 설정 ---
app = Flask(__name__, template_folder='templates')
app.secret_key = 'csi-profiler-secret-key-!@#$'
ADMIN_PASSWORD = "change_this_password" # 대표님께서 사용할 관리자 비밀번호를 여기에 설정하세요.

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
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error="비밀번호가 틀렸습니다.")
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
    return render_template('admin.html', codes=active_codes)

@app.route('/admin/generate-code', methods=['POST'])
def admin_generate_code():
    if not session.get('admin_logged_in'): return jsonify({'error': 'Unauthorized'}), 401
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    active_codes[code] = {'status': 'active', 'created_at': datetime.now().isoformat()}
    return jsonify({'access_code': code})

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin'))

# --- 사용자 페이지 ---
@app.route('/')
def home():
    return render_template('index.html')

# (이하 사용자 관련 코드는 이전과 동일)
@app.route('/validate-code', methods=['POST'])
def validate_code():
    user_code = request.get_json().get('code')
    if user_code in active_codes:
        del active_codes[user_code]
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': '유효하지 않은 코드입니다.'})
# ... (생략된 나머지 코드는 이전 버전과 동일합니다)