import sys
import os
import cv2
import json
import time
import numpy as np
import mediapipe as mp
import shutil
import subprocess
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QListWidget, QLabel, QMessageBox, QSizePolicy, QLineEdit,
                             QRadioButton, QButtonGroup)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QImage

mp_holistic = mp.solutions.holistic

def t_log(category, message):
    current_time = time.strftime('%H:%M:%S')
    print(f"[{current_time}] [{category}] {message}", flush=True)

def assemble_hangul(jamos):
    CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
    JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
    JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
    COMPLEX_JUNG = {'ㅗㅏ': 'ㅘ', 'ㅗㅐ': 'ㅙ', 'ㅗㅣ': 'ㅚ', 'ㅜㅓ': 'ㅝ', 'ㅜㅔ': 'ㅞ', 'ㅜㅣ': 'ㅟ', 'ㅡㅣ': 'ㅢ'}
    COMPLEX_JONG = {'ㄱㅅ': 'ㄳ', 'ㄴㅈ': 'ㄵ', 'ㄴㅎ': 'ㄶ', 'ㄹㄱ': 'ㄺ', 'ㄹㅁ': 'ㄻ', 'ㄹㅂ': 'ㄼ', 'ㄹㅅ': 'ㄽ', 'ㄹㅌ': 'ㄾ', 'ㄹㅍ': 'ㄿ', 'ㄹㅎ': 'ㅀ', 'ㅂㅅ': 'ㅄ'}
    result = ""
    state = 0
    cho_idx, jung_idx, jong_idx = -1, -1, 0
    def flush():
        nonlocal result, cho_idx, jung_idx, jong_idx, state
        if state == 1: result += CHO[cho_idx]
        elif state == 2 or state == 3: result += chr(0xAC00 + (cho_idx * 21 * 28) + (jung_idx * 28) + jong_idx)
        cho_idx, jung_idx, jong_idx = -1, -1, 0
        state = 0
    i = 0
    while i < len(jamos):
        j = jamos[i]
        if j == " ":
            flush(); result += " "; i += 1; continue
        is_cho = j in CHO
        is_jung = j in JUNG
        if state == 0:
            if is_cho: cho_idx = CHO.index(j); state = 1
            elif is_jung: result += j
            else: result += j
        elif state == 1:
            if is_jung: jung_idx = JUNG.index(j); state = 2
            elif is_cho: flush(); cho_idx = CHO.index(j); state = 1
            else: flush(); result += j
        elif state == 2:
            if is_jung:
                combined = JUNG[jung_idx] + j
                if combined in COMPLEX_JUNG: jung_idx = JUNG.index(COMPLEX_JUNG[combined])
                else: flush(); result += j
            elif is_cho:
                if j in JONG:
                    if i + 1 < len(jamos) and jamos[i+1] in JUNG: flush(); cho_idx = CHO.index(j); state = 1
                    else: jong_idx = JONG.index(j); state = 3
                else: flush(); cho_idx = CHO.index(j); state = 1
            else: flush(); result += j
        elif state == 3:
            if is_cho:
                combined = JONG[jong_idx] + j
                if combined in COMPLEX_JONG:
                    if i + 1 < len(jamos) and jamos[i+1] in JUNG: flush(); cho_idx = CHO.index(j); state = 1
                    else: jong_idx = JONG.index(COMPLEX_JONG[combined])
                else: flush(); cho_idx = CHO.index(j); state = 1
            elif is_jung:
                prev_jong = JONG[jong_idx]
                jong_chars = ""
                for k, v in COMPLEX_JONG.items():
                    if v == prev_jong: jong_chars = k; break
                if jong_chars: jong_idx = JONG.index(jong_chars[0]); flush(); cho_idx = CHO.index(jong_chars[1])
                else: jong_idx = 0; flush(); cho_idx = CHO.index(prev_jong)
                jung_idx = JUNG.index(j); state = 2
            else:
                flush()
                result += j
        i += 1
    flush()
    return result

