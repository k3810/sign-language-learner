import os
import sys
import shutil
import cv2
import random
import time
import threading
import json
import queue  
import traceback
import unicodedata
import subprocess
from collections import deque
import numpy as np
import mediapipe as mp
import requests
import base64

try:
    import speech_recognition as sr
    SR_READY = True
except ImportError:
    SR_READY = False

os.environ["FONTCONFIG_PATH"] = "/etc/fonts"
os.environ["FONTCONFIG_FILE"] = "/etc/fonts/fonts.conf"
os.environ["XDG_DATA_DIRS"] = "/usr/share:/usr/local/share"
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
os.environ["QT_QPA_PLATFORM"] = "xcb"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["GLOG_minloglevel"] = "2"

def t_log(category, message):
    current_time = time.strftime('%H:%M:%S')
    print(f"[{current_time}] [{category}] {message}", flush=True)

try:
    from PIL import Image as PILImage
    PILLOW_READY = True
except ImportError:
    PILLOW_READY = False

try:
    from gtts import gTTS
    TTS_READY = True
except ImportError:
    TTS_READY = False

mp_holistic = mp.solutions.holistic

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QTabWidget, QLabel, 
                             QListWidget, QProgressBar, QStackedWidget, QSizePolicy, QDialog, QGridLayout, QMessageBox, QTextEdit, QLineEdit, QMenu, QAction)
from PyQt5.QtCore import Qt, QUrl, QTimer, QProcess
from PyQt5.QtGui import QPixmap, QImage, QFontDatabase, QFont

def assemble_hangul(jamos):
    CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
    JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
    JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
    COMPLEX_JUNG = {'ㅗㅏ': 'ㅘ', 'ㅗㅐ': 'ㅙ', 'ㅗㅣ': 'ㅚ', 'ㅜㅓ': 'ㅝ', 'ㅜㅔ': 'ㅞ', 'ㅜㅣ': 'ㅟ', 'ㅡㅣ': 'ㅢ'}
    COMPLEX_JONG = {'ㄱㅅ': 'ㄳ', 'ㄴㅈ': 'ㄵ', 'ㄴㅎ': 'ㄶ', 'ㄹㄱ': 'ㄺ', 'ㄹㅁ': 'ㄻ', 'ㄹㅂ': 'ㄽ', 'ㄹㅌ': 'ㄾ', 'ㄹㅍ': 'ㄿ', 'ㄹㅎ': 'ㅀ', 'ㅂㅅ': 'ㅄ'}
    result = ""
    state, cho_idx, jung_idx, jong_idx = 0, -1, -1, 0
    def flush():
        nonlocal result, cho_idx, jung_idx, jong_idx, state
        if state == 1: result += CHO[cho_idx]
        elif state in [2, 3]: result += chr(0xAC00 + (cho_idx * 21 * 28) + (jung_idx * 28) + jong_idx)
        cho_idx, jung_idx, jong_idx, state = -1, -1, 0, 0
    i = 0
    while i < len(jamos):
        j = jamos[i]
        if j == " ":
            flush()
            result += " "
            i += 1
            continue
        is_cho, is_jung = j in CHO, j in JUNG
        if state == 0:
            if is_cho: cho_idx, state = CHO.index(j), 1
            else: result += j
        elif state == 1:
            if is_jung: jung_idx, state = JUNG.index(j), 2
            elif is_cho: flush(); cho_idx, state = CHO.index(j), 1
            else: flush(); result += j
        elif state == 2:
            if is_jung:
                combined = JUNG[jung_idx] + j
                if combined in COMPLEX_JUNG: jung_idx = JUNG.index(COMPLEX_JUNG[combined])
                else: flush(); result += j
            elif is_cho:
                if j in JONG:
                    if i + 1 < len(jamos) and jamos[i+1] in JUNG: flush(); cho_idx, state = CHO.index(j), 1
                    else: jong_idx, state = JONG.index(j), 3
                else: flush(); cho_idx, state = CHO.index(j), 1
            else: flush(); result += j
        elif state == 3:
            if is_cho:
                combined = JONG[jong_idx] + j
                if combined in COMPLEX_JONG:
                    if i + 1 < len(jamos) and jamos[i+1] in JUNG: flush(); cho_idx, state = CHO.index(j), 1
                    else: jong_idx = JONG.index(COMPLEX_JONG[combined])
                else: flush(); cho_idx, state = CHO.index(j), 1
            elif is_jung:
                prev_jong = JONG[jong_idx]
                jong_chars = next((k for k, v in COMPLEX_JONG.items() if v == prev_jong), None)
                if jong_chars: jong_idx, cho_idx = JONG.index(jong_chars[0]), CHO.index(jong_chars[1])
                else: jong_idx, cho_idx = 0, CHO.index(prev_jong)
                flush()
                jung_idx, state = JUNG.index(j), 2
            else: flush(); result += j
        i += 1
    flush()
    return result

class VirtualHangulKeyboard(QWidget):
    def __init__(self, target_input):
        super().__init__()
        self.target = target_input
        self.buffer, self.is_shift = [], False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)
        self.keys_normal = [['ㅂ', 'ㅈ', 'ㄷ', 'ㄱ', 'ㅅ', 'ㅛ', 'ㅕ', 'ㅑ', 'ㅐ', 'ㅔ'],['ㅁ', 'ㄴ', 'ㅇ', 'ㄹ', 'ㅎ', 'ㅗ', 'ㅓ', 'ㅏ', 'ㅣ'],['Shift', 'ㅋ', 'ㅌ', 'ㅊ', 'ㅍ', 'ㅠ', 'ㅜ', 'ㅡ', '지우기']]
        self.keys_shift = [['ㅃ', 'ㅉ', 'ㄸ', 'ㄲ', 'ㅆ', 'ㅛ', 'ㅕ', 'ㅑ', 'ㅒ', 'ㅖ'],['ㅁ', 'ㄴ', 'ㅇ', 'ㄹ', 'ㅎ', 'ㅗ', 'ㅓ', 'ㅏ', 'ㅣ'],['Shift', 'ㅋ', 'ㅌ', 'ㅊ', 'ㅍ', 'ㅠ', 'ㅜ', 'ㅡ', '지우기']]
        self.buttons = []
        for r_idx, row in enumerate(self.keys_normal):
            r_layout = QHBoxLayout(); r_layout.setSpacing(5); row_btns = []
            for c_idx, key in enumerate(row):
                btn = QPushButton(key)
                btn.setFixedHeight(45)
                btn.setFocusPolicy(Qt.NoFocus) 
                btn.setStyleSheet("background-color: #555; color: white; font-size: 18px; font-weight: bold; border-radius: 5px;")
                btn.clicked.connect(lambda checked, r=r_idx, c=c_idx: self.on_key(r, c))
                r_layout.addWidget(btn); row_btns.append(btn)
            self.layout.addLayout(r_layout); self.buttons.append(row_btns)
            
        bottom_layout = QHBoxLayout()
        for text, act, flex in [("전체 지우기", "Clear", 1), ("띄어쓰기", " ", 3)]:
            btn = QPushButton(text)
            btn.setFixedHeight(40)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setStyleSheet(f"background-color: {'#f44336' if text=='전체 지우기' else '#666'}; color: white; font-size: 18px; font-weight: bold; border-radius: 5px;")
            btn.clicked.connect(lambda checked, a=act: self.on_key_str(a))
            bottom_layout.addWidget(btn, flex)
        self.layout.addLayout(bottom_layout)

    def on_key(self, r, c):
        key = self.keys_shift[r][c] if self.is_shift else self.keys_normal[r][c]
        if key == 'Shift': self.is_shift = not self.is_shift; self.update_ui()
        elif key == '지우기':
            if self.buffer: self.buffer.pop(); self.update_target()
        else:
            self.buffer.append(key)
            if self.is_shift: self.is_shift = False; self.update_ui()
            self.update_target()
            
    def on_key_str(self, action):
        if action == "Clear": self.buffer.clear()
        elif action == "Backspace": 
            if self.buffer: self.buffer.pop()
        else: self.buffer.append(action)
        self.update_target()

    def update_ui(self):
        keys = self.keys_shift if self.is_shift else self.keys_normal
        for r in range(3):
            for c in range(len(keys[r])):
                self.buttons[r][c].setText(keys[r][c])
                if keys[r][c] == 'Shift':
                    self.buttons[r][c].setStyleSheet(f"background-color: {'#2196F3' if self.is_shift else '#555'}; color: white; font-size: 18px; font-weight: bold; border-radius: 5px;")

    def update_target(self):
        new_text = assemble_hangul(self.buffer)
        self.target.setText(new_text)
        self.target.setFocus()
        self.target.setCursorPosition(len(new_text))

class HangulLineEdit(QLineEdit):
    def __init__(self, kbd_ref, enter_callback=None):
        super().__init__()
        self.kbd_ref = kbd_ref
        self.enter_callback = enter_callback
        self.eng_to_kor = {'q':'ㅂ', 'w':'ㅈ', 'e':'ㄷ', 'r':'ㄱ', 't':'ㅅ', 'y':'ㅛ', 'u':'ㅕ', 'i':'ㅑ', 'o':'ㅐ', 'p':'ㅔ', 'a':'ㅁ', 's':'ㄴ', 'd':'ㅇ', 'f':'ㄹ', 'g':'ㅎ', 'h':'ㅗ', 'j':'ㅓ', 'k':'ㅏ', 'l':'ㅣ', 'z':'ㅋ', 'x':'ㅌ', 'c':'ㅊ', 'v':'ㅍ', 'b':'ㅠ', 'n':'ㅜ', 'm':'ㅡ', 'Q':'ㅃ', 'W':'ㅉ', 'E':'ㄸ', 'R':'ㄲ', 'T':'ㅆ', 'O':'ㅒ', 'P':'ㅖ'}
    def mousePressEvent(self, event):
        self.kbd_ref.show()
        self.setFocus()
        super().mousePressEvent(event)
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            if self.enter_callback: self.enter_callback()
        else:
            key = event.text()
            if key in self.eng_to_kor: self.kbd_ref.on_key_str(self.eng_to_kor[key])
            elif event.key() == Qt.Key_Backspace: self.kbd_ref.on_key_str("Backspace")
            elif event.key() == Qt.Key_Space: self.kbd_ref.on_key_str(" ")
            else: super().keyPressEvent(event)

