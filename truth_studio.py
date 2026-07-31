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
                             QHBoxLayout, QPushButton, QListWidget, QLabel, QMessageBox, QSizePolicy, QLineEdit)
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
        if state == 1:
            result += CHO[cho_idx]
        elif state == 2 or state == 3:
            result += chr(0xAC00 + (cho_idx * 21 * 28) + (jung_idx * 28) + jong_idx)
        cho_idx, jung_idx, jong_idx = -1, -1, 0
        state = 0

    i = 0
    while i < len(jamos):
        j = jamos[i]
        if j == " ":
            flush()
            result += " "
            i += 1
            continue
            
        is_cho = j in CHO
        is_jung = j in JUNG
        
        if state == 0:
            if is_cho:
                cho_idx = CHO.index(j)
                state = 1
            elif is_jung:
                result += j
            else:
                result += j
        elif state == 1:
            if is_jung:
                jung_idx = JUNG.index(j)
                state = 2
            elif is_cho:
                flush()
                cho_idx = CHO.index(j)
                state = 1
            else:
                flush()
                result += j
        elif state == 2:
            if is_jung:
                combined = JUNG[jung_idx] + j
                if combined in COMPLEX_JUNG:
                    jung_idx = JUNG.index(COMPLEX_JUNG[combined])
                else:
                    flush()
                    result += j
            elif is_cho:
                if j in JONG:
                    if i + 1 < len(jamos) and jamos[i+1] in JUNG:
                        flush()
                        cho_idx = CHO.index(j)
                        state = 1
                    else:
                        jong_idx = JONG.index(j)
                        state = 3
                else:
                    flush()
                    cho_idx = CHO.index(j)
                    state = 1
            else:
                flush()
                result += j
        elif state == 3:
            if is_cho:
                combined = JONG[jong_idx] + j
                if combined in COMPLEX_JONG:
                    if i + 1 < len(jamos) and jamos[i+1] in JUNG:
                        flush()
                        cho_idx = CHO.index(j)
                        state = 1
                    else:
                        jong_idx = JONG.index(COMPLEX_JONG[combined])
                else:
                    flush()
                    cho_idx = CHO.index(j)
                    state = 1
            elif is_jung:
                prev_jong = JONG[jong_idx]
                jong_chars = ""
                for k, v in COMPLEX_JONG.items():
                    if v == prev_jong:
                        jong_chars = k
                        break
                if jong_chars:
                    jong_idx = JONG.index(jong_chars[0])
                    flush()
                    cho_idx = CHO.index(jong_chars[1])
                else:
                    jong_idx = 0
                    flush()
                    cho_idx = CHO.index(prev_jong)
                jung_idx = JUNG.index(j)
                state = 2
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
        
        keys_normal = [
            ['ㅂ', 'ㅈ', 'ㄷ', 'ㄱ', 'ㅅ', 'ㅛ', 'ㅕ', 'ㅑ', 'ㅐ', 'ㅔ'],
            ['ㅁ', 'ㄴ', 'ㅇ', 'ㄹ', 'ㅎ', 'ㅗ', 'ㅓ', 'ㅏ', 'ㅣ'],
            ['Shift', 'ㅋ', 'ㅌ', 'ㅊ', 'ㅍ', 'ㅠ', 'ㅜ', 'ㅡ', '지우기']
        ]
        keys_shift = [
            ['ㅃ', 'ㅉ', 'ㄸ', 'ㄲ', 'ㅆ', 'ㅛ', 'ㅕ', 'ㅑ', 'ㅒ', 'ㅖ'],
            ['ㅁ', 'ㄴ', 'ㅇ', 'ㄹ', 'ㅎ', 'ㅗ', 'ㅓ', 'ㅏ', 'ㅣ'],
            ['Shift', 'ㅋ', 'ㅌ', 'ㅊ', 'ㅍ', 'ㅠ', 'ㅜ', 'ㅡ', '지우기']
        ]
        
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
        
        bottom_layout.addWidget(clear_btn, 1)
        bottom_layout.addWidget(space_btn, 2)
        bottom_layout.addWidget(close_btn, 1)
        self.layout.addLayout(bottom_layout)

    def on_key(self, r, c):
        if not self.target: return
        key = self.keys_shift[r][c] if self.is_shift else self.keys_normal[r][c]
        if key == 'Shift':
            self.is_shift = not self.is_shift
            self.update_ui()
        elif key == '지우기':
            if self.buffer:
                self.buffer.pop()
                self.update_target()
            else:
                self.base_text = self.target.text()[:-1]
                self.update_target()
        else:
            self.buffer.append(key)
            if self.is_shift:
                self.is_shift = False
                self.update_ui()
            self.update_target()
            
    def on_key_str(self, action):
        if not self.target: return
        if action == " ":
            self.buffer.append(" ")
            self.update_target()
        elif action == "Clear":
            self.buffer.clear()
            self.base_text = ""
            self.update_target()
        elif action == "Backspace":
            if self.buffer:
                self.buffer.pop()
                self.update_target()
        else:
            self.buffer.append(action)
            self.update_target()

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
        if self.kbd_ref.target != self:
            self.kbd_ref.target = self
            self.kbd_ref.buffer = []
            self.kbd_ref.base_text = self.text()
        self.kbd_ref.show()
        self.setFocus()
        super().mousePressEvent(event)
        
    def keyPressEvent(self, event):
        if self.kbd_ref.target != self:
            self.kbd_ref.target = self
            self.kbd_ref.buffer = []
            self.kbd_ref.base_text = self.text()
            
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            if self.enter_callback:
                self.enter_callback()
        else:
            key = event.text()
            if key in self.eng_to_kor: 
                self.kbd_ref.on_key_str(self.eng_to_kor[key])
            elif event.key() == Qt.Key_Backspace: 
                if len(self.kbd_ref.buffer) > 0:
                    self.kbd_ref.on_key_str("Backspace")
                else:
                    super().keyPressEvent(event)
                    self.kbd_ref.base_text = self.text() 
            elif event.key() == Qt.Key_Space: 
                self.kbd_ref.on_key_str(" ")
            else: 
                super().keyPressEvent(event)
                self.kbd_ref.base_text = self.text()