class VirtualHangulKeyboard(QWidget):
    def __init__(self, target_input):
        super().__init__()
        self.target = target_input
        self.buffer = []
        self.base_text = ""
        self.is_shift = False
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)
        keys_normal = [['ㅂ', 'ㅈ', 'ㄷ', 'ㄱ', 'ㅅ', 'ㅛ', 'ㅕ', 'ㅑ', 'ㅐ', 'ㅔ'],['ㅁ', 'ㄴ', 'ㅇ', 'ㄹ', 'ㅎ', 'ㅗ', 'ㅓ', 'ㅏ', 'ㅣ'],['Shift', 'ㅋ', 'ㅌ', 'ㅊ', 'ㅍ', 'ㅠ', 'ㅜ', 'ㅡ', '지우기']]
        keys_shift = [['ㅃ', 'ㅉ', 'ㄸ', 'ㄲ', 'ㅆ', 'ㅛ', 'ㅕ', 'ㅑ', 'ㅒ', 'ㅖ'],['ㅁ', 'ㄴ', 'ㅇ', 'ㄹ', 'ㅎ', 'ㅗ', 'ㅓ', 'ㅏ', 'ㅣ'],['Shift', 'ㅋ', 'ㅌ', 'ㅊ', 'ㅍ', 'ㅠ', 'ㅜ', 'ㅡ', '지우기']]
        self.keys_normal = keys_normal
        self.keys_shift = keys_shift
        self.buttons = []
        for r_idx, row in enumerate(keys_normal):
            r_layout = QHBoxLayout()
            r_layout.setSpacing(5)
            row_btns = []
            for c_idx, key in enumerate(row):
                btn = QPushButton(key)
                btn.setFixedHeight(40)
                btn.setFocusPolicy(Qt.NoFocus) 
                btn.setStyleSheet("background-color: #555; color: white; font-size: 18px; font-weight: bold; border-radius: 5px;")
                btn.clicked.connect(lambda checked, r=r_idx, c=c_idx: self.on_key(r, c))
                r_layout.addWidget(btn)
                row_btns.append(btn)
            self.layout.addLayout(r_layout)
            self.buttons.append(row_btns)
            
        bottom_layout = QHBoxLayout()
        clear_btn = QPushButton("전체 지우기")
        clear_btn.setFixedHeight(40)
        clear_btn.setFocusPolicy(Qt.NoFocus)
        clear_btn.setStyleSheet("background-color: #f44336; color: white; font-size: 18px; font-weight: bold; border-radius: 5px;")
        clear_btn.clicked.connect(lambda: self.on_key_str("Clear"))
        space_btn = QPushButton("띄어쓰기")
        space_btn.setFixedHeight(40)
        space_btn.setFocusPolicy(Qt.NoFocus)
        space_btn.setStyleSheet("background-color: #666; color: white; font-size: 18px; font-weight: bold; border-radius: 5px;")
        space_btn.clicked.connect(lambda: self.on_key_str(" "))
        close_btn = QPushButton("키보드 닫기")
        close_btn.setFixedHeight(40)
        close_btn.setFocusPolicy(Qt.NoFocus)
        close_btn.setStyleSheet("background-color: #008CBA; color: white; font-size: 18px; font-weight: bold; border-radius: 5px;")
        close_btn.clicked.connect(self.hide)
        
        bottom_layout.addWidget(clear_btn, 1); bottom_layout.addWidget(space_btn, 2); bottom_layout.addWidget(close_btn, 1)
        self.layout.addLayout(bottom_layout)

    def on_key(self, r, c):
        if not self.target: return
        key = self.keys_shift[r][c] if self.is_shift else self.keys_normal[r][c]
        if key == 'Shift': self.is_shift = not self.is_shift; self.update_ui()
        elif key == '지우기':
            if self.buffer: self.buffer.pop(); self.update_target()
            else: self.base_text = self.target.text()[:-1]; self.update_target()
        else:
            self.buffer.append(key)
            if self.is_shift: self.is_shift = False; self.update_ui()
            self.update_target()
            
    def on_key_str(self, action):
        if not self.target: return
        if action == " ": self.buffer.append(" "); self.update_target()
        elif action == "Clear": self.buffer.clear(); self.base_text = ""; self.update_target()
        elif action == "Backspace":
            if self.buffer: self.buffer.pop(); self.update_target()
        else: self.buffer.append(action); self.update_target()

    def update_ui(self):
        keys = self.keys_shift if self.is_shift else self.keys_normal
        for r in range(3):
            for c in range(len(keys[r])):
                self.buttons[r][c].setText(keys[r][c])
                if keys[r][c] == 'Shift':
                    color = "#2196F3" if self.is_shift else "#555"
                    self.buttons[r][c].setStyleSheet(f"background-color: {color}; color: white; font-size: 18px; font-weight: bold; border-radius: 5px;")

    def update_target(self):
        if self.target:
            new_text = self.base_text + assemble_hangul(self.buffer)
            self.target.setText(new_text); self.target.setFocus(); self.target.setCursorPosition(len(new_text))

class HangulLineEdit(QLineEdit):
    def __init__(self, kbd_ref, enter_callback=None):
        super().__init__()
        self.kbd_ref = kbd_ref
        self.enter_callback = enter_callback
        self.eng_to_kor = {'q':'ㅂ', 'w':'ㅈ', 'e':'ㄷ', 'r':'ㄱ', 't':'ㅅ', 'y':'ㅛ', 'u':'ㅕ', 'i':'ㅑ', 'o':'ㅐ', 'p':'ㅔ', 'a':'ㅁ', 's':'ㄴ', 'd':'ㅇ', 'f':'ㄹ', 'g':'ㅎ', 'h':'ㅗ', 'j':'ㅓ', 'k':'ㅏ', 'l':'ㅣ', 'z':'ㅋ', 'x':'ㅌ', 'c':'ㅊ', 'v':'ㅍ', 'b':'ㅠ', 'n':'ㅜ', 'm':'ㅡ', 'Q':'ㅃ', 'W':'ㅉ', 'E':'ㄸ', 'R':'ㄲ', 'T':'ㅆ', 'O':'ㅒ', 'P':'ㅖ'}
        
    def mousePressEvent(self, event):
        if self.kbd_ref.target != self:
            self.kbd_ref.target = self; self.kbd_ref.buffer = []; self.kbd_ref.base_text = self.text()
        self.kbd_ref.show()
        self.setFocus()
        super().mousePressEvent(event)
        
    def keyPressEvent(self, event):
        if self.kbd_ref.target != self:
            self.kbd_ref.target = self; self.kbd_ref.buffer = []; self.kbd_ref.base_text = self.text()
            
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            if self.enter_callback: self.enter_callback()
        else:
            key = event.text()
            if key in self.eng_to_kor: self.kbd_ref.on_key_str(self.eng_to_kor[key])
            elif event.key() == Qt.Key_Backspace: 
                if len(self.kbd_ref.buffer) > 0: self.kbd_ref.on_key_str("Backspace")
                else: super().keyPressEvent(event); self.kbd_ref.base_text = self.text() 
            elif event.key() == Qt.Key_Space: self.kbd_ref.on_key_str(" ")
            else: super().keyPressEvent(event); self.kbd_ref.base_text = self.text()