class LocalHailoVLM:
    def __init__(self):
        self.model_loaded = True
        self.api_url = "http://127.0.0.1:5000/generate"
        
    def generate_advanced(self, request_type, target_word="", correct_description="", dtw_semantic="", dtw_score=0, image=None, prompt_text=""):
        payload = {
            'request_type': request_type,
            'target_word': target_word,
            'correct_description': correct_description,
            'dtw_semantic_analysis': dtw_semantic,
            'dtw_score': dtw_score,
            'prompt': prompt_text
        }
        
        if image is not None and request_type == "practice":
            img_np = np.array(image)
            frame_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR) if img_np.shape[-1] == 3 else img_np
            height, width = frame_bgr.shape[:2]
            if width > 1000: frame_bgr = cv2.resize(frame_bgr, (width // 3, height // 3), interpolation=cv2.INTER_AREA)
            _, buffer = cv2.imencode('.jpg', frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            payload['image'] = base64.b64encode(buffer).decode('utf-8')
            
        try:
            response = requests.post(self.api_url, json=payload, timeout=150)
            if response.status_code == 200: return response.json().get('result', '')
            else: return f"[서버 에러] {response.json().get('error', '알 수 없는 에러')}"
        except Exception as e: return "[통신 에러] 서버 응답 지연."

local_vlm_model = LocalHailoVLM()
VLM_READY = local_vlm_model.model_loaded

def get_chosung(text):
    chosung_list = ['ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']
    result = ""
    for char in text:
        if '가' <= char <= '힣': result += chosung_list[(ord(char) - 0xAC00) // 588]
        else: result += char
    return result

class QuizResultDialog(QDialog):
    def __init__(self, correct_count, total_count, parent=None):
        super().__init__(parent)
        self.setWindowTitle("퀴즈 결과 분석")
        self.setFixedSize(500, 350)
        self.setStyleSheet("background-color: #2b2b2b; border-radius: 15px;")
        layout = QVBoxLayout()
        lbl_title = QLabel("최종 성적표")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("color: #ffb74d; font-size: 32px; font-weight: bold; margin-top: 10px;")
        
        score_percent = int((correct_count / total_count) * 100) if total_count > 0 else 0
        lbl_score = QLabel(f"{score_percent} 점" if total_count != float('inf') else f"{correct_count}문제 연속 성공!")
        lbl_score.setAlignment(Qt.AlignCenter)
        
        if total_count == float('inf'): color, msg = "#FFD700", "서바이벌 종료! 대단한 집중력입니다!"
        else:
            if score_percent >= 80: color, msg = "#4CAF50", "최고의 실력입니다! 완벽해요!"
            elif score_percent >= 40: color, msg = "#FFD700", "조금만 더 연습하면 완벽해질 거예요!"
            else: color, msg = "#f44336", "학습 모드에서 다시 연습해 봅시다!"
            
        lbl_score.setStyleSheet(f"color: {color}; font-size: 70px; font-weight: bold; margin: 10px 0px;")
        lbl_detail = QLabel(f"총 {total_count if total_count != float('inf') else '무한'}문제 중 {correct_count}문제를 통과했습니다.\n\n{msg}")
        lbl_detail.setAlignment(Qt.AlignCenter)
        lbl_detail.setStyleSheet("color: white; font-size: 20px;")
        
        btn_close = QPushButton("확인 및 닫기")
        btn_close.setStyleSheet("background-color: #008CBA; color: white; font-size: 20px; font-weight: bold; padding: 15px; border-radius: 10px;")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(lbl_title); layout.addWidget(lbl_score); layout.addWidget(lbl_detail); layout.addWidget(btn_close)
        self.setLayout(layout)

class SignLanguageApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI 수어 번역 어시스턴트 플랫폼")
        self.resize(1024, 600)
        self.showFullScreen()
        
        self.holistic = mp_holistic.Holistic(min_detection_confidence=0.5, min_tracking_confidence=0.5)
        self.mp_drawing = mp.solutions.drawing_utils
        self.base_path = "/home/a/Sign_Kiosk/media/수어 영상 mp4"
        self.default_expert_img_path = "/home/a/Sign_Kiosk/media/전문가 시연 이미지.png"
        self.json_model_path = "/home/a/Sign_Kiosk/dynamic_sign_model.json"
        
        self.json_desc_path = "/home/a/Sign_Kiosk/dynamic_sign_desc.json"
        
        self.app_started = False  
        self.initial_load = True
        self.is_recording = False
        self.is_counting_down = False
        self.countdown_start_time = 0
        self.record_start_time = 0
        self.analysis_mode = ""
        self.current_target_word = ""
        self.vision_buffer = [] 
        self.video_loop_count = 0 
        self.audio_process = None
        self.latest_raw_frame = None 
        
        self.all_chat_sessions = []
        self.current_chat_history = []
        self.current_session_idx = -1
        self.is_gigong_camera_active = False
        
        self.is_mic_listening = False
        self.is_ai_thinking = False

        self.quiz_type = ""
        self.quiz_current_q = 0
        self.quiz_correct_count = 0
        self.quiz_target_word = ""
        
        self.is_processing_frame = False
        self.pose_buffer = deque(maxlen=100)
        self.frame_count = 0
        self.ui_queue = queue.Queue()
        
        self.video_cap = None
        self.video_timer = QTimer()
        self.video_timer.timeout.connect(self.update_video_frame)
        self.video_start_time = 0
        self.video_fps = 30
        
        self.word_data = {
            "감사합니다": "손끝이 밖으로 향하게 펴서 모로 세운 오른손의 4지 옆면을 손바닥이 아래로 향하게 편 왼 손등에 두 번 댄다.",
            "괜찮다": "오른 주먹의 4지를 펴서 끝 바닥을 턱에 가볍게 두 번 댄다.",
            "안녕하세요": "오른 손바닥으로 주먹을 쥔 왼 팔을 쓸어내린 다음, 두 주먹을 쥐고 바닥이 아래로 향하게하여 가슴 앞에서 아래로 내린다.",
            "못생기다": "얼굴 앞에서 오므렸던 오른손을 얼굴 쪽으로 끌어들이며 편다.",
            "미안합니다": "오른손의 1·5지 끝을 맞대어 동그라미를 만들어 이마에 댔다가 1·5지를 펴며 내린다.",
            "사랑합니다": "5지 바닥을 1지 옆면에 대고 손등이 왼쪽으로 향하게 모로 세운 왼 주먹 위에 오른 손바닥을 대고 오른손만 오른쪽으로 돌린다.",
            "정말로": "5지를 접고 나머지 손가락을 펴서 손바닥이 왼쪽으로 향하게 세운 오른손의 1지 옆면을 턱 중앙에 댄다.",
            "기다리다": "오른손을 ‘ㄱ’자 모양으로 구부려 끝이 약간 안으로 향하게 하여 손가락 등을 턱 밑에 댄다.",
            "좋다": "오른 주먹을 코에 1·5지 옆면이 닿게 댄다.",
            "만나다": "두 주먹의 1지를 펴서 마주 세웠다가 중앙으로 모아 마주 댄다.",
            "아니다": "두 주먹의 1·5지를 펴서 끝이 마주 보게 하였다가 손목을 양옆으로 돌린다."
        }
        
        self.load_dynamic_descriptions()

        self.expert_data = {}
        if os.path.exists(self.json_model_path):
            try:
                with open(self.json_model_path, 'r', encoding='utf-8') as f:
                    raw_json = json.load(f)
                    for k in raw_json.keys():
                        if k not in self.word_data: self.word_data[k] = "학습자가 새롭게 추가한 수어입니다."
            except Exception: pass
            
        self.words = list(self.word_data.keys())
        if os.path.exists(self.json_model_path):
            with open(self.json_model_path, 'r', encoding='utf-8') as f:
                raw_json = json.load(f)
                for k, v in raw_json.items():
                    res = self.resample_sequence(v, 30)
                    if res is not None: self.expert_data[k] = res.tolist()

        self.root_stack = QStackedWidget()
        self.setCentralWidget(self.root_stack)

        self.intro_widget = QWidget()
        self.intro_widget.setObjectName("IntroWidget")
        self.intro_widget.setStyleSheet("#IntroWidget { border-image: url(/usr/share/rpd-wallpaper/aurora.jpg) 0 0 0 0 stretch stretch; }")
        intro_layout = QVBoxLayout(self.intro_widget)
        
        lbl_main_title = QLabel("수어 학습기")
        lbl_main_title.setAlignment(Qt.AlignCenter)
        lbl_main_title.setStyleSheet("font-size: 80px; font-weight: bold; color: white; background-color: rgba(0,0,0,150); padding: 40px; border-radius: 15px; margin-bottom: 50px;")
        
        btn_enter = QPushButton("[ 시작하기 ]")
        btn_enter.setStyleSheet("background-color: #008CBA; color: white; font-size: 30px; font-weight: bold; padding: 25px; border-radius: 15px; margin: 10px 200px;")
        btn_enter.clicked.connect(self.enter_main_app)
        
        btn_truth_studio = QPushButton("[ 정답지 스튜디오 ]")
        btn_truth_studio.setStyleSheet("background-color: #9C27B0; color: white; font-size: 30px; font-weight: bold; padding: 25px; border-radius: 15px; margin: 10px 200px;")
        btn_truth_studio.clicked.connect(self.launch_truth_studio)
        
        btn_intro_exit = QPushButton("[ 종료하기 ]")
        btn_intro_exit.setStyleSheet("background-color: #f44336; color: white; font-size: 30px; font-weight: bold; padding: 25px; border-radius: 15px; margin: 10px 200px;")
        btn_intro_exit.clicked.connect(self.close_app)
        
        intro_layout.addStretch(); intro_layout.addWidget(lbl_main_title); intro_layout.addWidget(btn_enter); intro_layout.addWidget(btn_truth_studio); intro_layout.addWidget(btn_intro_exit); intro_layout.addStretch()

        self.main_app_widget = QWidget()
        self.main_app_widget.setStyleSheet("background-color: #1e1e1e;")
        layout = QVBoxLayout(self.main_app_widget)

        top_bar = QHBoxLayout()
        self.btn_stop_audio_global = QPushButton("⏹️ 음성 종료"); self.btn_home = QPushButton("처음으로"); self.btn_window = QPushButton("창 모드"); self.btn_fullscreen = QPushButton("전체화면"); self.btn_exit = QPushButton("종료하기")
        btn_style = "background-color: #008CBA; color: white; padding: 8px 15px; font-size: 14px; font-weight: bold; border-radius: 5px;"
        self.btn_stop_audio_global.setStyleSheet("background-color: #9C27B0; color: white; padding: 8px 15px; font-size: 14px; font-weight: bold; border-radius: 5px;")
        self.btn_home.setStyleSheet(btn_style); self.btn_window.setStyleSheet(btn_style); self.btn_fullscreen.setStyleSheet(btn_style)
        self.btn_exit.setStyleSheet("background-color: #f44336; color: white; padding: 8px 15px; font-size: 14px; font-weight: bold; border-radius: 5px;" )
        
        self.btn_stop_audio_global.clicked.connect(self.stop_tts_audio); self.btn_home.clicked.connect(self.return_to_intro); self.btn_window.clicked.connect(self.showNormal); self.btn_fullscreen.clicked.connect(self.showFullScreen); self.btn_exit.clicked.connect(self.close_app)
        top_bar.addStretch(); top_bar.addWidget(self.btn_stop_audio_global); top_bar.addWidget(self.btn_home); top_bar.addWidget(self.btn_window); top_bar.addWidget(self.btn_fullscreen); top_bar.addWidget(self.btn_exit)
        layout.addLayout(top_bar)

        self.tabs = QTabWidget(); self.tabs.setUsesScrollButtons(False)
        self.tab_learn = QWidget(); self.tab_practice = QWidget(); self.tab_test = QWidget(); self.tab_auto = QWidget(); self.tab_chat = QWidget() 
        self.tabs.addTab(self.tab_learn, "학습 모드"); self.tabs.addTab(self.tab_practice, "연습 모드"); self.tabs.addTab(self.tab_test, "확인 모드"); self.tabs.addTab(self.tab_auto, "자율 모드"); self.tabs.addTab(self.tab_chat, "AI와 대화") 
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.setup_learn_tab(); self.setup_practice_tab(); self.setup_test_tab(); self.setup_auto_tab(); self.setup_chat_tab() 
        layout.addWidget(self.tabs); self.apply_styles()
        
        self.root_stack.addWidget(self.intro_widget); self.root_stack.addWidget(self.main_app_widget); self.root_stack.setCurrentIndex(0) 

        self.cap = None
        self.timer = QTimer(); self.timer.timeout.connect(self.update_camera_frame)
        self.speed_timer = QTimer(); self.speed_timer.timeout.connect(self.update_speed_timer)
        self.speed_time_left = 50 

    def load_dynamic_descriptions(self):
        txt_path = os.path.join(self.base_path, "수형설명.txt")
        if os.path.exists(txt_path):
            try:
                with open(txt_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    for line in lines:
                        if ':' in line:
                            parts = line.split(':', 1)
                            w = parts[0].strip()
                            while w.startswith('-') or w.startswith('*'):
                                w = w[1:].strip()
                            d = parts[1].strip()
                            if w: self.word_data[w] = d
            except Exception as e:
                t_log("파일시스템", f"수형설명.txt 읽기 에러: {e}")
                
        if os.path.exists(self.base_path):
            for file in os.listdir(self.base_path):
                if file.endswith(".txt") and file != "수형설명.txt":
                    word_name = os.path.splitext(file)[0].strip()
                    try:
                        with open(os.path.join(self.base_path, file), 'r', encoding='utf-8') as f:
                            self.word_data[word_name] = f.read().strip()
                    except: pass
                    
        if os.path.exists(self.json_desc_path):
            try:
                with open(self.json_desc_path, 'r', encoding='utf-8') as f:
                    desc_data = json.load(f)
                    for k, v in desc_data.items():
                        self.word_data[k] = v
            except Exception: pass

    def init_camera(self):
        if self.cap is not None and self.cap.isOpened(): return
        for i in range(4):
            cap = cv2.VideoCapture(i, cv2.CAP_V4L2)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480); cap.set(cv2.CAP_PROP_FPS, 30)
                ret, _ = cap.read()
                if ret: self.cap = cap; break
                else: cap.release()
            else: cap.release()

    def return_to_intro(self):
        t_log("사용자조작", "'처음으로' 버튼이 클릭되었습니다.")
        self.app_started = False
        self.timer.stop(); self.speed_timer.stop()
        if hasattr(self, 'video_timer'): self.video_timer.stop()
        if getattr(self, 'video_cap', None) is not None: self.video_cap.release(); self.video_cap = None
        if self.cap and self.cap.isOpened(): self.cap.release(); self.cap = None
        self.stop_tts_audio(); self.stop_gigong_features(); self.root_stack.setCurrentIndex(0)

    def reload_dynamic_data(self):
        self.load_dynamic_descriptions()
        if os.path.exists(self.json_model_path):
            try:
                with open(self.json_model_path, 'r', encoding='utf-8') as f:
                    raw_json = json.load(f)
                    for k, v in raw_json.items():
                        if k not in self.words:
                            self.words.append(k)
                            if k not in self.word_data:
                                self.word_data[k] = "학습자가 정답지 스튜디오를 통해 새롭게 추가한 수어입니다."
                        res = self.resample_sequence(v, 30)
                        if res is not None: self.expert_data[k] = res.tolist()
                self.learn_list.blockSignals(True); self.practice_list.blockSignals(True)
                self.learn_list.clear(); self.practice_list.clear()
                self.learn_list.addItems(self.words); self.practice_list.addItems(self.words)
                self.learn_list.blockSignals(False); self.practice_list.blockSignals(False)
            except Exception: pass

    def launch_truth_studio(self):
        t_log("사용자조작", "'정답지 스튜디오'가 실행되었습니다.")
        if self.cap and self.cap.isOpened(): self.cap.release(); self.cap = None
        self.stop_tts_audio()
        self.studio_process = QProcess(self)
        self.studio_process.setProcessChannelMode(QProcess.ForwardedChannels)
        if os.path.exists("/home/a/Sign_Kiosk/run_truth_studio.sh"): self.studio_process.start('bash', ['/home/a/Sign_Kiosk/run_truth_studio.sh'])
        else: self.studio_process.start('python3', ['-u', '/home/a/Sign_Kiosk/truth_studio.py'])
        self.studio_process.finished.connect(self.on_studio_finished)

    def on_studio_finished(self):
        self.reload_dynamic_data()
        if self.app_started: self.init_camera()
        
    def close_app(self): self.close()

    def enter_main_app(self):
        t_log("사용자조작", "'시작하기' 버튼이 클릭되었습니다. 메인 앱으로 진입합니다.")
        self.init_camera()
        self.app_started = True 
        self.root_stack.setCurrentIndex(1)
        self.tabs.setCurrentIndex(0)
        self.timer.start(35)
        self.play_sound_effect("학습 모드")

    def setup_chat_tab(self):
        main_layout = QHBoxLayout()
        self.chat_left_widget = QWidget()
        left_layout = QVBoxLayout(self.chat_left_widget)
        left_layout.setContentsMargins(0,0,0,0)
        
        lbl_history = QLabel("대화 목록 (선택 후 삭제)")
        lbl_history.setStyleSheet("font-size: 20px; font-weight: bold; color: #FFD700;")
        
        self.btn_new_chat = QPushButton("➕ 새 대화 시작")
        self.btn_new_chat.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px; font-size: 16px; font-weight: bold; border-radius: 5px;")
        self.btn_new_chat.clicked.connect(self.start_new_chat_session)
        
        self.chat_session_list = QListWidget()
        self.chat_session_list.setStyleSheet("""
            QListWidget { background-color: #3a3a3a; color: white; font-size: 16px; padding: 5px; border-radius: 5px; border: none;}
            QListWidget::item { padding: 15px; border-bottom: 1px solid #555; }
            QListWidget::item:selected { background-color: #E91E63; border-radius: 5px; color: white; font-weight: bold; }
        """)
        self.chat_session_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.chat_session_list.customContextMenuRequested.connect(self.show_chat_session_context_menu)
        self.chat_session_list.itemClicked.connect(self.load_chat_session)
        
        self.btn_delete_chat = QPushButton("🗑️ 선택 대화 삭제")
        self.btn_delete_chat.setStyleSheet("background-color: #f44336; color: white; padding: 10px; font-size: 16px; font-weight: bold; border-radius: 5px;")
        self.btn_delete_chat.clicked.connect(self.delete_selected_chat_session)
        
        self.btn_hide_history = QPushButton("◀ 목록 숨기기")
        self.btn_hide_history.setStyleSheet("background-color: #555; color: white; padding: 10px; font-size: 16px; font-weight: bold; border-radius: 5px;")
        self.btn_hide_history.clicked.connect(self.toggle_chat_history_panel)
        
        left_layout.addWidget(lbl_history); left_layout.addWidget(self.btn_new_chat); left_layout.addWidget(self.chat_session_list, stretch=1); left_layout.addWidget(self.btn_delete_chat); left_layout.addWidget(self.btn_hide_history)
        
        self.chat_right_widget = QWidget()
        right_layout = QVBoxLayout(self.chat_right_widget)
        right_layout.setContentsMargins(0,0,0,0)
        
        self.btn_show_history = QPushButton("▶ 대화 목록 열기")
        self.btn_show_history.setStyleSheet("background-color: #555; color: white; padding: 10px; font-size: 16px; font-weight: bold; border-radius: 5px; margin-bottom: 5px;")
        self.btn_show_history.clicked.connect(self.toggle_chat_history_panel); self.btn_show_history.hide()
        
        self.lbl_chat_camera = QLabel("카메라를 켜면 이 곳에 모습이 보입니다.")
        self.lbl_chat_camera.setAlignment(Qt.AlignCenter)
        self.lbl_chat_camera.setStyleSheet("background-color: black; border-radius: 10px; color: grey; font-size: 20px;")
        self.lbl_chat_camera.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored); self.lbl_chat_camera.hide() 
        
        self.active_chat_display = QTextEdit()
        self.active_chat_display.setReadOnly(True)
        self.active_chat_display.setStyleSheet("background-color: #2b2b2b; color: white; font-size: 18px; padding: 15px; border-radius: 10px;")
        
        cam_chat_layout = QVBoxLayout()
        cam_chat_layout.addWidget(self.lbl_chat_camera, stretch=1); cam_chat_layout.addWidget(self.active_chat_display, stretch=1)
        
        input_layout = QHBoxLayout()
        self.chat_kbd = VirtualHangulKeyboard(None)
        
        self.chat_input = HangulLineEdit(self.chat_kbd, enter_callback=self.send_text_chat)
        # 💡 [버그 해결] 타겟 연결 복구!
        self.chat_kbd.target = self.chat_input
        self.chat_input.setPlaceholderText("터치하여 텍스트 입력 (또는 VNC 키보드, 마이크 사용)")
        self.chat_input.setFixedHeight(45); self.chat_input.setReadOnly(False) 
        self.chat_input.setStyleSheet("font-size: 18px; padding: 5px; border-radius: 5px; color: black; background-color: white;")
        self.chat_kbd.hide()
        
        self.btn_send_chat = QPushButton("전송")
        self.btn_send_chat.setFixedWidth(80); self.btn_send_chat.setFixedHeight(45)
        self.btn_send_chat.setStyleSheet("background-color: #4CAF50; color: white; font-size: 18px; font-weight: bold; border-radius: 5px;")
        self.btn_send_chat.clicked.connect(self.send_text_chat)
        
        input_layout.addWidget(self.chat_input); input_layout.addWidget(self.btn_send_chat)
        
        control_layout = QHBoxLayout()
        self.btn_gigong_mic = QPushButton("🎤 연속 듣기 켜기")
        self.btn_gigong_cam = QPushButton("📷 카메라 켜기")
        self.btn_gigong_stop = QPushButton("❌ 닫기")
        self.btn_gigong_record = QPushButton("⏺️ 동작 2초 녹화 전송")
        
        btn_ctl_style = "color: white; font-size: 20px; font-weight: bold; padding: 15px; border-radius: 10px;"
        self.btn_gigong_mic.setStyleSheet(f"background-color: #E91E63; {btn_ctl_style}")
        self.btn_gigong_cam.setStyleSheet(f"background-color: #008CBA; {btn_ctl_style}")
        self.btn_gigong_record.setStyleSheet(f"background-color: #FF9800; {btn_ctl_style}")
        self.btn_gigong_stop.setStyleSheet(f"background-color: #555555; {btn_ctl_style}")
        
        self.btn_gigong_mic.clicked.connect(self.toggle_gigong_mic)
        self.btn_gigong_cam.clicked.connect(self.toggle_gigong_cam)
        self.btn_gigong_record.clicked.connect(lambda: self.start_recording("gigong"))
        self.btn_gigong_stop.clicked.connect(self.stop_gigong_features)
        
        self.btn_gigong_record.hide()
        
        control_layout.addWidget(self.btn_gigong_mic)
        control_layout.addWidget(self.btn_gigong_cam)
        control_layout.addWidget(self.btn_gigong_record)
        control_layout.addWidget(self.btn_gigong_stop)
        
        right_layout.addWidget(self.btn_show_history); right_layout.addLayout(cam_chat_layout, stretch=1)
        right_layout.addWidget(self.chat_kbd); right_layout.addLayout(input_layout); right_layout.addLayout(control_layout)
        
        main_layout.addWidget(self.chat_left_widget, 3); main_layout.addWidget(self.chat_right_widget, 7)
        self.tab_chat.setLayout(main_layout)

    def show_chat_session_context_menu(self, pos):
        item = self.chat_session_list.itemAt(pos)
        if item is not None:
            menu = QMenu()
            delete_action = QAction("🗑️ 대화 삭제", self)
            delete_action.triggered.connect(lambda: self.delete_chat_session(item))
            menu.addAction(delete_action)
            menu.exec_(self.chat_session_list.mapToGlobal(pos))

    def delete_selected_chat_session(self):
        item = self.chat_session_list.currentItem()
        if item is not None: self.delete_chat_session(item)

    def delete_chat_session(self, item):
        row = self.chat_session_list.row(item)
        orig_idx = len(self.all_chat_sessions) - 1 - row
        del self.all_chat_sessions[orig_idx]
        self.chat_session_list.takeItem(row)
        if self.current_session_idx == orig_idx:
            self.current_chat_history = []; self.current_session_idx = -1
            self.active_chat_display.clear(); self.chat_session_list.clearSelection()
            self.append_chat_log("시스템", "대화가 삭제되었습니다. 새로운 대화를 시작합니다.")
        elif self.current_session_idx > orig_idx: self.current_session_idx -= 1
        self.refresh_session_list()

    def toggle_chat_history_panel(self):
        if self.chat_left_widget.isVisible(): self.chat_left_widget.hide(); self.btn_show_history.show()
        else: self.chat_left_widget.show(); self.btn_show_history.hide()

    def start_new_chat_session(self):
        t_log("사용자조작", "새 대화 시작 버튼 클릭됨")
        self.current_chat_history = []; self.current_session_idx = -1
        self.active_chat_display.clear(); self.chat_session_list.clearSelection()
        self.append_chat_log("시스템", "새로운 대화를 시작합니다. AI 어시스턴트에게 질문해 보세요!")

    def load_chat_session(self, item):
        row = self.chat_session_list.currentRow()
        orig_idx = len(self.all_chat_sessions) - 1 - row
        self.current_session_idx = orig_idx
        self.current_chat_history = list(self.all_chat_sessions[orig_idx]["history"])
        self.active_chat_display.clear()
        for msg in self.current_chat_history:
            color = "#4CAF50" if msg["role"] == "사용자" else "#FF9800" if msg["role"] == "🤖 AI 어시스턴트" else "#9E9E9E"
            prefix = "👤" if msg["role"] == "사용자" else "🤖" if msg["role"] == "🤖 AI 어시스턴트" else "ℹ️"
            self.active_chat_display.append(f"<b style='color:{color};'>{prefix} {msg['role']}:</b> <span style='color:white;'>{msg['content']}</span><br>")
        self.active_chat_display.verticalScrollBar().setValue(self.active_chat_display.verticalScrollBar().maximum())

    def refresh_session_list(self):
        self.chat_session_list.clear()
        for session in reversed(self.all_chat_sessions): self.chat_session_list.addItem(session["title"])
        if self.current_session_idx != -1:
            rev_idx = len(self.all_chat_sessions) - 1 - self.current_session_idx
            self.chat_session_list.setCurrentRow(rev_idx)

    def append_chat_log(self, role, text):
        self.current_chat_history.append({"role": role, "content": text})
        color = "#4CAF50" if role == "사용자" else "#FF9800" if role == "🤖 AI 어시스턴트" else "#9E9E9E"
        prefix = "👤" if role == "사용자" else "🤖" if role == "🤖 AI 어시스턴트" else "ℹ️"
        self.active_chat_display.append(f"<b style='color:{color};'>{prefix} {role}:</b> <span style='color:white;'>{text}</span><br>")
        self.active_chat_display.verticalScrollBar().setValue(self.active_chat_display.verticalScrollBar().maximum())
        
        if role == "사용자" and self.current_session_idx == -1:
            title = text[:15] + "..." if len(text) > 15 else text
            self.all_chat_sessions.append({"title": title, "history": list(self.current_chat_history)})
            self.current_session_idx = len(self.all_chat_sessions) - 1
            self.refresh_session_list()
        elif self.current_session_idx != -1:
            self.all_chat_sessions[self.current_session_idx]["history"] = list(self.current_chat_history)

    def send_text_chat(self):
        text = self.chat_input.text().strip()
        if not text: return
        t_log("사용자입력", f"텍스트 입력 전송: {text}")
        self.chat_input.clear(); self.chat_kbd.buffer.clear(); self.chat_kbd.hide()
        self.process_gigong_chat(text)

    def toggle_gigong_mic(self):
        if not SR_READY: return self.append_chat_log("시스템", "음성 인식 라이브러리가 설치되지 않았습니다.")
        
        if not self.is_mic_listening:
            self.is_mic_listening = True
            t_log("사용자조작", "연속 마이크 켜짐 - 음성 인식을 시작합니다.")
            self.btn_gigong_mic.setText("⏹️ 연속 듣기 끄기")
            self.btn_gigong_mic.setStyleSheet("background-color: #f44336; color: white; font-size: 20px; font-weight: bold; padding: 15px; border-radius: 10px;")
            self.stop_tts_audio()
            threading.Thread(target=self.continuous_mic_loop, daemon=True).start()
        else:
            self.is_mic_listening = False
            t_log("사용자조작", "연속 마이크 꺼짐")
            self.reset_gigong_mic_btn()

    def continuous_mic_loop(self):
        while self.is_mic_listening:
            if self.is_ai_thinking:
                time.sleep(0.5)
                continue
                
            recognizer = sr.Recognizer()
            try:
                with sr.Microphone() as source:
                    if source.stream is None: raise Exception("마이크 오류")
                    recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    self.ui_queue.put(("mic_status_update", "🎙️ 듣는 중... (말씀해주세요)"))
                    audio = recognizer.listen(source, timeout=2, phrase_time_limit=10)
                
                if self.is_mic_listening and not self.is_ai_thinking:
                    recognized_text = recognizer.recognize_google(audio, language='ko-KR')
                    t_log("음성인식", f"성공적으로 인식된 음성: {recognized_text}")
                    self.ui_queue.put(("gigong_mic_success", recognized_text))
                    
            except sr.WaitTimeoutError:
                pass
            except Exception:
                pass

    def process_gigong_chat(self, user_text, gigong_top3=None):
        if not user_text and not gigong_top3: return
        
        self.is_ai_thinking = True
        
        if user_text: 
            self.append_chat_log("사용자", user_text)
            
        if self.is_mic_listening:
            self.btn_gigong_mic.setText("⏳ AI 분석 중...")
            self.btn_gigong_mic.setStyleSheet("background-color: #FF9800; color: white; font-size: 20px; font-weight: bold; padding: 15px; border-radius: 10px;")
        
        if gigong_top3:
            best_match, best_score = gigong_top3[0]
            if best_match not in ["손 동작 없음", "프레임 부족", "연산 오류", "데이터 규격 불일치"] and best_score >= 20:
                dtw_semantic = f"[수어 동작 확인됨] NPU의 정밀 궤적 분석 지표 -> 1순위: '{gigong_top3[0][0]}'({gigong_top3[0][1]}점), 2순위: '{gigong_top3[1][0]}'({gigong_top3[1][1]}점), 3순위: '{gigong_top3[2][0]}'({gigong_top3[2][1]}점)."
                self.append_chat_log("사용자", f"📷 (카메라를 통해 '{best_match}' 수어 동작을 2초간 보여줌)")
                t_log("AI통신", f"NPU 판독 성공 -> 1순위: {gigong_top3[0][0]}, 2순위: {gigong_top3[1][0]}, 3순위: {gigong_top3[2][0]}")
                user_text = "(사용자가 카메라에 수어 동작을 보여주었습니다. 방금 보여준 동작에 대해 전문적으로 피드백해 주세요.)"
            else:
                best_match, best_score = "알 수 없음", 0
                dtw_semantic = "[수어 동작 없음] 동작 녹화 버튼을 눌렀으나 의미 있는 수어 궤적이 감지되지 않았습니다."
                self.append_chat_log("사용자", "📷 (카메라에 손을 보여주었으나, 동작이 정확하지 않음)")
                t_log("AI통신", "NPU 판독 실패 -> 의미 있는 동작이 감지되지 않음")
                user_text = "(제가 방금 한 동작이 잘 인식되지 않았나요? 어떻게 해야 하나요?)"
        else:
            best_match, best_score = "알 수 없음", 0
            dtw_semantic = "[일반 대화 중] 사용자가 카메라로 수어 동작을 보여주지 않고, 오직 텍스트나 음성으로만 질문했습니다. 시각 정보가 없으므로 대화 내용에만 집중해서 자연스럽게 대답하세요."
            t_log("AI통신", "시각 정보 없이 텍스트/음성 대화만 노트북으로 전송합니다.")

        def run_llm():
            try:
                feedback = local_vlm_model.generate_advanced(
                    request_type="gigong", 
                    prompt_text=user_text, 
                    image=None,
                    target_word=best_match,
                    dtw_score=best_score,
                    dtw_semantic=dtw_semantic
                )
                clean_feedback = feedback.replace("[번역 결과]", "").replace("[판단 근거]", "").replace("[상세 분석]", "").strip()
                if not clean_feedback: clean_feedback = "방금 하신 말씀을 명확히 이해하지 못했습니다. 다시 한 번 말씀해 주시겠습니까?"
                
                self.ui_queue.put(("gigong_answer", clean_feedback))
            except Exception as e:
                t_log("AI통신", f"노트북 서버 통신 에러 발생: {e}")
                self.ui_queue.put(("gigong_answer", "AI 서버와 통신 중 오류가 발생했습니다."))
                
        threading.Thread(target=run_llm, daemon=True).start()

    def toggle_gigong_cam(self):
        t_log("사용자조작", "'카메라 켜기/끄기' 토글 버튼이 클릭되었습니다.")
        if not getattr(self, 'is_gigong_camera_active', False):
            self.is_gigong_camera_active = True; self.lbl_chat_camera.show(); self.btn_gigong_record.show()
            self.lbl_chat_camera.setText("카메라 켜짐 (오른쪽 동작 녹화 버튼을 누르면 채점을 시작합니다)")
            self.btn_gigong_cam.setStyleSheet("background-color: #555555; color: white; font-size: 20px; font-weight: bold; padding: 15px; border-radius: 10px;"); self.btn_gigong_cam.setText("📷 카메라 끄기")
        else:
            self.is_gigong_camera_active = False; self.lbl_chat_camera.hide(); self.btn_gigong_record.hide()
            self.btn_gigong_cam.setStyleSheet("background-color: #008CBA; color: white; font-size: 20px; font-weight: bold; padding: 15px; border-radius: 10px;"); self.btn_gigong_cam.setText("📷 카메라 켜기")

    def stop_gigong_features(self):
        t_log("사용자조작", "'기능 닫기' 버튼이 클릭되었습니다.")
        self.is_gigong_camera_active = False
        self.is_mic_listening = False
        self.lbl_chat_camera.hide(); self.btn_gigong_record.hide(); self.chat_kbd.hide(); self.stop_tts_audio()
        self.btn_gigong_cam.setStyleSheet("background-color: #008CBA; color: white; font-size: 20px; font-weight: bold; padding: 15px; border-radius: 10px;"); self.btn_gigong_cam.setText("📷 카메라 켜기")
        self.reset_gigong_mic_btn()

    def reset_gigong_mic_btn(self):
        if hasattr(self, 'btn_gigong_mic'):
            self.is_mic_listening = False
            self.is_ai_thinking = False
            self.btn_gigong_mic.setEnabled(True)
            self.btn_gigong_mic.setText("🎤 연속 듣기 켜기")
            self.btn_gigong_mic.setStyleSheet("background-color: #E91E63; color: white; font-size: 20px; font-weight: bold; padding: 15px; border-radius: 10px;")

    def stop_tts_audio(self):
        os.system("pkill -9 -f vlc > /dev/null 2>&1")
        os.system("pkill -9 -f cvlc > /dev/null 2>&1")
        if self.audio_process is not None: self.audio_process = None

    def play_sound_effect(self, effect_name):
        self.stop_tts_audio()
        audio_dir = os.path.join(self.base_path, "오디오 파일")
        clean_name = effect_name.replace(" ", "")
        target_audio = os.path.join(audio_dir, f"{clean_name}.mp3")
        if os.path.exists(target_audio):
            self.audio_process = subprocess.Popen(['cvlc', '--play-and-exit', '--no-video', target_audio], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else: self.speak_text(effect_name)

    def play_word_audio(self, word):
        if not getattr(self, 'app_started', False): return 
        self.stop_tts_audio()
        audio_dir = os.path.join(self.base_path, "오디오 파일")
        target_audio = None
        clean_target = unicodedata.normalize('NFC', word.strip().replace(" ", ""))
        if os.path.exists(audio_dir):
            for file in os.listdir(audio_dir):
                name, ext = os.path.splitext(file)
                if clean_target == unicodedata.normalize('NFC', name.strip().replace(" ", "")) and ext.lower() == '.mp3':
                    target_audio = os.path.join(audio_dir, file); break
        if target_audio:
            self.audio_process = subprocess.Popen(['cvlc', '--play-and-exit', '--no-video', target_audio], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else: self.speak_text(word)

    def speak_text(self, text):
        if not TTS_READY: 
            self.is_ai_thinking = False 
            return
            
        self.stop_tts_audio() 
        def run_tts():
            try:
                temp_file = '/tmp/sign_chat_tts.mp3'
                safe_text = text.replace('"', '').replace("'", "").replace('\n', ' ').strip()
                EDGE_TTS_BIN = "/home/a/miniforge3/envs/hailo10_env/bin/edge-tts"
                result = subprocess.run([EDGE_TTS_BIN, '--voice', 'ko-KR-SunHiNeural', '--text', safe_text, '--write-media', temp_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if result.returncode != 0:
                    tts = gTTS(text=safe_text, lang='ko'); tts.save(temp_file)
                
                self.audio_process = subprocess.Popen(['cvlc', '--play-and-exit', '--no-video', temp_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.audio_process.wait() 
                
                self.is_ai_thinking = False
                if self.is_mic_listening:
                    self.ui_queue.put(("mic_resume", ""))
                    
            except Exception as e: 
                t_log("음성에러", f"TTS 생성 실패: {e}")
                self.is_ai_thinking = False
                
        threading.Thread(target=run_tts, daemon=True).start()

    def create_word_selection_panel(self, list_widget):
        panel = QVBoxLayout()
        lbl_category = QLabel("학습 단어 목록")
        lbl_category.setStyleSheet("font-size: 20px; font-weight: bold; color: #4CAF50;")
        list_widget.setFixedWidth(220)
        list_widget.addItems(self.words)
        list_widget.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        list_widget.itemClicked.connect(self.on_item_clicked)
        list_widget.currentRowChanged.connect(self.change_word_by_index)
        panel.addWidget(lbl_category); panel.addWidget(list_widget)
        return panel

    def on_tab_changed(self, index):
        tab_names = ["학습 모드", "연습 모드", "확인 모드", "자율 모드", "AI와 대화"]
        t_log("사용자조작", f"탭 변경: '{tab_names[index]}' 탭으로 이동했습니다.")
        self.stop_tts_audio()
        
        if index != 4: QTimer.singleShot(300, lambda: self.play_sound_effect(tab_names[index]))
            
        self.video_timer.stop()
        if getattr(self, 'video_cap', None) is not None: self.video_cap.release(); self.video_cap = None
        if hasattr(self, 'learn_video_stack'): self.learn_video_stack.setCurrentIndex(0)
        
        self.is_recording = False
        self.is_counting_down = False
        self.pose_buffer.clear()
        self.vision_buffer = []
        
        if index == 4:
            self.chat_kbd.hide()
            if getattr(self, 'current_session_idx', -1) == -1 and not getattr(self, 'current_chat_history', []): self.start_new_chat_session()
        else:
            if hasattr(self, 'stop_gigong_features'): self.stop_gigong_features()

    def on_item_clicked(self, item):
        self.initial_load = False 
        word = item.text()
        t_log("사용자조작", f"단어 선택됨: {word}")
        if self.learn_list.currentItem() and self.learn_list.currentItem().text() == word:
            if self.tabs.currentIndex() == 0: self.play_word_audio(word); self.replay_video()
        else: self.change_word(word)

    def change_word_by_index(self, index):
        if index < 0 or index >= len(self.words): return
        self.change_word(self.words[index])

    def change_word(self, word):
        self.stop_tts_audio() 
        self.current_target_word = word
        self.pose_buffer.clear()
        self.learn_list.blockSignals(True)
        if hasattr(self, 'practice_list'): self.practice_list.blockSignals(True)
        items = self.learn_list.findItems(word, Qt.MatchExactly)
        if items: self.learn_list.setCurrentItem(items[0])
        if hasattr(self, 'practice_list'):
            items_prac = self.practice_list.findItems(word, Qt.MatchExactly)
            if items_prac: self.practice_list.setCurrentItem(items_prac[0])
        self.learn_list.blockSignals(False)
        if hasattr(self, 'practice_list'): self.practice_list.blockSignals(False)
        
        desc = self.word_data.get(word, "설명이 없습니다.")
        if hasattr(self, 'lbl_learn_desc'): self.lbl_learn_desc.setText(desc)
        if hasattr(self, 'practice_progress'):
            self.practice_progress.setValue(0); self.practice_progress.setFormat(f"[{word}] 동작 연습을 시작합니다.")
        if hasattr(self, 'lbl_practice_desc_text'):
            self.lbl_practice_desc_text.setText(f"<span style='color:#4CAF50; font-size: 20px; font-weight: bold;'>[수형 설명] {desc}</span>")
            self.lbl_practice_ai_feedback.setText("AI 분석 대기 중...")
            
        if not self.initial_load and self.tabs.currentIndex() == 0: self.play_word_audio(word)
        target_video = target_img = None
        clean_target_word = unicodedata.normalize('NFC', word.strip().replace(" ", ""))
        if os.path.exists(self.base_path):
            for file in os.listdir(self.base_path):
                name, ext = os.path.splitext(file)
                if clean_target_word == unicodedata.normalize('NFC', name.strip().replace(" ", "")):
                    if ext.lower() in ['.mp4', '.avi', '.mov', '.webm', '.mkv']: target_video = os.path.join(self.base_path, file)
                    elif ext.lower() in ['.jpg', '.jpeg', '.png']: target_img = os.path.join(self.base_path, file)
        
        if hasattr(self, 'learn_default_img'):
            if os.path.exists(self.default_expert_img_path):
                self.learn_default_img.setPixmap(QPixmap(self.default_expert_img_path).scaled(600, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.learn_default_img.setStyleSheet("background-color: black; border-radius: 10px;")
            self.learn_video_stack.setCurrentIndex(0)
            
        if target_img:
            safe_img_path = "/tmp/temp_sign_img.jpg"
            try:
                shutil.copy2(target_img, safe_img_path)
                pixmap = QPixmap(safe_img_path).scaled(450, 350, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                if hasattr(self, 'lbl_learn_image'): self.lbl_learn_image.setPixmap(pixmap)
                if hasattr(self, 'lbl_practice_image'): self.lbl_practice_image.setPixmap(pixmap)
            except Exception: pass
        else:
            no_img_style = "background-color: #3a3a3a; border-radius: 10px; color: #ff4444; font-size: 16px;"
            if hasattr(self, 'lbl_learn_image'): self.lbl_learn_image.setText("사진 없음"); self.lbl_learn_image.setStyleSheet(no_img_style)
            if hasattr(self, 'lbl_practice_image'): self.lbl_practice_image.setText("사진 없음"); self.lbl_practice_image.setStyleSheet(no_img_style)
                
        self.current_video_path = target_video
        if target_video and self.tabs.currentIndex() == 0:
            if not self.initial_load: self.play_video()
        else:
            self.video_timer.stop()
            if getattr(self, 'video_cap', None) is not None: self.video_cap.release(); self.video_cap = None
            if hasattr(self, 'learn_video_stack'): self.learn_video_stack.setCurrentIndex(0)

    def setup_learn_tab(self):
        layout = QHBoxLayout()
        self.learn_list = QListWidget()
        left_panel = self.create_word_selection_panel(self.learn_list)
        right_panel = QVBoxLayout()
        top_half = QVBoxLayout()
        lbl_video_title = QLabel("전문 시연 영상")
        lbl_video_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffb74d;")
        
        self.learn_video_stack = QStackedWidget()
        self.learn_default_img = QLabel(); self.learn_default_img.setAlignment(Qt.AlignCenter)
        self.learn_default_img.setStyleSheet("background-color: black; border-radius: 10px;"); self.learn_default_img.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        if os.path.exists(self.default_expert_img_path): self.learn_default_img.setPixmap(QPixmap(self.default_expert_img_path).scaled(600, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        self.learn_video_label = QLabel("비디오 재생 영역\n(영상이 없거나 코덱을 지원하지 않습니다)"); self.learn_video_label.setAlignment(Qt.AlignCenter)
        self.learn_video_label.setStyleSheet("background-color: black; border-radius: 10px; color: white;"); self.learn_video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.learn_video_stack.addWidget(self.learn_default_img); self.learn_video_stack.addWidget(self.learn_video_label)
        
        self.btn_replay_learn = QPushButton("영상 다시보기")
        self.btn_replay_learn.setStyleSheet("background-color: #ff9800; color: white; font-size: 16px; font-weight: bold; padding: 10px; border-radius: 5px;")
        self.btn_replay_learn.clicked.connect(self.replay_video)
        
        top_half.addWidget(lbl_video_title); top_half.addWidget(self.learn_video_stack, stretch=1); top_half.addWidget(self.btn_replay_learn)
        
        bottom_half = QVBoxLayout()
        lbl_img_title = QLabel("수형 이미지 및 설명")
        lbl_img_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #4CAF50;")
        self.lbl_learn_image = QLabel("사진 없음"); self.lbl_learn_image.setStyleSheet("background-color: transparent;"); self.lbl_learn_image.setAlignment(Qt.AlignCenter)
        self.lbl_learn_desc = QLabel("단어를 선택해 주세요."); self.lbl_learn_desc.setWordWrap(True)
        self.lbl_learn_desc.setStyleSheet("font-size: 20px; color: #FFD700; font-weight: bold; padding-top: 5px;"); self.lbl_learn_desc.setAlignment(Qt.AlignCenter)
        
        bottom_half.addWidget(lbl_img_title); bottom_half.addWidget(self.lbl_learn_image, stretch=1); bottom_half.addWidget(self.lbl_learn_desc)
        right_panel.addLayout(top_half, 6); right_panel.addLayout(bottom_half, 4)
        layout.addLayout(left_panel, 1); layout.addLayout(right_panel, 3)
        self.tab_learn.setLayout(layout)

    def play_video(self):
        if hasattr(self, 'current_video_path') and self.current_video_path:
            self.video_loop_count = 0 
            if self.video_cap is not None: self.video_cap.release()
            self.video_cap = cv2.VideoCapture(self.current_video_path)
            if not self.video_cap.isOpened():
                self.learn_video_label.setText("영상 재생 실패\n(지원하지 않는 코덱이거나 파일이 손상되었습니다)")
                self.learn_video_stack.setCurrentIndex(1)
                return
            self.learn_video_stack.setCurrentIndex(1)
            total_frames = self.video_cap.get(cv2.CAP_PROP_FRAME_COUNT)
            fps = self.video_cap.get(cv2.CAP_PROP_FPS)
            self.video_fps = total_frames / 2.0 if 0 < total_frames <= 60 else fps if (0 < fps <= 60) else 30
            self.video_start_time = time.time()
            self.video_timer.start(10)

    def update_video_frame(self):
        if self.video_cap is None or not self.video_cap.isOpened(): return
        elapsed = time.time() - self.video_start_time
        expected_frame_idx = int(elapsed * self.video_fps)
        current_frame_idx = int(self.video_cap.get(cv2.CAP_PROP_POS_FRAMES))

        if current_frame_idx > expected_frame_idx: return 

        ret = False; frame = None
        while current_frame_idx <= expected_frame_idx:
            ret, frame = self.video_cap.read()
            if not ret: break
            current_frame_idx += 1

        if not ret or frame is None:
            self.video_loop_count += 1
            if self.video_loop_count < 2:
                self.video_cap.release(); self.video_cap = cv2.VideoCapture(self.current_video_path); self.video_start_time = time.time() 
            else:
                self.video_timer.stop(); self.learn_video_stack.setCurrentIndex(0); self.video_cap.release(); self.video_cap = None
            return

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        q_img = QImage(rgb_frame.data, w, h, ch * w, QImage.Format_RGB888)
        cw, ch = self.learn_video_label.width(), self.learn_video_label.height()
        if cw > 0 and ch > 0: self.learn_video_label.setPixmap(QPixmap.fromImage(q_img).scaled(cw, ch, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def replay_video(self): self.play_video()

    def setup_practice_tab(self):
        tab_layout = QHBoxLayout()
        self.practice_list = QListWidget()
        left_panel = self.create_word_selection_panel(self.practice_list)
        right_panel = QVBoxLayout()
        lbl_cam_title = QLabel("내 동작 분석 및 Hailo-10H 로컬 AI 피드백")
        lbl_cam_title.setStyleSheet("font-size: 22px; font-weight: bold; color: #008CBA;")
        self.lbl_practice_camera = QLabel("카메라 대기 중..."); self.lbl_practice_camera.setAlignment(Qt.AlignCenter)
        self.lbl_practice_camera.setStyleSheet("background-color: black; border-radius: 10px;"); self.lbl_practice_camera.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored) 
        self.practice_progress = QProgressBar()
        self.practice_progress.setRange(0, 100); self.practice_progress.setValue(0); self.practice_progress.setFormat("버튼을 누르고 동작하세요")
        self.practice_progress.setFixedHeight(35)
        self.practice_progress.setStyleSheet("QProgressBar { border: 2px solid grey; border-radius: 10px; text-align: center; font-size: 20px; font-weight: bold; color: white; background-color: #2b2b2b;} QProgressBar::chunk { background-color: #4CAF50; border-radius: 8px;}")
        self.lbl_practice_desc_text = QLabel("[수형 설명] 단어를 선택해주세요."); self.lbl_practice_desc_text.setWordWrap(True)
        self.lbl_practice_desc_text.setStyleSheet("font-size: 20px; font-weight: bold; color: #4CAF50; margin: 5px 0px;")
        self.lbl_practice_ai_feedback = QLabel("AI 분석 대기 중..."); self.lbl_practice_ai_feedback.setWordWrap(True); self.lbl_practice_ai_feedback.setAlignment(Qt.AlignCenter)
        self.lbl_practice_ai_feedback.setStyleSheet("font-size: 22px; font-weight: bold; color: #FFD700; background-color: #3a3a3a; padding: 15px; border-radius: 10px;")
        
        btn_layout = QHBoxLayout()
        self.btn_check_motion = QPushButton("동작 2초 녹화 및 정확도 판독")
        self.btn_check_motion.setStyleSheet("background-color: #4CAF50; color: white; font-size: 22px; font-weight: bold; padding: 15px; border-radius: 8px;")
        self.btn_check_motion.clicked.connect(lambda: self.start_recording("practice"))
        btn_layout.addWidget(self.btn_check_motion, stretch=3)
        
        right_panel.addWidget(lbl_cam_title, stretch=0); right_panel.addWidget(self.lbl_practice_camera, stretch=6); right_panel.addWidget(self.practice_progress, stretch=0)
        right_panel.addWidget(self.lbl_practice_desc_text, stretch=0); right_panel.addWidget(self.lbl_practice_ai_feedback, stretch=3); right_panel.addLayout(btn_layout, stretch=0) 
        tab_layout.addLayout(left_panel, 1); tab_layout.addLayout(right_panel, 3) 
        self.tab_practice.setLayout(tab_layout)

    def setup_test_tab(self):
        self.test_stack = QStackedWidget()
        menu_widget = QWidget(); menu_layout = QVBoxLayout(menu_widget)
        lbl_menu_title = QLabel("[ 원하시는 퀴즈 모드를 선택하세요 ]"); lbl_menu_title.setStyleSheet("font-size: 32px; font-weight: bold; color: #ffb74d;"); lbl_menu_title.setAlignment(Qt.AlignCenter)
        menu_layout.addStretch(); menu_layout.addWidget(lbl_menu_title)
        vbox_btns = QVBoxLayout(); vbox_btns.setAlignment(Qt.AlignCenter)
        btns_info = [("1. 실전 동작 퀴즈", "action"), ("2. 이미지 매칭 퀴즈", "image"), ("3. 설명 매칭 퀴즈", "desc"), ("4. 스피드 단어 맞추기", "speed"), ("5. 수어 초성 퀴즈", "initial"), ("6. 거꾸로 퀴즈", "reverse"), ("7. 서바이벌 실전", "survival")]
        for text, mode in btns_info:
            btn = QPushButton(text); btn.setFixedWidth(650)
            btn.setStyleSheet("background-color: #008CBA; color: white; font-size: 22px; font-weight: bold; padding: 15px 30px; text-align: left; padding-left: 30px; border-radius: 10px; margin: 5px;")
            btn.clicked.connect(lambda checked, m=mode: self.start_quiz_session(m))
            vbox_btns.addWidget(btn)
        menu_layout.addLayout(vbox_btns); menu_layout.addStretch()
        
        action_widget = QWidget(); action_layout = QVBoxLayout(action_widget)
        self.lbl_quiz_title_act = QLabel("실전 동작 퀴즈"); self.lbl_quiz_title_act.setStyleSheet("font-size: 28px; font-weight: bold; color: #ffb74d;"); self.lbl_quiz_title_act.setAlignment(Qt.AlignCenter)
        self.lbl_quiz_target_act = QLabel("버튼을 누르면 문제가 나옵니다"); self.lbl_quiz_target_act.setStyleSheet("font-size: 36px; font-weight: bold; color: white; background-color: #3a3a3a; padding: 20px; border-radius: 15px;"); self.lbl_quiz_target_act.setAlignment(Qt.AlignCenter)
        self.lbl_test_camera = QLabel("카메라 대기 중..."); self.lbl_test_camera.setAlignment(Qt.AlignCenter)
        self.lbl_test_camera.setStyleSheet("background-color: black; border-radius: 10px;"); self.lbl_test_camera.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        btn_action_layout = QHBoxLayout()
        self.btn_submit_act = QPushButton("정답 제출 (1초 퀵 스캔)"); self.btn_submit_act.setStyleSheet("background-color: #4CAF50; color: white; font-size: 20px; font-weight: bold; padding: 15px; border-radius: 10px;")
        self.btn_submit_act.clicked.connect(lambda: self.start_recording("quiz_act"))
        self.btn_exit_quiz1 = QPushButton("퀴즈 포기 및 나가기"); self.btn_exit_quiz1.setStyleSheet("background-color: #f44336; color: white; font-size: 20px; font-weight: bold; padding: 15px; border-radius: 10px;")
        self.btn_exit_quiz1.clicked.connect(self.exit_mc_quiz)
        btn_action_layout.addWidget(self.btn_submit_act); btn_action_layout.addWidget(self.btn_exit_quiz1)
        action_layout.addWidget(self.lbl_quiz_title_act); action_layout.addWidget(self.lbl_quiz_target_act); action_layout.addWidget(self.lbl_test_camera, stretch=1); action_layout.addLayout(btn_action_layout)
        
        mc_widget = QWidget(); mc_layout = QVBoxLayout(mc_widget)
        self.lbl_quiz_title_mc = QLabel("객관식 퀴즈"); self.lbl_quiz_title_mc.setStyleSheet("font-size: 28px; font-weight: bold; color: #ffb74d;"); self.lbl_quiz_title_mc.setAlignment(Qt.AlignCenter)
        self.speed_progress = QProgressBar(); self.speed_progress.setRange(0, 50); self.speed_progress.setValue(50); self.speed_progress.setTextVisible(False); self.speed_progress.setFixedHeight(15)
        self.speed_progress.setStyleSheet("QProgressBar { border: none; background-color: #2b2b2b;} QProgressBar::chunk { background-color: #f44336; }"); self.speed_progress.hide()
        self.mc_content_stack = QStackedWidget()
        self.lbl_mc_image = QLabel("이미지"); self.lbl_mc_image.setAlignment(Qt.AlignCenter); self.lbl_mc_image.setStyleSheet("background-color: #2b2b2b; border-radius: 10px;")
        self.lbl_mc_desc = QLabel("설명 텍스트"); self.lbl_mc_desc.setWordWrap(True); self.lbl_mc_desc.setAlignment(Qt.AlignCenter)
        self.lbl_mc_desc.setStyleSheet("font-size: 32px; font-weight: bold; color: white; background-color: #2b2b2b; padding: 30px; border-radius: 10px;")
        self.mc_content_stack.addWidget(self.lbl_mc_image); self.mc_content_stack.addWidget(self.lbl_mc_desc)
        grid_layout = QGridLayout()
        self.btn_mc_choices = []
        for i in range(4):
            btn = QPushButton(f"보기 {i+1}"); btn.setStyleSheet("background-color: #008CBA; color: white; font-size: 24px; font-weight: bold; padding: 20px 30px; text-align: left; padding-left: 30px; border-radius: 10px;")
            btn.clicked.connect(lambda checked, idx=i: self.check_mc_answer(idx))
            self.btn_mc_choices.append(btn)
            grid_layout.addWidget(btn, i//2, i%2)
        self.btn_exit_quiz2 = QPushButton("퀴즈 메뉴로"); self.btn_exit_quiz2.setStyleSheet("background-color: #f44336; color: white; font-size: 20px; font-weight: bold; padding: 15px; border-radius: 10px;")
        self.btn_exit_quiz2.clicked.connect(self.exit_mc_quiz)
        mc_layout.addWidget(self.lbl_quiz_title_mc); mc_layout.addWidget(self.speed_progress); mc_layout.addWidget(self.mc_content_stack, stretch=1); mc_layout.addLayout(grid_layout); mc_layout.addWidget(self.btn_exit_quiz2)
        
        self.test_stack.addWidget(menu_widget); self.test_stack.addWidget(action_widget); self.test_stack.addWidget(mc_widget)
        self.tab_test.setLayout(QVBoxLayout()); self.tab_test.layout().addWidget(self.test_stack)

    def setup_auto_tab(self):
        layout = QVBoxLayout()
        cam_panel = QVBoxLayout()
        lbl_auto_cam = QLabel("자율 동작 녹화 및 AI 분석 모드")
        lbl_auto_cam.setStyleSheet("font-size: 20px; font-weight: bold; color: #008CBA;")
        self.lbl_auto_camera = QLabel("카메라 구동 대기 중...")
        self.lbl_auto_camera.setAlignment(Qt.AlignCenter)
        self.lbl_auto_camera.setStyleSheet("background-color: black; border-radius: 10px;")
        self.lbl_auto_camera.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        cam_panel.addWidget(lbl_auto_cam); cam_panel.addWidget(self.lbl_auto_camera, stretch=1)
        
        bottom_panel = QVBoxLayout()
        lbl_local_title = QLabel("AI 판별 및 피드백 (사전 외의 동작도 뼈대 데이터 힌트를 통해 유추하여 번역합니다)")
        lbl_local_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #4CAF50;")
        self.lbl_auto_result = QLabel("준비가 되면 아래 버튼을 누르고 2초간 수어 동작을 취해보세요.")
        self.lbl_auto_result.setWordWrap(True); self.lbl_auto_result.setAlignment(Qt.AlignCenter)
        self.lbl_auto_result.setStyleSheet("font-size: 24px; font-weight: bold; color: white; background-color: #2b2b2b; border-radius: 10px; padding: 20px;")
        
        btn_layout_auto = QHBoxLayout()
        self.btn_auto_scan = QPushButton("동작 2초 녹화 후 AI 분석")
        self.btn_auto_scan.setStyleSheet("background-color: #4CAF50; color: white; font-size: 22px; font-weight: bold; padding: 15px; border-radius: 8px;")
        self.btn_auto_scan.clicked.connect(lambda: self.start_recording("auto"))
        btn_layout_auto.addWidget(self.btn_auto_scan)
        
        bottom_panel.addWidget(lbl_local_title); bottom_panel.addWidget(self.lbl_auto_result, stretch=1); bottom_panel.addLayout(btn_layout_auto)
        layout.addLayout(cam_panel, 7); layout.addLayout(bottom_panel, 3)
        self.tab_auto.setLayout(layout)

    def get_image_path(self, word):
        if not os.path.exists(self.base_path): return None
        clean_target_word = unicodedata.normalize('NFC', word.strip().replace(" ", ""))
        for file in os.listdir(self.base_path):
            name, ext = os.path.splitext(file)
            if clean_target_word == unicodedata.normalize('NFC', name.strip().replace(" ", "")) and ext.lower() in ['.jpg', '.jpeg', '.png']:
                return os.path.join(self.base_path, file)
        return None

    def start_quiz_session(self, q_type):
        self.quiz_type, self.quiz_current_q, self.quiz_correct_count = q_type, 1, 0
        self.speed_timer.stop(); self.stop_tts_audio(); self.speed_progress.hide()
        if q_type in ["action", "initial", "survival"]: self.test_stack.setCurrentIndex(1); self.next_action_question()
        else: self.test_stack.setCurrentIndex(2); self.next_mc_question()

    def next_action_question(self):
        if self.quiz_type != "survival" and self.quiz_current_q > 5: return self.show_quiz_result()
        self.quiz_target_word = random.choice(self.words)
        title = f"실전 동작 퀴즈 (문제 {self.quiz_current_q}/5)" if self.quiz_type == "action" else f"🔠 초성 동작 퀴즈 (문제 {self.quiz_current_q}/5)" if self.quiz_type == "initial" else f"💀 서바이벌 모드 (현재 {self.quiz_correct_count}연속 성공 중)"
        target_text = f"초성: [{get_chosung(self.quiz_target_word)}]" if self.quiz_type == "initial" else f"제시어: [{self.quiz_target_word}]"
        self.lbl_quiz_title_act.setText(title); self.lbl_quiz_target_act.setText(target_text)
        self.lbl_quiz_target_act.setStyleSheet("font-size: 36px; font-weight: bold; color: #FFD700; background-color: #2b2b2b; padding: 20px; border-radius: 15px;")
        self.btn_submit_act.setEnabled(True)

    def update_speed_timer(self):
        self.speed_time_left -= 1; self.speed_progress.setValue(self.speed_time_left)
        if self.speed_time_left > 0 and self.speed_time_left % 10 == 0: self.play_sound_effect("타이머")
        if self.speed_time_left <= 0: self.speed_timer.stop(); self.play_sound_effect("오답"); self.handle_mc_wrong_answer()

    def handle_mc_wrong_answer(self):
        for btn in self.btn_mc_choices: btn.setEnabled(False)
        for i, w in enumerate(self.mc_current_choices):
            self.btn_mc_choices[i].setStyleSheet(f"background-color: {'#4CAF50' if w == self.quiz_target_word else '#f44336'}; color: white; font-size: 18px; font-weight: bold; padding: 20px; border-radius: 10px; text-align: left; padding-left: 30px;")
        self.quiz_current_q += 1; QTimer.singleShot(1500, self.next_mc_question)

    def exit_mc_quiz(self): self.speed_timer.stop(); self.stop_tts_audio(); self.test_stack.setCurrentIndex(0)

    def next_mc_question(self):
        if self.quiz_current_q > 5: return self.show_quiz_result()
        self.quiz_target_word = random.choice(self.words)
        choices = random.sample([w for w in self.words if w != self.quiz_target_word], 3) + [self.quiz_target_word]; random.shuffle(choices)
        self.mc_current_choices = choices
        if self.quiz_type == "reverse":
            self.lbl_quiz_title_mc.setText(f"거꾸로 설명 맞추기 (문제 {self.quiz_current_q}/5)")
            for i in range(4):
                desc = self.word_data.get(choices[i], "설명 없음")
                self.btn_mc_choices[i].setText(desc[:30] + "..." if len(desc) > 30 else desc)
                self.btn_mc_choices[i].setStyleSheet("background-color: #008CBA; color: white; font-size: 16px; font-weight: bold; padding: 15px; border-radius: 10px; text-align: left; padding-left: 30px;"); self.btn_mc_choices[i].setEnabled(True)
            img_path = self.get_image_path(self.quiz_target_word)
            self.lbl_mc_image.setPixmap(QPixmap(img_path).scaled(450, 350, Qt.KeepAspectRatio, Qt.SmoothTransformation)) if img_path else self.lbl_mc_image.setText(f"[{self.quiz_target_word}] 사진 없음")
            self.mc_content_stack.setCurrentIndex(0)
        else:
            for i in range(4):
                self.btn_mc_choices[i].setText(choices[i]); self.btn_mc_choices[i].setStyleSheet("background-color: #008CBA; color: white; font-size: 24px; font-weight: bold; padding: 20px; border-radius: 10px; text-align: left; padding-left: 30px;"); self.btn_mc_choices[i].setEnabled(True)
            if self.quiz_type in ["image", "speed"]:
                self.lbl_quiz_title_mc.setText(f"스피드 단어 맞추기 (문제 {self.quiz_current_q}/5)" if self.quiz_type == "speed" else f"이미지 매칭 퀴즈 (문제 {self.quiz_current_q}/5)")
                img_path = self.get_image_path(self.quiz_target_word)
                self.lbl_mc_image.setPixmap(QPixmap(img_path).scaled(450, 350, Qt.KeepAspectRatio, Qt.SmoothTransformation)) if img_path else self.lbl_mc_image.setText(f"[{self.quiz_target_word}] 사진 없음")
                self.mc_content_stack.setCurrentIndex(0)
                if self.quiz_type == "speed": self.speed_progress.show(); self.speed_time_left = 50; self.speed_progress.setValue(50); self.speed_timer.start(100)
            elif self.quiz_type == "desc":
                self.lbl_quiz_title_mc.setText(f"설명 매칭 퀴즈 (문제 {self.quiz_current_q}/5)")
                self.lbl_mc_desc.setText(f"설명: {self.word_data.get(self.quiz_target_word, '설명이 없습니다.')}")
                self.mc_content_stack.setCurrentIndex(1)

    def check_mc_answer(self, btn_idx):
        self.speed_timer.stop(); self.stop_tts_audio()
        selected_word = self.mc_current_choices[btn_idx]; font_size = "16px" if self.quiz_type == "reverse" else "24px"
        for btn in self.btn_mc_choices: btn.setEnabled(False)
        if selected_word == self.quiz_target_word:
            self.play_sound_effect("정답"); self.quiz_correct_count += 1
            self.btn_mc_choices[btn_idx].setStyleSheet(f"background-color: #4CAF50; color: white; font-size: {font_size}; font-weight: bold; padding: 20px; border-radius: 10px; text-align: left; padding-left: 30px;")
        else:
            self.play_sound_effect("오답"); self.btn_mc_choices[btn_idx].setStyleSheet(f"background-color: #f44336; color: white; font-size: {font_size}; font-weight: bold; padding: 20px; border-radius: 10px; text-align: left; padding-left: 30px;")
            for i, w in enumerate(self.mc_current_choices):
                if w == self.quiz_target_word: self.btn_mc_choices[i].setStyleSheet(f"background-color: #4CAF50; color: white; font-size: {font_size}; font-weight: bold; padding: 20px; border-radius: 10px; text-align: left; padding-left: 30px;")
        self.quiz_current_q += 1; QTimer.singleShot(1500, self.next_mc_question)

    def show_quiz_result(self): self.play_sound_effect("종료"); QuizResultDialog(self.quiz_correct_count, float('inf') if self.quiz_type == "survival" else 5, self).exec_(); self.test_stack.setCurrentIndex(0)

    def start_recording(self, mode):
        t_log("사용자조작", f"녹화 시작 버튼이 클릭되었습니다. (모드: {mode})")
        
        self.stop_tts_audio()
        
        self.analysis_mode, self.is_counting_down, self.countdown_start_time = mode, True, time.time()
        self.last_pose, self.last_lh, self.last_rh, self.last_rel, self.last_rel_head, self.last_torso = [0.0]*12, [0.0]*15, [0.0]*15, [0.0]*9, [0.0]*6, [0.0]*18
        if mode in ["practice", "auto", "gigong"]: self.play_sound_effect("안내멘트")
        if mode == "practice":
            self.record_duration = 2.0; self.btn_check_motion.setEnabled(False); self.practice_progress.setValue(0); self.practice_progress.setFormat("원 안으로 두 손을 모으고 준비하세요... 5, 4, 3, 2, 1"); self.lbl_practice_ai_feedback.setText("...")
        elif mode in ["quiz_act", "initial", "survival"]:
            self.record_duration = 1.0; self.btn_submit_act.setEnabled(False); self.lbl_quiz_target_act.setText("동작 준비... (5초 후 시작)"); self.lbl_quiz_target_act.setStyleSheet("background-color: #FF9800; color: white; font-size: 36px; font-weight: bold; padding: 20px; border-radius: 15px;")
        elif mode == "auto":
            self.record_duration = 2.0; self.btn_auto_scan.setEnabled(False); self.btn_auto_scan.setText("준비하세요... 5, 4, 3, 2, 1"); self.btn_auto_scan.setStyleSheet("background-color: #FF9800; color: white; font-size: 22px; font-weight: bold; padding: 15px; border-radius: 8px;")
        elif mode == "gigong":
            self.record_duration = 2.0; self.btn_gigong_record.setEnabled(False); self.btn_gigong_record.setText("준비하세요... 5, 4, 3, 2, 1")

    def get_3d_direction(self, p1, p2):
        v = np.array([p2.x - p1.x, p2.y - p1.y, p2.z - p1.z]); norm = np.linalg.norm(v)
        return (v / norm).tolist() if norm > 0 else [0.0, 0.0, 0.0]

    def extract_feature_vector(self, results):
        vec = []
        lms_pose, lms_lh, lms_rh = results.pose_landmarks.landmark if results.pose_landmarks else None, results.left_hand_landmarks.landmark if results.left_hand_landmarks else None, results.right_hand_landmarks.landmark if results.right_hand_landmarks else None
        if lms_pose:
            self.last_pose = self.get_3d_direction(lms_pose[11], lms_pose[13]) + self.get_3d_direction(lms_pose[12], lms_pose[14]) + self.get_3d_direction(lms_pose[13], lms_pose[15]) + self.get_3d_direction(lms_pose[14], lms_pose[16])
        vec.extend(self.last_pose)
        if lms_lh:
            lh = []
            for tip in [4, 8, 12, 16, 20]: lh.extend(self.get_3d_direction(lms_lh[0], lms_lh[tip]))
            self.last_lh = lh
        vec.extend(self.last_lh)
        if lms_rh:
            rh = []
            for tip in [4, 8, 12, 16, 20]: rh.extend(self.get_3d_direction(lms_rh[0], lms_rh[tip]))
            self.last_rh = rh
        vec.extend(self.last_rh)
        if lms_pose and len(lms_pose) > 24: 
            class Point3D:
                def __init__(self, x, y, z): self.x, self.y, self.z = x, y, z
            center = Point3D((lms_pose[11].x + lms_pose[12].x) / 2, (lms_pose[11].y + lms_pose[12].y) / 2, (lms_pose[11].z + lms_pose[12].z) / 2)
            self.last_rel = self.get_3d_direction(lms_pose[15], lms_pose[16]) + self.get_3d_direction(center, lms_pose[15]) + self.get_3d_direction(center, lms_pose[16])
            self.last_rel_head = self.get_3d_direction(lms_pose[0], lms_pose[15]) + self.get_3d_direction(lms_pose[0], lms_pose[16])
            stomach = Point3D((lms_pose[11].x + lms_pose[12].x + lms_pose[23].x + lms_pose[24].x) / 4, (lms_pose[11].y + lms_pose[12].y + lms_pose[23].y + lms_pose[24].y) / 4, (lms_pose[11].z + lms_pose[12].z + lms_pose[23].z + lms_pose[24].z) / 4)
            self.last_torso = self.get_3d_direction(lms_pose[11], lms_pose[15]) + self.get_3d_direction(lms_pose[11], lms_pose[16]) + self.get_3d_direction(lms_pose[12], lms_pose[15]) + self.get_3d_direction(lms_pose[12], lms_pose[16]) + self.get_3d_direction(stomach, lms_pose[15]) + self.get_3d_direction(stomach, lms_pose[16])
        vec.extend(self.last_rel); vec.extend(self.last_rel_head); vec.extend(self.last_torso) 
        return vec

    def trim_active_sequence(self, seq):
        if len(seq) < 10: return seq
        arr, diffs = np.array(seq), np.linalg.norm(np.array(seq)[1:] - np.array(seq)[:-1], axis=1)
        active_indices = np.where(diffs > np.max(diffs) * 0.15)[0]
        return seq[max(0, active_indices[0] - 2):min(len(seq), active_indices[-1] + 3)] if len(active_indices) >= 2 else seq

    def resample_sequence(self, seq, target_len=30):
        if seq is None or len(seq) < 2: return None
        seq_arr = np.array(seq, dtype=np.float32)
        if len(seq_arr.shape) != 2 or seq_arr.shape[1] != 75: return None 
        if seq_arr.shape[0] == target_len: return seq_arr
        resampled, orig_idx, target_idx = np.zeros((target_len, 75), dtype=np.float32), np.linspace(0, 1, seq_arr.shape[0]), np.linspace(0, 1, target_len)
        for d in range(75): resampled[:, d] = np.interp(target_idx, orig_idx, seq_arr[:, d])
        return resampled

    def compute_universal_dtw(self, seq1, seq2):
        if len(seq1) == 0 or len(seq2) == 0: return float('inf')
        seq1_arr, seq2_arr = np.array(seq1), np.array(seq2)
        weights = np.array([1.5]*12 + [2.5]*30 + [2.0]*9 + [3.0]*6 + [2.0]*18) 
        dist_matrix = np.sqrt(np.sum(((seq1_arr[:, None, :] - seq2_arr[None, :, :]) ** 2) * weights, axis=2))
        dtw_matrix = np.full((len(seq1) + 1, len(seq2) + 1), float('inf')); dtw_matrix[0, 0] = 0
        for i in range(1, len(seq1) + 1):
            for j in range(max(1, i - 5), min(len(seq2) + 1, i + 5 + 1)):
                dtw_matrix[i, j] = dist_matrix[i-1, j-1] + min(dtw_matrix[i-1, j], dtw_matrix[i, j-1], dtw_matrix[i-1, j-1])
        return dtw_matrix[len(seq1), len(seq2)] / len(seq1)

    def evaluate_motion_locally(self, user_seq):
        try:
            if len(user_seq) < 5: return [("프레임 부족", 0), ("-", 0), ("-", 0)]
            if np.mean(np.std(np.array(user_seq), axis=0)) < 0.015: return [("손 동작 없음", 0), ("-", 0), ("-", 0)]
            norm_user = self.resample_sequence(self.trim_active_sequence(user_seq), 30)
            if norm_user is None: return [("데이터 규격 불일치", 0), ("-", 0), ("-", 0)]
            results = sorted([(w, int(max(0, min(100, 100 - (max(0, self.compute_universal_dtw(norm_user, self.expert_data[w]) - 3.5) * 4.0)))), self.compute_universal_dtw(norm_user, self.expert_data[w])) for w in self.words if self.expert_data.get(w)], key=lambda x: x[1], reverse=True)
            return [(r[0], r[1]) for r in (results + [("알 수 없음", 0, 0)] * 3)[:3]]
        except Exception: return [("연산 오류", 0), ("-", 0), ("-", 0)]

    def process_hybrid_analysis(self, user_seq=None, vision_frame=None):
        if user_seq is None: user_seq = list(self.pose_buffer)
        top3 = self.evaluate_motion_locally(user_seq)
        
        t_log("NPU판독", f"결과 ➡️ 1순위: {top3[0][0]}({top3[0][1]}점), 2순위: {top3[1][0]}({top3[1][1]}점), 3순위: {top3[2][0]}({top3[2][1]}점)")
        
        if self.analysis_mode == "gigong":
            return self.ui_queue.put(("gigong_motion_done", top3))
            
        self.ui_queue.put(("local", top3, self.analysis_mode))
        best_match, best_score = top3[0]
        if best_match in ["손 동작 없음", "동작 대기 중...", "데이터 규격 불일치", "연산 오류"] or best_score < 20: 
            return self.ui_queue.put(("ai", "수어 동작이 명확하지 않거나 감지되지 않았습니다. 카메라 앞에서 크고 정확하게 다시 동작을 취해주세요.", top3, self.analysis_mode))
        
        if self.analysis_mode in ["action", "initial", "survival", "quiz_act"]: 
            self.ui_queue.put(("ai", "로컬 채점 완료", top3, self.analysis_mode))
            
        elif self.analysis_mode in ["auto", "practice"]: 
            t_log("AI통신", f"노트북 AI({self.analysis_mode} 모드)에게 번역/대화 응답을 요청합니다.")
            feedback, _, _ = self.request_vlm_feedback(top3, self.analysis_mode, vision_frame, user_seq)
            self.ui_queue.put(("ai", feedback, top3, self.analysis_mode))

    def update_ui_local_first(self, top3, mode):
        best_match, best_score = top3[0]
        if mode == "practice":
            target_score = next((score for w, score in top3 if w == self.current_target_word), 0); self.practice_progress.setValue(target_score); self.practice_progress.setFormat(f"로컬 판독: {self.current_target_word} ({target_score}점) - AI 분석 대기 중...")
        elif mode == "auto":
            self.lbl_auto_result.setText("[알림] 동작이 감지되지 않아 분석을 취소했습니다." if best_match in ["손 동작 없음", "동작 대기 중...", "데이터 규격 불일치", "연산 오류"] else f"[NPU 1차 판독] 1순위 '{top3[0][0]}', 2순위 '{top3[1][0]}'\n[대기] AI 어시스턴트가 상황을 분석하고 있습니다..." if best_score >= 55 else f"[녹화 완료] (유사 동작: {best_match})\n[대기] AI 어시스턴트가 상황을 분석 중입니다...")

    def request_vlm_feedback(self, top3, mode, vision_frame=None, user_seq=None):
        best_match, best_score = top3[0]
        target_score = best_score if mode != "practice" else next((score for w, score in top3 if w == self.current_target_word), 0)
        
        if mode == "auto":
            dtw_semantic = f"1순위: '{top3[0][0]}'({top3[0][1]}점), 2순위: '{top3[1][0]}'({top3[1][1]}점), 3순위: '{top3[2][0]}'({top3[2][1]}점)."
        else:
            if target_score >= 80: dtw_semantic = f"'{best_match}' 동작을 훌륭하게 수행하고 있습니다."
            elif target_score >= 40: dtw_semantic = f"'{best_match}' 동작의 방향성은 맞으나 손의 위치나 각도가 약간 어색합니다."
            else: dtw_semantic = "의미를 알 수 없는 다른 동작을 하고 있습니다."

        target_word = self.current_target_word if mode == "practice" else best_match
        desc = self.word_data.get(target_word, '')

        try:
            img_to_send = PILImage.fromarray(vision_frame) if vision_frame is not None and PILLOW_READY and mode == "practice" else None
            feedback = local_vlm_model.generate_advanced(
                request_type=mode,
                target_word=target_word,
                correct_description=desc,
                dtw_semantic=dtw_semantic,
                dtw_score=target_score,
                image=img_to_send
            )
        except Exception as e:
            t_log("에러", f"AI 통신 에러: {e}")
            feedback = "[시스템 에러] 통신 에러로 피드백을 생성할 수 없습니다."
        return feedback, best_match, best_score

    def update_ui_ai_feedback(self, feedback, top3, mode):
        best_match, best_score = top3[0]
        if mode == "practice":
            self.btn_check_motion.setEnabled(True); target_score = next((score for w, score in top3 if w == self.current_target_word), 0)
            self.practice_progress.setFormat(f"최종 정확도: {target_score}점"); self.practice_progress.setValue(target_score); self.lbl_practice_ai_feedback.setText(f"{feedback}"); self.speak_text(feedback.replace("[AI 어시스턴트 피드백]", ""))
        elif mode in ["action", "initial", "survival", "quiz_act"]: 
            if best_match == self.quiz_target_word and best_score >= 60: self.play_sound_effect("정답"); self.quiz_correct_count += 1; self.lbl_quiz_target_act.setText(f"[ 정답! ] (판독: {best_score}점)"); self.lbl_quiz_target_act.setStyleSheet("font-size: 24px; font-weight: bold; color: white; background-color: #4CAF50; padding: 20px; border-radius: 15px;")
            else: self.play_sound_effect("오답"); self.lbl_quiz_target_act.setText(f"[ 오답 ] (내 동작: {best_match} / {best_score}점)"); self.lbl_quiz_target_act.setStyleSheet("font-size: 24px; font-weight: bold; color: white; background-color: #FF5722; padding: 20px; border-radius: 15px;")
            if mode == "survival" and best_match != self.quiz_target_word: QTimer.singleShot(2500, self.show_quiz_result)
            else: self.quiz_current_q += 1; QTimer.singleShot(2500, self.next_action_question)
        elif mode == "auto":
            self.btn_auto_scan.setEnabled(True); self.btn_auto_scan.setText("동작 2초 녹화 후 초고속 AI 번역"); self.btn_auto_scan.setStyleSheet("background-color: #4CAF50; color: white; font-size: 22px; font-weight: bold; padding: 15px; border-radius: 8px;")
            self.lbl_auto_result.setText(f"[판독 취소]\n{feedback}" if "명확하지 않거나" in feedback or "감지되지 않았습니다" in feedback else f"{feedback}")
            self.speak_text(feedback if "명확하지 않거나" in feedback or "감지되지 않았습니다" in feedback else feedback.split("번역 결과]")[1].split("[판단 근거]")[0].strip() if "[번역 결과]" in feedback else feedback)

    def update_camera_frame(self):
        if self.root_stack.currentIndex() == 0: return
        while not self.ui_queue.empty():
            try:
                msg = self.ui_queue.get_nowait()
                if msg[0] == "local": self.update_ui_local_first(msg[1], msg[2])
                elif msg[0] == "ai": self.update_ui_ai_feedback(msg[1], msg[2], msg[3])
                elif msg[0] == "gigong_mic_success": self.process_gigong_chat(msg[1])
                elif msg[0] == "mic_status_update":
                    if self.is_mic_listening and not self.is_ai_thinking: self.btn_gigong_mic.setText(msg[1])
                elif msg[0] == "gigong_answer": 
                    self.append_chat_log("🤖 AI 어시스턴트", msg[1])
                    self.speak_text(msg[1])
                elif msg[0] == "gigong_motion_done":
                    self.btn_gigong_record.setEnabled(True); self.btn_gigong_record.setText("⏺️ 동작 2초 녹화 전송")
                    self.process_gigong_chat("", gigong_top3=msg[1])
                elif msg[0] == "mic_resume":
                    if self.is_mic_listening:
                        self.btn_gigong_mic.setText("⏹️ 연속 듣기 끄기")
                        self.btn_gigong_mic.setStyleSheet("background-color: #f44336; color: white; font-size: 20px; font-weight: bold; padding: 15px; border-radius: 10px;")
            except Exception: pass

        if getattr(self, 'is_processing_frame', False): return
        self.is_processing_frame = True
        
        try:
            if self.cap is None or not self.cap.isOpened(): return
            self.frame_count += 1
            ret, raw_frame = self.cap.read()
            if not ret: return
            
            frame = cv2.flip(raw_frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.latest_raw_frame = rgb_frame.copy()
            final_frame = rgb_frame.copy() 
            h, w, ch = final_frame.shape
            
            if getattr(self, 'is_counting_down', False):
                remain = 5 - int(time.time() - self.countdown_start_time)
                if remain > 0: cv2.putText(final_frame, str(remain), (int(w/2) - 30, int(h/2) + 30), cv2.FONT_HERSHEY_SIMPLEX, 5, (0, 165, 255), 10, cv2.LINE_AA)
                else:
                    self.is_counting_down, self.is_recording, self.record_start_time, self.pose_buffer, self.vision_buffer = False, True, time.time(), deque(maxlen=100), []
                    if self.analysis_mode == "practice": self.ui_queue.put(("ui_update", "practice")); self.practice_progress.setFormat("동작을 녹화 중입니다...")
                    elif self.analysis_mode in ["quiz_act", "initial", "survival"]: self.lbl_quiz_target_act.setText("1초 빠른 판독 진행 중..."); self.lbl_quiz_target_act.setStyleSheet("background-color: #f44336; color: white; font-size: 36px; font-weight: bold; padding: 20px; border-radius: 15px;")
                    elif self.analysis_mode == "auto": self.lbl_auto_result.setText("카메라를 보고 자유롭게 수어 동작을 취해주세요..."); self.btn_auto_scan.setText("동작을 녹화 중입니다..."); self.btn_auto_scan.setStyleSheet("background-color: #f44336; color: white; font-size: 22px; font-weight: bold; padding: 15px; border-radius: 8px;")
                    elif self.analysis_mode == "gigong": self.lbl_chat_camera.setText("카메라를 보고 수어 동작을 취해주세요..."); self.btn_gigong_record.setText("동작을 녹화 중입니다...")

            current_tab = self.tabs.currentIndex()
            results = self.holistic.process(rgb_frame) if current_tab != 0 else None
            
            if results:
                if results.pose_landmarks: self.mp_drawing.draw_landmarks(final_frame, results.pose_landmarks, mp_holistic.POSE_CONNECTIONS)
                if results.left_hand_landmarks: self.mp_drawing.draw_landmarks(final_frame, results.left_hand_landmarks, mp_holistic.HAND_CONNECTIONS)
                if results.right_hand_landmarks: self.mp_drawing.draw_landmarks(final_frame, results.right_hand_landmarks, mp_holistic.HAND_CONNECTIONS)
                
                if self.is_recording:
                    self.pose_buffer.append(self.extract_feature_vector(results))
                    self.vision_buffer.append(rgb_frame.copy())
                    if time.time() - self.record_start_time >= getattr(self, 'record_duration', 2.0):
                        self.is_recording = False
                        seq_copy, vision_copy = list(self.pose_buffer), cv2.hconcat([self.vision_buffer[0], self.vision_buffer[len(self.vision_buffer)//2], self.vision_buffer[-1]]) if len(self.vision_buffer) >= 3 else rgb_frame.copy()
                        self.vision_buffer = [] 
                        threading.Thread(target=self.process_hybrid_analysis, args=(seq_copy, vision_copy), daemon=True).start()

            box_color = (0, 165, 255) if getattr(self, 'is_counting_down', False) else (255, 0, 0) if self.is_recording else (0, 255, 0)
            cv2.rectangle(final_frame, (int(w*0.02), int(h*0.02)), (int(w*0.98), int(h*0.98)), box_color, 4 if (self.is_recording or getattr(self, 'is_counting_down', False)) else 2)
            cv2.ellipse(final_frame, (int(w/2), int(h*0.25)), (int(w*0.08), int(h*0.15)), 0, 0, 360, (255, 255, 0), 2, cv2.LINE_AA)
            cv2.putText(final_frame, "HEAD", (int(w/2) - 30, int(h*0.25) - int(h*0.15) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2, cv2.LINE_AA)
            cv2.line(final_frame, (int(w/2) - int(w*0.28), int(h*0.60)), (int(w/2) + int(w*0.28), int(h*0.60)), (255, 255, 0), 2, cv2.LINE_AA)
            cv2.putText(final_frame, "SHOULDER", (int(w/2) - 55, int(h*0.60) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2, cv2.LINE_AA)
            for offset, label in [(-int(w*0.21), "L-HAND"), (int(w*0.21), "R-HAND")]:
                cv2.circle(final_frame, (int(w/2) + offset, int(h*0.88)), int(w*0.045), (255, 255, 0), 2, cv2.LINE_AA)
                cv2.putText(final_frame, label, (int(w/2) + offset - 30, int(h*0.88) - int(w*0.045) - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 2, cv2.LINE_AA)
            
            scaled_img = QPixmap.fromImage(QImage(final_frame.data, w, h, ch * w, QImage.Format_RGB888))
            
            if current_tab == 1 and hasattr(self, 'lbl_practice_camera') and self.lbl_practice_camera.width() > 0: self.lbl_practice_camera.setPixmap(scaled_img.scaled(self.lbl_practice_camera.width(), self.lbl_practice_camera.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            elif current_tab == 2 and hasattr(self, 'lbl_test_camera') and self.quiz_type in ["action", "initial", "survival"] and self.lbl_test_camera.width() > 0: self.lbl_test_camera.setPixmap(scaled_img.scaled(self.lbl_test_camera.width(), self.lbl_test_camera.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            elif current_tab == 3 and hasattr(self, 'lbl_auto_camera') and self.lbl_auto_camera.width() > 0: self.lbl_auto_camera.setPixmap(scaled_img.scaled(self.lbl_auto_camera.width(), self.lbl_auto_camera.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            elif current_tab == 4 and getattr(self, 'is_gigong_camera_active', False) and hasattr(self, 'lbl_chat_camera') and self.lbl_chat_camera.width() > 0: self.lbl_chat_camera.setPixmap(scaled_img.scaled(self.lbl_chat_camera.width(), self.lbl_chat_camera.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                
        except Exception: pass
        finally: self.is_processing_frame = False

    def apply_styles(self):
        self.setStyleSheet("""
            QWidget { font-family: 'NanumGothic', 'Nanum Gothic', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; }
            QMainWindow { background-color: #1e1e1e; }
            QTabWidget::pane { border: 2px solid #3a3a3a; background: #2b2b2b; border-radius: 10px; }
            QTabBar::tab { background: #3a3a3a; color: white; padding: 10px 10px; font-size: 18px; font-weight: bold; border-top-left-radius: 10px; border-top-right-radius: 10px; margin-right: 2px; min-width: 110px; }
            QTabBar::tab:selected { background: #4CAF50; color: white; }
            QTabBar::scroller { width: 0px; } 
            QLabel { color: #cccccc; font-size: 20px; }
            QListWidget { background-color: #3a3a3a; color: white; font-size: 20px; padding: 10px; border-radius: 10px; border: none;}
            QListWidget::item { padding: 15px; border-bottom: 1px solid #555; }
            QListWidget::item:selected { background-color: #E91E63; border-radius: 5px; color: white; font-weight: bold; }
            QScrollBar:vertical { background: #2b2b2b; width: 15px; border-radius: 5px; }
            QScrollBar::handle:vertical { background: #555; border-radius: 5px; }
        """)

    def closeEvent(self, event):
        t_log("시스템", "==================================================")
        t_log("시스템", "수어 학습기 및 투명 관제 모드 종료 시퀀스 가동...")
        self.timer.stop()
        if hasattr(self, 'video_timer'): self.video_timer.stop()
        if getattr(self, 'video_cap', None) is not None: self.video_cap.release()
        self.stop_tts_audio()
        if self.cap and self.cap.isOpened(): self.cap.release()
        t_log("시스템", "카메라, 오디오, 스레드 자원을 안전하게 해제했습니다.")
        t_log("시스템", "프로그램이 성공적으로 종료되었습니다. 안녕히 계세요!")
        t_log("시스템", "==================================================")
        event.accept()
        os._exit(0) 

if __name__ == '__main__':
    if "DISPLAY" not in os.environ: os.environ["DISPLAY"] = ":0"
    os.environ["QT_X11_NO_MITSHM"] = "1"
    app = QApplication(sys.argv)
    font_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id != -1:
            font_families = QFontDatabase.applicationFontFamilies(font_id)
            if font_families: app.setFont(QFont(font_families[0], 11))
    ex = SignLanguageApp()
    ex.show()
    sys.exit(app.exec_())