class GroundTruthStudio(QMainWindow):
    def __init__(self):
        super().__init__()
        
        t_log("초기화", "==================================================")
        t_log("초기화", "수동 정답지 레코딩 스튜디오 PRO 시스템 가동 시작")
        t_log("초기화", "==================================================")
        
        self.setWindowTitle("수동 정답지 레코딩 스튜디오 PRO")
        self.resize(1024, 600)
        self.showFullScreen()
        
        t_log("초기화", "MediaPipe 비전 엔진 로드 중...")
        self.holistic = mp_holistic.Holistic(min_detection_confidence=0.5, min_tracking_confidence=0.5)
        self.mp_drawing = mp.solutions.drawing_utils
        self.json_path = "/home/a/Sign_Kiosk/dynamic_sign_model.json"
        
        self.json_desc_path = "/home/a/Sign_Kiosk/dynamic_sign_desc.json"
        self.media_dir = "/home/a/Sign_Kiosk/media/수어 영상 mp4"
        
        os.makedirs(self.media_dir, exist_ok=True)
        t_log("파일시스템", f"미디어 저장 폴더 확인 완료: {self.media_dir}")
        
        if os.path.exists(self.json_path):
            t_log("파일시스템", f"기존 정답지 JSON 파일 읽기 시도: {self.json_path}")
            with open(self.json_path, 'r', encoding='utf-8') as f:
                self.expert_data = json.load(f)
        else:
            t_log("파일시스템", "기존 JSON 정답지 없음. 새로 생성을 준비합니다.")
            self.expert_data = {}

        self.words = [
            "감사합니다", "괜찮다", "안녕하세요", "못생기다", "미안합니다", "사랑합니다", "정말로",
            "기다리다", "좋다", "만나다", "아니다", "그", "기역", "나", "나이", "남자", "너",
            "넷", "니은", "다섯", "돕다", "둘", "디귿", "리을", "산", "셋", "시옷", "십",
            "아홉", "여기", "여덟", "여섯", "여자", "열다섯", "열여덟", "이응", "일등", "지읒",
            "책", "치읓", "키읔", "티읕", "피읖", "필요", "하나", "핸드폰", "히읗"
        ]
        
        new_count = 0
        for saved_word in self.expert_data.keys():
            if saved_word not in self.words:
                self.words.append(saved_word)
                new_count += 1
        t_log("데이터로드", f"기본 단어 세트 로드 완료. (JSON에서 발견된 추가 단어: {new_count}개)")
        
        self.is_counting_down = False
        self.countdown_start_time = 0
        self.is_recording = False
        self.record_start_time = 0
        self.record_mode = None  
        self.sequence_data = []
        self.recorded_frames = [] 
        self.current_state = "idle" 
        
        self.last_pose = [0.0]*12
        self.last_lh = [0.0]*15
        self.last_rh = [0.0]*15
        self.last_rel = [0.0]*9
        self.last_rel_head = [0.0]*6
        self.last_torso = [0.0]*18 
        
        self.init_ui()
        self.init_camera()
        t_log("초기화", "정답지 스튜디오 UI 렌더링 및 모든 준비 완료")

    def init_camera(self):
        t_log("시스템", "카메라 스캔 및 비디오 스트림 연결 프로세스 시작...")
        self.cap = None
        for i in range(4):
            cap = cv2.VideoCapture(i, cv2.CAP_V4L2)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 30)
                ret, _ = cap.read()
                if ret:
                    self.cap = cap
                    t_log("카메라", f"웹캠 연결 성공 (장치 인덱스 ID: {i})")
                    break
                else: cap.release()
            else: cap.release()
            
        if self.cap is None:
            t_log("카메라에러", "사용 가능한 웹캠을 찾을 수 없습니다.")
            
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_widget.setStyleSheet("background-color: #1e1e1e; font-family: 'NanumGothic';")

        self.kbd = VirtualHangulKeyboard(None)
        self.kbd.hide()

        top_row1 = QHBoxLayout()
        
        self.btn_window = QPushButton("창 모드")
        self.btn_fullscreen = QPushButton("전체화면")
        self.btn_exit = QPushButton("종료하기")
        
        btn_style = "background-color: #008CBA; color: white; padding: 10px 20px; font-size: 14px; font-weight: bold; border-radius: 5px;"
        for btn in [self.btn_window, self.btn_fullscreen]:
            btn.setStyleSheet(btn_style)
        self.btn_exit.setStyleSheet("background-color: #f44336; color: white; padding: 10px 20px; font-size: 14px; font-weight: bold; border-radius: 5px;")
        
        self.btn_window.clicked.connect(lambda: self.showNormal())
        self.btn_fullscreen.clicked.connect(lambda: self.showFullScreen())
        self.btn_exit.clicked.connect(lambda: self.close())
        
        self.word_input = HangulLineEdit(self.kbd, self.add_new_word)
        self.word_input.setPlaceholderText("새로운 단어 입력 (마우스 클릭 시 터치 키보드 나옴)")
        self.word_input.setFixedHeight(45)
        self.word_input.setStyleSheet("background-color: white; color: black; font-size: 16px; padding: 10px; border-radius: 5px;")
        
        self.btn_add_word = QPushButton("새 단어 추가하기")
        self.btn_add_word.setFixedHeight(45)
        self.btn_add_word.setStyleSheet("background-color: #9C27B0; color: white; padding: 10px 20px; font-size: 16px; font-weight: bold; border-radius: 5px;")
        self.btn_add_word.clicked.connect(self.add_new_word)
        
        top_row1.addWidget(self.btn_window)
        top_row1.addWidget(self.btn_fullscreen)
        top_row1.addWidget(self.btn_exit)
        top_row1.addSpacing(30)
        top_row1.addWidget(self.word_input, stretch=1)
        top_row1.addWidget(self.btn_add_word)
        
        top_row2 = QHBoxLayout()
        self.desc_input = HangulLineEdit(self.kbd, self.add_new_word)
        self.desc_input.setPlaceholderText("수형 설명을 상세히 입력하세요 (단어 리스트 선택 후 설명 추가 가능)")
        self.desc_input.setFixedHeight(45)
        self.desc_input.setStyleSheet("background-color: #e0f7fa; color: black; font-size: 16px; padding: 10px; border-radius: 5px;")
        top_row2.addWidget(self.desc_input)

        main_layout.addLayout(top_row1)
        main_layout.addLayout(top_row2)
        main_layout.addSpacing(15)

        bottom_layout = QHBoxLayout()
        
        left_panel = QVBoxLayout()
        lbl_list = QLabel("정답지 갱신 및 추가 (단어 선택 시 동작 덮어쓰기)")
        lbl_list.setStyleSheet("color: #4CAF50; font-size: 16px; font-weight: bold;")
        
        self.word_list = QListWidget()
        self.word_list.addItems(self.words)
        self.word_list.setStyleSheet("""
            QListWidget { background-color: #3a3a3a; color: white; font-size: 20px; padding: 10px; border-radius: 10px; }
            QListWidget::item { padding: 15px; border-bottom: 1px solid #555; }
            QListWidget::item:selected { background-color: #ff9800; color: white; font-weight: bold; }
        """)
        self.word_list.itemClicked.connect(self.on_word_selected)
        
        left_panel.addWidget(lbl_list)
        left_panel.addWidget(self.word_list, stretch=1)
        
        right_panel = QVBoxLayout()
        
        self.lbl_camera = QLabel("카메라 연결 중...")
        self.lbl_camera.setAlignment(Qt.AlignCenter)
        self.lbl_camera.setStyleSheet("background-color: black; border-radius: 10px;")
        self.lbl_camera.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        
        self.lbl_status = QLabel("노란색 가이드라인에 머리와 어깨를 맞추고 대기하세요.")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("font-size: 22px; font-weight: bold; color: #FFD700; background-color: #2b2b2b; padding: 15px; border-radius: 10px;")
        
        btn_record_layout = QHBoxLayout()
        self.btn_record_json = QPushButton("📝 정답지 만들기\n(3초 대기 + 2초 캡처)")
        self.btn_record_json.setStyleSheet("background-color: #4CAF50; color: white; font-size: 20px; font-weight: bold; padding: 15px; border-radius: 10px;")
        self.btn_record_json.clicked.connect(lambda: self.start_recording("json"))
        
        self.btn_record_video = QPushButton("🎥 전문가 영상 녹화\n(2초 대기 + 3초 녹화)")
        self.btn_record_video.setStyleSheet("background-color: #2196F3; color: white; font-size: 20px; font-weight: bold; padding: 15px; border-radius: 10px;")
        self.btn_record_video.clicked.connect(lambda: self.start_recording("video"))
        
        self.btn_record_json.setEnabled(False)
        self.btn_record_video.setEnabled(False)
        
        btn_record_layout.addWidget(self.btn_record_json)
        btn_record_layout.addWidget(self.btn_record_video)
        
        right_panel.addWidget(self.kbd) 
        right_panel.addWidget(self.lbl_camera, stretch=1)
        right_panel.addWidget(self.lbl_status)
        right_panel.addLayout(btn_record_layout)

        bottom_layout.addLayout(left_panel, 3)
        bottom_layout.addLayout(right_panel, 7)
        
        main_layout.addLayout(bottom_layout, stretch=1)

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
            cx = (lms_pose[11].x + lms_pose[12].x) / 2
            cy = (lms_pose[11].y + lms_pose[12].y) / 2
            cz = (lms_pose[11].z + lms_pose[12].z) / 2
            class Point3D:
                def __init__(self, x, y, z):
                    self.x = x; self.y = y; self.z = z
            center = Point3D(cx, cy, cz)
            
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
            
        vec.extend(self.last_rel)
        vec.extend(self.last_rel_head)
        vec.extend(self.last_torso)

        return vec 

    def add_new_word(self):
        new_word = self.word_input.text().strip()
        new_desc = self.desc_input.text().strip()
        
        t_log("사용자조작", f"'단어 추가' 버튼 클릭. (단어: '{new_word}', 설명: '{new_desc}')")
        
        if new_word:
            if new_word not in self.words:
                self.words.insert(0, new_word)
                self.word_list.insertItem(0, new_word)
                self.word_list.setCurrentRow(0)
                t_log("데이터갱신", f"새로운 단어 '{new_word}'가 학습 목록에 등록되었습니다.")
            else:
                t_log("시스템경고", f"단어 병합: '{new_word}'는 이미 존재하는 단어입니다. 설명을 덮어씁니다.")
                items = self.word_list.findItems(new_word, Qt.MatchExactly)
                if items: self.word_list.setCurrentItem(items[0])
            
            if new_desc:
                try:
                    desc_data = {}
                    if os.path.exists(self.json_desc_path):
                        with open(self.json_desc_path, 'r', encoding='utf-8') as f:
                            desc_data = json.load(f)
                    desc_data[new_word] = new_desc
                    with open(self.json_desc_path, 'w', encoding='utf-8') as f:
                        json.dump(desc_data, f, ensure_ascii=False, indent=4)
                    t_log("파일시스템", f"'{new_word}'의 수형 설명이 저장되었습니다.")
                except Exception as e:
                    t_log("설명 저장 에러", str(e))
                
            self.on_word_selected(self.word_list.currentItem())
            
            self.word_input.clear()
            self.desc_input.clear()
            self.kbd.buffer.clear()
            self.kbd.hide() 
        else:
            t_log("시스템경고", "단어 추가 실패: 입력란이 비어있습니다.")

    def on_word_selected(self, item):
        self.target_word = item.text()
        self.lbl_status.setText(f"선택된 단어: [{self.target_word}] - 버튼을 눌러 작업을 시작하세요.")
        self.lbl_status.setStyleSheet("font-size: 24px; font-weight: bold; color: white; background-color: #E91E63; padding: 10px; border-radius: 5px;")
        self.btn_record_json.setEnabled(True)
        self.btn_record_video.setEnabled(True)
        
        self.word_input.setText(self.target_word)
        self.kbd.hide()

    def start_recording(self, r_type):
        self.record_mode = r_type
        self.current_word = self.target_word
        
        self.is_counting_down = True
        self.countdown_start_time = time.time()
        self.sequence_data = []
        self.recorded_frames = []
        self.btn_record_json.setEnabled(False)
        self.btn_record_video.setEnabled(False)
        self.kbd.hide()
        
        if r_type == "json":
            self.wait_time = 3
            self.rec_time = 2.0
            t_log("레코딩", f"[{self.current_word}] 정답지 뼈대 데이터(JSON) 녹화 준비 중... (3초 대기)")
        elif r_type == "video":
            self.wait_time = 2
            self.rec_time = 3.0
            t_log("레코딩", f"[{self.current_word}] 전문가 시연 영상(MP4) 녹화 준비 중... (2초 대기)")

    def update_frame(self):
        if self.cap is None or not self.cap.isOpened(): return
        
        ret, frame = self.cap.read()
        if not ret: return
        
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        run_ai = True
        if self.is_recording and self.record_mode == "video":
            run_ai = False
            
        results = None
        if run_ai:
            results = self.holistic.process(rgb_frame)
            if results.pose_landmarks:
                self.mp_drawing.draw_landmarks(rgb_frame, results.pose_landmarks, mp_holistic.POSE_CONNECTIONS)
            if results.left_hand_landmarks:
                self.mp_drawing.draw_landmarks(rgb_frame, results.left_hand_landmarks, mp_holistic.HAND_CONNECTIONS)
            if results.right_hand_landmarks:
                self.mp_drawing.draw_landmarks(rgb_frame, results.right_hand_landmarks, mp_holistic.HAND_CONNECTIONS)

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
                    t_log("레코딩", f"🔴 카운트다운 완료. [{self.current_word}] 녹화 시작 ({int(self.rec_time)}초)")
                    
                self.lbl_status.setText(f"🔴 [{self.current_word}] 녹화 중! ({int(self.rec_time)}초) 동작을 확실하게 맺어주세요.")
                self.lbl_status.setStyleSheet("font-size: 24px; font-weight: bold; color: white; background-color: #f44336; padding: 15px; border-radius: 10px;")
            else:
                if self.current_state != f"countdown_{remain_cd}":
                    self.current_state = f"countdown_{remain_cd}"
                    t_log("레코딩", f"⏳ 녹화 시작 전 카운트다운: {remain_cd}초 남음")
                self.lbl_status.setText(f"⏳ 삐- {remain_cd}초 뒤 녹화가 시작됩니다!")

        if self.is_recording:
            if self.record_mode == "json" and results:
                feature = self.extract_feature_vector(results)
                self.sequence_data.append(feature)
            elif self.record_mode == "video":
                self.recorded_frames.append(frame.copy()) 
            
            elapsed = time.time() - self.record_start_time
            if elapsed >= self.rec_time:
                self.current_state = "idle"
                self.finish_recording()

        final_frame = cv2.flip(rgb_frame, 1)
        h, w, ch = final_frame.shape
        
        if self.is_counting_down:
            box_color = (255, 165, 0) 
            cv2.rectangle(final_frame, (int(w*0.02), int(h*0.02)), (int(w*0.98), int(h*0.98)), box_color, 4)
            remain_cd = self.wait_time - int(time.time() - self.countdown_start_time)
            text = str(max(1, remain_cd))
            font = cv2.FONT_HERSHEY_SIMPLEX
            text_size = cv2.getTextSize(text, font, 5, 10)[0]
            text_x = (w - text_size[0]) // 2
            text_y = (h + text_size[1]) // 2
            cv2.putText(final_frame, text, (text_x, text_y), font, 5, (255, 165, 0), 10, cv2.LINE_AA)
        elif self.is_recording:
            box_color = (255, 0, 0) 
            cv2.rectangle(final_frame, (int(w*0.02), int(h*0.02)), (int(w*0.98), int(h*0.98)), box_color, 4)
        else:
            box_color = (0, 255, 0) 
            cv2.rectangle(final_frame, (int(w*0.02), int(h*0.02)), (int(w*0.98), int(h*0.98)), box_color, 2)
        
        center_x = int(w / 2)
        head_y = int(h * 0.25)
        head_r_x, head_r_y = int(w * 0.08), int(h * 0.15)
        shoulder_y = int(h * 0.60)
        shoulder_w = int(w * 0.28)
        
        cv2.ellipse(final_frame, (center_x, head_y), (head_r_x, head_r_y), 0, 0, 360, (255, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(final_frame, "HEAD", (center_x - 30, head_y - head_r_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2, cv2.LINE_AA)
        cv2.line(final_frame, (center_x - shoulder_w, shoulder_y), (center_x + shoulder_w, shoulder_y), (255, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(final_frame, "SHOULDER", (center_x - 55, shoulder_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2, cv2.LINE_AA)
        
        hand_y = int(h * 0.88)
        hand_offset = int(w * 0.21)
        hand_r = int(w * 0.045)
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
        n_frames, n_dims = seq_arr.shape
        if n_frames == target_len: return seq_arr
        
        orig_idx = np.linspace(0, 1, n_frames)
        target_idx = np.linspace(0, 1, target_len)
        resampled = np.zeros((target_len, n_dims), dtype=np.float32)
        for d in range(n_dims):
            resampled[:, d] = np.interp(target_idx, orig_idx, seq_arr[:, d])
        return resampled

    def finish_recording(self):
        self.is_recording = False
        t_log("레코딩", f"[{self.current_word}] 지정된 녹화 완료.")
        
        QTimer.singleShot(100, self.prompt_save)

    def prompt_save(self):
        if self.record_mode == "json":
            reply = QMessageBox.question(self, '저장 확인', f"방금 녹화한 '{self.current_word}'의 정답지(뼈대 데이터)를 저장하시겠습니까?", QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                self.save_json_data()
            else:
                self.lbl_status.setText(f"ℹ️ [{self.current_word}] 정답지 저장이 취소되었습니다.")
                self.lbl_status.setStyleSheet("font-size: 22px; font-weight: bold; color: white; background-color: #555555; padding: 15px; border-radius: 10px;")
        elif self.record_mode == "video":
            reply = QMessageBox.question(self, '저장 확인', f"방금 녹화한 '{self.current_word}'의 전문가 시연 영상을 저장하시겠습니까?", QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                self.save_video_data()
            else:
                self.lbl_status.setText(f"ℹ️ [{self.current_word}] 영상 저장이 취소되었습니다.")
                self.lbl_status.setStyleSheet("font-size: 22px; font-weight: bold; color: white; background-color: #555555; padding: 15px; border-radius: 10px;")

        self.btn_record_json.setEnabled(True)
        self.btn_record_video.setEnabled(True)

    def save_json_data(self):
        resampled_seq = self.resample_sequence(self.sequence_data, 30)
        if resampled_seq is not None:
            self.expert_data[self.current_word] = resampled_seq.tolist()
            try:
                with open(self.json_path, "w", encoding="utf-8") as f:
                    json.dump(self.expert_data, f, ensure_ascii=False, indent=4)
                t_log("데이터저장", f"'{self.current_word}'의 75차원 뼈대 데이터(JSON) 정상 업데이트 완료")
                self.lbl_status.setText(f"✅ [{self.current_word}] 75차원 정답지 저장 완료!")
                self.lbl_status.setStyleSheet("font-size: 22px; font-weight: bold; color: white; background-color: #4CAF50; padding: 15px; border-radius: 10px;")
            except Exception as e: 
                t_log("시스템에러", f"JSON 저장 중 오류 발생: {e}")
        else:
            t_log("데이터에러", f"녹화 실패: [{self.current_word}] 유효한 뼈대 데이터를 추출하지 못했습니다.")
            self.lbl_status.setText(f"❌ [{self.current_word}] 녹화 실패 (데이터 추출 오류)")
            self.lbl_status.setStyleSheet("font-size: 22px; font-weight: bold; color: white; background-color: #f44336; padding: 15px; border-radius: 10px;")

    def save_video_data(self):
        if self.recorded_frames:
            try:
                actual_fps = len(self.recorded_frames) / self.rec_time
                if actual_fps < 5.0: actual_fps = 30.0 
                
                video_path = os.path.join(self.media_dir, f"{self.current_word}.mp4")
                h, w, _ = self.recorded_frames[0].shape
                fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
                out = cv2.VideoWriter(video_path, fourcc, actual_fps, (w, h))
                for f in self.recorded_frames:
                    out.write(f)
                out.release()
                t_log("미디어저장", f"전문가 시연 영상(.mp4) 생성 완료 (실제 FPS: {actual_fps:.1f}): {video_path}")
                
                img_path = os.path.join(self.media_dir, f"{self.current_word}.jpg")
                cv2.imwrite(img_path, self.recorded_frames[0])
                t_log("미디어저장", f"학습 모드용 썸네일 이미지(.jpg) 추출 완료: {img_path}")
                
                self.lbl_status.setText(f"✅ [{self.current_word}] 시연 영상(.mp4) 및 썸네일(.jpg) 저장 완료!")
                self.lbl_status.setStyleSheet("font-size: 22px; font-weight: bold; color: white; background-color: #4CAF50; padding: 15px; border-radius: 10px;")
            except Exception as e: 
                t_log("시스템에러", f"미디어(mp4/jpg) 저장 중 오류 발생: {e}")
                self.lbl_status.setText(f"❌ [{self.current_word}] 영상 저장 실패")
                self.lbl_status.setStyleSheet("font-size: 22px; font-weight: bold; color: white; background-color: #f44336; padding: 15px; border-radius: 10px;")
        else:
            self.lbl_status.setText(f"❌ [{self.current_word}] 저장할 프레임이 없습니다.")
            self.lbl_status.setStyleSheet("font-size: 22px; font-weight: bold; color: white; background-color: #f44336; padding: 15px; border-radius: 10px;")

    def closeEvent(self, event):
        t_log("시스템", "정답지 스튜디오 종료 시퀀 가동 (카메라 릴리즈)")
        self.timer.stop()
        if self.cap: self.cap.release()
        event.accept()

if __name__ == '__main__':
    if "DISPLAY" not in os.environ: os.environ["DISPLAY"] = ":0"
    app = QApplication(sys.argv)
    ex = GroundTruthStudio()
    ex.show()
    sys.exit(app.exec_())