class GroundTruthStudio(QMainWindow):
    def __init__(self):
        super().__init__()
        
        t_log("초기화", "==================================================")
        t_log("초기화", "수동 정답지 레코딩 스튜디오 PRO 시스템 가동 시작")
        t_log("초기화", "==================================================")
        
        self.setWindowTitle("수동 정답지 레코딩 스튜디오 PRO")
        self.resize(1024, 768)
        self.showFullScreen()
        
        self.holistic = mp_holistic.Holistic(min_detection_confidence=0.5, min_tracking_confidence=0.7)
        self.mp_drawing = mp.solutions.drawing_utils
        self.json_path = "/home/a/Sign_Kiosk/dynamic_sign_model.json"
        self.json_desc_path = "/home/a/Sign_Kiosk/dynamic_sign_desc.json"
        self.json_category_path = "/home/a/Sign_Kiosk/dynamic_sign_category.json"
        self.media_dir = "/home/a/Sign_Kiosk/media/수어 영상 mp4"
        
        os.makedirs(self.media_dir, exist_ok=True)
        
        self.expert_data = {}
        self.category_data = {}
        self.desc_data = {}
        
        if os.path.exists(self.json_path):
            with open(self.json_path, 'r', encoding='utf-8') as f: self.expert_data = json.load(f)
        if os.path.exists(self.json_category_path):
            with open(self.json_category_path, 'r', encoding='utf-8') as f: self.category_data = json.load(f)
        if os.path.exists(self.json_desc_path):
            with open(self.json_desc_path, 'r', encoding='utf-8') as f: self.desc_data = json.load(f)

        self.words = [
            "감사합니다", "괜찮다", "안녕하세요", "못생기다", "미안합니다", "사랑합니다", "정말로",
            "기다리다", "좋다", "만나다", "아니다", "그", "기역", "나", "나이", "남자", "너",
            "넷", "니은", "다섯", "돕다", "둘", "디귿", "리을", "산", "셋", "시옷", "십",
            "아홉", "여기", "여덟", "여섯", "여자", "열다섯", "열여덟", "이응", "일등", "지읒",
            "책", "치읓", "키읔", "티읕", "피읖", "필요", "하나", "핸드폰", "히읗"
        ]
        
        for saved_word in self.expert_data.keys():
            if saved_word not in self.words: self.words.append(saved_word)
        
        self.is_counting_down = False; self.countdown_start_time = 0
        self.is_recording = False; self.record_start_time = 0
        self.record_mode = None; self.sequence_data = []; self.recorded_frames = []
        self.current_state = "idle"; self.multi_sequence_data = []; self.shot_count = 0
        self.target_word = "" 
        
        self.last_pose = [0.0]*12
        self.last_lh = [0.0]*15
        self.last_rh = [0.0]*15
        self.last_rel = [0.0]*9
        self.last_rel_head = [0.0]*6
        self.last_torso = [0.0]*18 
        
        self.init_ui()
        self.init_camera()

    def init_camera(self):
        self.cap = None
        for backend in [cv2.CAP_ANY, cv2.CAP_V4L2]:
            if self.cap is not None: break
            for i in range(3):
                cap = cv2.VideoCapture(i, backend)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    cap.set(cv2.CAP_PROP_FPS, 30)
                    ret, frame = cap.read()
                    if ret and frame is not None: 
                        self.cap = cap
                        t_log("카메라", f"웹캠 연결 성공 (장치 인덱스 ID: {i})")
                        break
                    else: cap.release()
                else: cap.release()
            
        if self.cap is None:
            self.lbl_camera.setText("🚨 카메라 연결 오류 🚨\n기존 프로세스를 강제 종료(pkill -9 -f python)하거나 재부팅하세요.")
            self.lbl_camera.setStyleSheet("background-color: black; color: red; font-size: 24px; font-weight: bold;")
                
        self.timer = QTimer(); self.timer.timeout.connect(self.update_frame); self.timer.start(30)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_widget.setStyleSheet("background-color: #1e1e1e; font-family: 'NanumGothic';")

        self.kbd = VirtualHangulKeyboard(None)
        self.kbd.hide()

        top_bar = QHBoxLayout()
        self.btn_window = QPushButton("창 모드")
        self.btn_fullscreen = QPushButton("전체화면")
        self.btn_exit = QPushButton("종료하기")
        
        btn_style = "background-color: #008CBA; color: white; padding: 10px; font-size: 16px; font-weight: bold; border-radius: 5px;"
        for btn in [self.btn_window, self.btn_fullscreen]: btn.setStyleSheet(btn_style)
        self.btn_exit.setStyleSheet("background-color: #f44336; color: white; padding: 10px; font-size: 16px; font-weight: bold; border-radius: 5px;")
        
        self.btn_window.clicked.connect(self.showNormal)
        self.btn_fullscreen.clicked.connect(self.showFullScreen)
        
        # 💡 [핵심 패치]: 1-Click OS 강제 종료 함수 연결
        self.btn_exit.clicked.connect(self.close_app) 
        
        self.word_input = HangulLineEdit(self.kbd, self.add_new_word)
        self.word_input.setPlaceholderText("새 단어 입력 (터치 시 키보드 팝업)")
        self.word_input.setFixedHeight(45)
        self.word_input.setStyleSheet("background-color: white; color: black; font-size: 18px; padding: 10px; border-radius: 5px;")
        
        self.btn_add_word = QPushButton("새 단어 추가하기")
        self.btn_add_word.setFixedHeight(45)
        self.btn_add_word.setStyleSheet("background-color: #9C27B0; color: white; font-weight: bold; font-size: 18px; padding: 10px; border-radius: 5px;")
        self.btn_add_word.clicked.connect(self.add_new_word)
        
        top_bar.addWidget(self.btn_window); top_bar.addWidget(self.btn_fullscreen); top_bar.addWidget(self.btn_exit)
        top_bar.addSpacing(20)
        top_bar.addWidget(self.word_input, stretch=1); top_bar.addWidget(self.btn_add_word)
        main_layout.addLayout(top_bar)
        main_layout.addSpacing(10)

        center_layout = QHBoxLayout()
        
        left_panel = QVBoxLayout()
        filter_layout = QHBoxLayout()
        
        self.radio_general = QRadioButton("일상 수어")
        self.radio_industry = QRadioButton("산업/전문 수어")
        self.radio_general.setChecked(True)
        
        radio_style = """
            QRadioButton { color: white; font-size: 18px; font-weight: bold; padding: 5px; }
            QRadioButton::indicator { width: 15px; height: 15px; border-radius: 7px; background-color: #555; }
            QRadioButton::indicator:checked#gen { background-color: #4CAF50; border: 2px solid white; }
            QRadioButton::indicator:checked#ind { background-color: #FF9800; border: 2px solid white; }
        """
        self.radio_general.setObjectName("gen")
        self.radio_industry.setObjectName("ind")
        self.radio_general.setStyleSheet(radio_style)
        self.radio_industry.setStyleSheet(radio_style)

        self.category_group = QButtonGroup(self)
        self.category_group.addButton(self.radio_general)
        self.category_group.addButton(self.radio_industry)
        
        self.radio_general.clicked.connect(self.refresh_word_list)
        self.radio_industry.clicked.connect(self.refresh_word_list)
        
        filter_layout.addWidget(self.radio_general)
        filter_layout.addWidget(self.radio_industry)
        left_panel.addLayout(filter_layout)
        
        self.word_list = QListWidget()
        self.word_list.setStyleSheet("""
            QListWidget { background-color: #3a3a3a; color: white; font-size: 18px; padding: 5px; border-radius: 10px; }
            QListWidget::item { padding: 10px; border-bottom: 1px solid #555; }
            QListWidget::item:selected { background-color: #FF9800; color: white; font-weight: bold; border-radius: 5px;}
        """)
        self.word_list.itemClicked.connect(self.on_word_selected)
        left_panel.addWidget(self.word_list, stretch=1)
        
        self.btn_delete_word = QPushButton("선택 단어 삭제")
        self.btn_delete_word.setFixedHeight(45)
        self.btn_delete_word.setStyleSheet("background-color: #e53935; color: white; font-weight: bold; font-size: 16px; border-radius: 5px;")
        self.btn_delete_word.clicked.connect(self.delete_word)
        left_panel.addWidget(self.btn_delete_word)
        
        right_panel = QVBoxLayout()
        self.lbl_word_image = QLabel("단어를 선택하면 수형 이미지가 표출됩니다.")
        self.lbl_word_image.setAlignment(Qt.AlignCenter)
        self.lbl_word_image.setStyleSheet("background-color: #2b2b2b; border-radius: 10px; color: grey; font-size: 18px;")
        right_panel.addWidget(self.lbl_word_image, stretch=1)
        
        self.lbl_view_desc = QLabel("[수형 설명] 등록된 설명이 없습니다.")
        self.lbl_view_desc.setWordWrap(True)
        self.lbl_view_desc.setAlignment(Qt.AlignCenter)
        self.lbl_view_desc.setStyleSheet("font-size: 18px; font-weight: bold; color: #4CAF50; padding: 10px; background-color: #2b2b2b; border-radius: 10px;")
        right_panel.addWidget(self.lbl_view_desc)
        
        desc_box = QHBoxLayout()
        self.edit_word_desc = HangulLineEdit(self.kbd)
        self.edit_word_desc.setPlaceholderText("단어 선택 후 이곳에서 설명을 수정/저장하세요.")
        self.edit_word_desc.setFixedHeight(45)
        self.edit_word_desc.setStyleSheet("background-color: #e0f7fa; color: black; font-size: 16px; padding: 10px; border-radius: 5px;")
        
        self.btn_save_desc = QPushButton("설명 저장")
        self.btn_save_desc.setFixedHeight(45)
        self.btn_save_desc.setStyleSheet("background-color: #9C27B0; color: white; font-weight: bold; font-size: 16px; padding: 10px; border-radius: 5px;")
        self.btn_save_desc.clicked.connect(self.update_description)
        
        desc_box.addWidget(self.edit_word_desc, stretch=1)
        desc_box.addWidget(self.btn_save_desc)
        right_panel.addLayout(desc_box)
        right_panel.addWidget(self.kbd, stretch=0)
        
        center_layout.addLayout(left_panel, stretch=3)
        center_layout.addLayout(right_panel, stretch=7)
        main_layout.addLayout(center_layout, stretch=4)

        bottom_panel = QVBoxLayout()
        
        self.lbl_camera = QLabel("카메라 연결 중...")
        self.lbl_camera.setAlignment(Qt.AlignCenter)
        self.lbl_camera.setStyleSheet("background-color: black; border-radius: 10px; border: 2px solid #555;")
        self.lbl_camera.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        bottom_panel.addWidget(self.lbl_camera, stretch=1)
        
        self.lbl_status = QLabel("가이드라인에 맞추고 대기하세요. (단어 선택 필수)")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("font-size: 20px; font-weight: bold; color: #FFD700; background-color: #2b2b2b; padding: 10px; border-radius: 10px;")
        bottom_panel.addWidget(self.lbl_status)
        
        btn_record_layout = QHBoxLayout()
        self.btn_record_json = QPushButton("📝 정답지 3회 자동 촬영")
        self.btn_record_video = QPushButton("🎥 전문가 시연 영상 녹화")
        
        btn_rc_style = "QPushButton { background-color: #4CAF50; color: white; font-size: 20px; font-weight: bold; padding: 15px; border-radius: 10px; } QPushButton:disabled { background-color: #555555; color: #888888; }"
        btn_vid_style = "QPushButton { background-color: #2196F3; color: white; font-size: 20px; font-weight: bold; padding: 15px; border-radius: 10px; } QPushButton:disabled { background-color: #555555; color: #888888; }"
        
        self.btn_record_json.setStyleSheet(btn_rc_style)
        self.btn_record_video.setStyleSheet(btn_vid_style)
        
        self.btn_record_json.clicked.connect(lambda checked=False, m="json": self.start_recording(m))
        self.btn_record_video.clicked.connect(lambda checked=False, m="video": self.start_recording(m))
        
        self.btn_record_json.setEnabled(False)
        self.btn_record_video.setEnabled(False)
        
        btn_record_layout.addWidget(self.btn_record_json)
        btn_record_layout.addWidget(self.btn_record_video)
        bottom_panel.addLayout(btn_record_layout)

        main_layout.addLayout(bottom_panel, stretch=6)
        
        self.refresh_word_list()

    def refresh_word_list(self):
        self.word_list.blockSignals(True)
        self.word_list.clear()
        selected_cat = "industry" if self.radio_industry.isChecked() else "general"
        
        for w in self.words:
            cat = self.category_data.get(w, "general")
            if cat == selected_cat:
                self.word_list.addItem(w)
                
        self.word_list.blockSignals(False)

    def delete_word(self):
        item = self.word_list.currentItem()
        if not item:
            QMessageBox.warning(self, "선택 오류", "삭제할 단어를 먼저 리스트에서 선택하세요.")
            return
            
        del_word = item.text()
        reply = QMessageBox.question(self, '삭제 확인', f"정말로 '{del_word}' 단어와 관련된 모든 데이터를 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            if del_word in self.words: self.words.remove(del_word)
            if del_word in self.expert_data: del self.expert_data[del_word]
            if del_word in self.category_data: del self.category_data[del_word]
            if del_word in self.desc_data: del self.desc_data[del_word]
            
            try:
                with open(self.json_path, 'w', encoding='utf-8') as f: json.dump(self.expert_data, f, ensure_ascii=False, indent=4)
                with open(self.json_category_path, 'w', encoding='utf-8') as f: json.dump(self.category_data, f, ensure_ascii=False, indent=4)
                with open(self.json_desc_path, 'w', encoding='utf-8') as f: json.dump(self.desc_data, f, ensure_ascii=False, indent=4)
            except Exception as e:
                t_log("파일 에러", f"삭제 후 저장 실패: {e}")
                
            try:
                img_path = os.path.join(self.media_dir, f"{del_word}.jpg")
                vid_path = os.path.join(self.media_dir, f"{del_word}.mp4")
                if os.path.exists(img_path): os.remove(img_path)
                if os.path.exists(vid_path): os.remove(vid_path)
            except Exception: pass
                
            t_log("데이터삭제", f"[{del_word}] 단어 및 연관 데이터 완벽 삭제 완료")
            self.refresh_word_list()
            self.lbl_word_image.setText(f"[{del_word}] 단어가 삭제되었습니다.")
            self.lbl_view_desc.setText("[수형 설명] 등록된 설명이 없습니다.")
            self.edit_word_desc.clear()
            self.target_word = ""
            self.lbl_status.setText("가이드라인에 맞추고 대기하세요. (단어 선택 필수)")
            self.lbl_status.setStyleSheet("font-size: 20px; font-weight: bold; color: #FFD700; background-color: #2b2b2b; padding: 10px; border-radius: 10px;")
            self.btn_record_json.setEnabled(False)
            self.btn_record_video.setEnabled(False)

    def get_3d_direction(self, p1, p2):
        v = np.array([p2.x - p1.x, p2.y - p1.y, p2.z - p1.z])
        norm = np.linalg.norm(v)
        return (v / norm).tolist() if norm > 0 else [0.0, 0.0, 0.0]

    def extract_feature_vector(self, results):
        vec = []
        lms_pose = results.pose_landmarks.landmark if results.pose_landmarks else None
        lms_lh = results.left_hand_landmarks.landmark if results.left_hand_landmarks else None
        lms_rh = results.right_hand_landmarks.landmark if results.right_hand_landmarks else None

        if lms_pose:
            pose = []
            pose.extend(self.get_3d_direction(lms_pose[11], lms_pose[13])) 
            pose.extend(self.get_3d_direction(lms_pose[12], lms_pose[14])) 
            pose.extend(self.get_3d_direction(lms_pose[13], lms_pose[15])) 
            pose.extend(self.get_3d_direction(lms_pose[14], lms_pose[16])) 
            self.last_pose = pose
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
            rel = []
            rel.extend(self.get_3d_direction(lms_pose[15], lms_pose[16])) 
            rel.extend(self.get_3d_direction(center, lms_pose[15]))       
            rel.extend(self.get_3d_direction(center, lms_pose[16]))       
            self.last_rel = rel
            head = lms_pose[0]
            rel_head = []
            rel_head.extend(self.get_3d_direction(head, lms_pose[15]))
            rel_head.extend(self.get_3d_direction(head, lms_pose[16]))
            self.last_rel_head = rel_head
            sx = (lms_pose[11].x + lms_pose[12].x + lms_pose[23].x + lms_pose[24].x) / 4
            sy = (lms_pose[11].y + lms_pose[12].y + lms_pose[23].y + lms_pose[24].y) / 4
            sz = (lms_pose[11].z + lms_pose[12].z + lms_pose[23].z + lms_pose[24].z) / 4
            stomach = Point3D(sx, sy, sz)
            torso = []
            torso.extend(self.get_3d_direction(lms_pose[11], lms_pose[15])) 
            torso.extend(self.get_3d_direction(lms_pose[11], lms_pose[16])) 
            torso.extend(self.get_3d_direction(lms_pose[12], lms_pose[15])) 
            torso.extend(self.get_3d_direction(lms_pose[12], lms_pose[16])) 
            torso.extend(self.get_3d_direction(stomach, lms_pose[15]))      
            torso.extend(self.get_3d_direction(stomach, lms_pose[16]))      
            self.last_torso = torso
        vec.extend(self.last_rel); vec.extend(self.last_rel_head); vec.extend(self.last_torso)
        return vec 

    def add_new_word(self):
        new_word = self.word_input.text().strip()
        selected_category = "industry" if self.radio_industry.isChecked() else "general"
        
        if new_word:
            if new_word not in self.words: self.words.insert(0, new_word)
            
            self.category_data[new_word] = selected_category
            try:
                with open(self.json_category_path, 'w', encoding='utf-8') as f:
                    json.dump(self.category_data, f, ensure_ascii=False, indent=4)
            except Exception as e: t_log("에러", str(e))
            
            if new_word not in self.desc_data: self.desc_data[new_word] = ""
                
            self.refresh_word_list()
            items = self.word_list.findItems(new_word, Qt.MatchExactly)
            if items:
                self.word_list.setCurrentItem(items[0])
                self.on_word_selected(items[0])
            
            self.word_input.clear(); self.kbd.buffer.clear(); self.kbd.hide() 
        else:
            QMessageBox.warning(self, "입력 오류", "추가할 단어를 입력하세요.")

    def update_description(self):
        if not hasattr(self, 'target_word') or not self.target_word: return
        new_desc = self.edit_word_desc.text().strip()
        self.desc_data[self.target_word] = new_desc
        try:
            with open(self.json_desc_path, 'w', encoding='utf-8') as f:
                json.dump(self.desc_data, f, ensure_ascii=False, indent=4)
            t_log("데이터저장", f"[{self.target_word}] 수형 설명 갱신 완료")
            self.lbl_view_desc.setText(f"[수형 설명] {new_desc}" if new_desc else "[수형 설명] 등록된 설명이 없습니다.")
            QMessageBox.information(self, "저장 완료", f"[{self.target_word}] 설명이 성공적으로 반영되었습니다.")
            self.kbd.hide()
        except Exception as e:
            QMessageBox.warning(self, "저장 실패", f"설명 저장 중 에러가 발생했습니다: {e}")

    def on_word_selected(self, item):
        self.target_word = item.text()
        self.lbl_status.setText(f"선택된 단어: [{self.target_word}] - 하단의 녹화 버튼을 눌러 작업을 시작하세요.")
        self.lbl_status.setStyleSheet("font-size: 22px; font-weight: bold; color: white; background-color: #E91E63; padding: 10px; border-radius: 5px;")
        
        self.btn_record_json.setEnabled(True)
        self.btn_record_video.setEnabled(True)
        self.kbd.hide()

        desc = self.desc_data.get(self.target_word, "")
        self.edit_word_desc.setText(desc)
        self.lbl_view_desc.setText(f"[수형 설명] {desc}" if desc else "[수형 설명] 등록된 설명이 없습니다.")
        
        img_path = os.path.join(self.media_dir, f"{self.target_word}.jpg")
        if os.path.exists(img_path):
            pixmap = QPixmap(img_path)
            self.lbl_word_image.setPixmap(pixmap.scaled(450, 350, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.lbl_word_image.setText(f"[{self.target_word}]\n저장된 시연 이미지가 없습니다.")

    def start_recording(self, r_type):
        if self.cap is None or not self.cap.isOpened():
            QMessageBox.critical(self, "카메라 오류", "카메라 화면이 보이지 않습니다.\n터미널 창을 닫고 다시 실행하세요.")
            return
            
        self.record_mode = r_type
        self.current_word = self.target_word
        
        self.last_pose = [0.0]*12
        self.last_lh = [0.0]*15
        self.last_rh = [0.0]*15
        self.last_rel = [0.0]*9
        self.last_rel_head = [0.0]*6
        self.last_torso = [0.0]*18 

        self.is_counting_down = True
        self.countdown_start_time = time.time()
        self.sequence_data = []
        self.recorded_frames = []
        self.multi_sequence_data = [] 
        self.shot_count = 1 
        
        self.btn_record_json.setEnabled(False)
        self.btn_record_video.setEnabled(False)
        self.kbd.hide()
        
        if r_type == "json":
            self.wait_time = 3; self.rec_time = 2.0
            t_log("레코딩", f"[{self.current_word}] 정답지 뼈대 데이터 녹화 준비 (3초 대기)")
        elif r_type == "video":
            self.wait_time = 2; self.rec_time = 3.0
            t_log("레코딩", f"[{self.current_word}] 시연 영상 녹화 준비 (2초 대기)")

    def update_frame(self):
        if self.cap is None or not self.cap.isOpened(): return
        
        ret, frame = self.cap.read()
        if not ret: return
        
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        run_ai = True
        if self.is_recording and self.record_mode == "video": run_ai = False
            
        results = None
        if run_ai:
            results = self.holistic.process(rgb_frame)
            if results.pose_landmarks: self.mp_drawing.draw_landmarks(rgb_frame, results.pose_landmarks, mp_holistic.POSE_CONNECTIONS)
            if results.left_hand_landmarks: self.mp_drawing.draw_landmarks(rgb_frame, results.left_hand_landmarks, mp_holistic.HAND_CONNECTIONS)
            if results.right_hand_landmarks: self.mp_drawing.draw_landmarks(rgb_frame, results.right_hand_landmarks, mp_holistic.HAND_CONNECTIONS)

        if self.is_counting_down:
            elapsed_cd = time.time() - self.countdown_start_time
            remain_cd = self.wait_time - int(elapsed_cd)
            
            if elapsed_cd >= self.wait_time:
                self.is_counting_down = False
                self.is_recording = True
                self.sequence_data = [] 
                self.recorded_frames = [] 
                self.record_start_time = time.time()
                
                if self.current_state != "recording":
                    self.current_state = "recording"
                    if self.record_mode == "json": self.lbl_status.setText(f"🔴 [{self.current_word}] {self.shot_count}/3 회차 녹화 중! ({int(self.rec_time)}초) 동작을 맺어주세요.")
                    else: self.lbl_status.setText(f"🔴 [{self.current_word}] 영상 녹화 중! ({int(self.rec_time)}초) 동작을 맺어주세요.")
                    self.lbl_status.setStyleSheet("font-size: 24px; font-weight: bold; color: white; background-color: #f44336; padding: 15px; border-radius: 10px;")
            else:
                if self.current_state != f"countdown_{remain_cd}": self.current_state = f"countdown_{remain_cd}"
                self.lbl_status.setText(f"⏳ 삐- {remain_cd}초 뒤 녹화가 시작됩니다!")

        if self.is_recording:
            if self.record_mode == "json" and results:
                self.sequence_data.append(self.extract_feature_vector(results))
            elif self.record_mode == "video":
                self.recorded_frames.append(frame.copy()) 
            
            elapsed = time.time() - self.record_start_time
            if elapsed >= self.rec_time:
                self.current_state = "idle"
                if self.record_mode == "json":
                    self.multi_sequence_data.append(self.sequence_data)
                    if self.shot_count < 3:
                        self.shot_count += 1
                        self.is_recording = False
                        self.is_counting_down = True
                        self.countdown_start_time = time.time()
                        self.sequence_data = [] 
                    else: self.finish_recording()
                else: self.finish_recording()

        final_frame = cv2.flip(rgb_frame, 1)
        h, w, ch = final_frame.shape
        
        if self.is_counting_down:
            cv2.rectangle(final_frame, (int(w*0.02), int(h*0.02)), (int(w*0.98), int(h*0.98)), (255, 165, 0), 4)
            remain_cd = self.wait_time - int(time.time() - self.countdown_start_time)
            text_size = cv2.getTextSize(str(max(1, remain_cd)), cv2.FONT_HERSHEY_SIMPLEX, 5, 10)[0]
            cv2.putText(final_frame, str(max(1, remain_cd)), ((w - text_size[0]) // 2, (h + text_size[1]) // 2), cv2.FONT_HERSHEY_SIMPLEX, 5, (255, 165, 0), 10, cv2.LINE_AA)
        elif self.is_recording: cv2.rectangle(final_frame, (int(w*0.02), int(h*0.02)), (int(w*0.98), int(h*0.98)), (255, 0, 0), 4)
        else: cv2.rectangle(final_frame, (int(w*0.02), int(h*0.02)), (int(w*0.98), int(h*0.98)), (0, 255, 0), 2)
        
        center_x, head_y, head_r_x, head_r_y = int(w / 2), int(h * 0.25), int(w * 0.08), int(h * 0.15)
        shoulder_y, shoulder_w = int(h * 0.60), int(w * 0.28)
        
        cv2.ellipse(final_frame, (center_x, head_y), (head_r_x, head_r_y), 0, 0, 360, (255, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(final_frame, "HEAD", (center_x - 30, head_y - head_r_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2, cv2.LINE_AA)
        cv2.line(final_frame, (center_x - shoulder_w, shoulder_y), (center_x + shoulder_w, shoulder_y), (255, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(final_frame, "SHOULDER", (center_x - 55, shoulder_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2, cv2.LINE_AA)
        
        hand_y, hand_offset, hand_r = int(h * 0.88), int(w * 0.21), int(w * 0.045)
        cv2.circle(final_frame, (center_x - hand_offset, hand_y), hand_r, (255, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(final_frame, "L-HAND", (center_x - hand_offset - 30, hand_y - hand_r - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 2, cv2.LINE_AA)
        cv2.circle(final_frame, (center_x + hand_offset, hand_y), hand_r, (255, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(final_frame, "R-HAND", (center_x + hand_offset - 30, hand_y - hand_r - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 2, cv2.LINE_AA)
        
        q_img = QImage(final_frame.data, w, h, ch * w, QImage.Format_RGB888)
        if self.lbl_camera.width() > 0:
            self.lbl_camera.setPixmap(QPixmap.fromImage(q_img).scaled(self.lbl_camera.width(), self.lbl_camera.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resample_sequence(self, seq, target_len=30):
        if seq is None or len(seq) < 2: return None
        seq_arr = np.array(seq, dtype=np.float32)
        if len(seq_arr.shape) != 2 or seq_arr.shape[1] != 75: return None 
        if seq_arr.shape[0] == target_len: return seq_arr
        resampled, orig_idx, target_idx = np.zeros((target_len, 75), dtype=np.float32), np.linspace(0, 1, seq_arr.shape[0]), np.linspace(0, 1, target_len)
        for d in range(75): resampled[:, d] = np.interp(target_idx, orig_idx, seq_arr[:, d])
        return resampled

    def finish_recording(self):
        self.is_recording = False
        QTimer.singleShot(100, self.prompt_save)

    def prompt_save(self):
        if self.record_mode == "json":
            reply = QMessageBox.question(self, '저장 확인', f"'{self.current_word}' 정답지(멀티 템플릿)를 저장할까요?", QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes: self.save_json_data()
            else:
                self.lbl_status.setText(f"ℹ️ [{self.current_word}] 정답지 저장이 취소되었습니다.")
                self.lbl_status.setStyleSheet("font-size: 22px; font-weight: bold; color: white; background-color: #555555; padding: 15px; border-radius: 10px;")
        elif self.record_mode == "video":
            reply = QMessageBox.question(self, '저장 확인', f"'{self.current_word}' 전문가 시연 영상을 저장할까요?", QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes: self.save_video_data()
            else:
                self.lbl_status.setText(f"ℹ️ [{self.current_word}] 영상 저장이 취소되었습니다.")
                self.lbl_status.setStyleSheet("font-size: 22px; font-weight: bold; color: white; background-color: #555555; padding: 15px; border-radius: 10px;")

        self.btn_record_json.setEnabled(True)
        self.btn_record_video.setEnabled(True)

    def save_json_data(self):
        saved_templates = []
        for seq in self.multi_sequence_data:
            resampled_seq = self.resample_sequence(seq, 30)
            if resampled_seq is not None:
                saved_templates.append(resampled_seq.tolist())
        
        if len(saved_templates) > 0:
            self.expert_data[self.current_word] = saved_templates
            try:
                with open(self.json_path, "w", encoding="utf-8") as f:
                    json.dump(self.expert_data, f, ensure_ascii=False, indent=4)
                self.lbl_status.setText(f"✅ [{self.current_word}] 정답지 저장 완료!")
                self.lbl_status.setStyleSheet("font-size: 22px; font-weight: bold; color: white; background-color: #4CAF50; padding: 15px; border-radius: 10px;")
            except Exception: pass
        else:
            self.lbl_status.setText(f"❌ [{self.current_word}] 녹화 실패 (데이터 추출 오류)")
            self.lbl_status.setStyleSheet("font-size: 22px; font-weight: bold; color: white; background-color: #f44336; padding: 15px; border-radius: 10px;")

    def save_video_data(self):
        if self.recorded_frames:
            try:
                actual_fps = len(self.recorded_frames) / self.rec_time
                if actual_fps < 5.0: actual_fps = 30.0 
                video_path = os.path.join(self.media_dir, f"{self.current_word}.mp4")
                h, w, _ = self.recorded_frames[0].shape
                out = cv2.VideoWriter(video_path, cv2.VideoWriter_fourcc(*'mp4v'), actual_fps, (w, h))
                for f in self.recorded_frames: out.write(f)
                out.release()
                cv2.imwrite(os.path.join(self.media_dir, f"{self.current_word}.jpg"), self.recorded_frames[0])
                
                self.on_word_selected(self.word_list.currentItem())
                self.lbl_status.setText(f"✅ [{self.current_word}] 시연 영상 저장 완료!")
                self.lbl_status.setStyleSheet("font-size: 22px; font-weight: bold; color: white; background-color: #4CAF50; padding: 15px; border-radius: 10px;")
            except Exception: pass
        else:
            self.lbl_status.setText(f"❌ [{self.current_word}] 저장할 프레임이 없습니다.")
            self.lbl_status.setStyleSheet("font-size: 22px; font-weight: bold; color: white; background-color: #f44336; padding: 15px; border-radius: 10px;")

    # 💡 [핵심 패치]: 프로그램 종료 시 시스템 레벨 강제 종료 적용 (카메라 완전 반환)
    def close_app(self):
        t_log("시스템", "프로그램 1-Click 강제 종료 시퀀스 가동")
        self.timer.stop()
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
            t_log("시스템", "카메라 자원 반환 완료")
        time.sleep(0.5) # 라즈베리파이 OS가 카메라 자원을 완전히 회수할 시간 보장
        os._exit(0)

    def closeEvent(self, event):
        self.close_app()

if __name__ == '__main__':
    if "DISPLAY" not in os.environ: os.environ["DISPLAY"] = ":0"
    app = QApplication(sys.argv)
    ex = GroundTruthStudio()
    ex.show()
    sys.exit(app.exec_())