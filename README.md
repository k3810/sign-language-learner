# 🤟 하이브리드 산업 안전 수어 교육 키오스크 (Customizable Edge-AI Sign Language Learner)

**'전국마이스터고 스타프로젝트 AI Competition' 출품작**  
본 프로젝트는 청각장애인과 건청인이 함께 안전하게 소통하며 일할 수 있도록 돕는 실시간 수어 학습 기기입니다. 엣지 컴퓨팅(Edge Computing)과 로컬 AI 서버를 결합하여, 학교 실습실이나 산업 현장에 당장 필요한 '맞춤형 안전 수어'를 관리자가 직접 3D 뼈대 데이터로 추가하고 학생들이 즉각적인 AI 피드백을 받으며 배울 수 있도록 개발되었습니다.

---

## 1. 문제정의

**"생명과 직결된 산업 현장, 그러나 '안전 수어'의 국가 표준은 없습니다."**

* **현장 맞춤형 수어의 부재:** 기계, 용접, 건설 등 산업 현장마다 사용하는 위험 장비가 다릅니다. 하지만 기존 수어 번역기들은 대중적인 일상 단어만 제공할 뿐, "프레스 기계 비상 정지"와 같은 특수한 생명 직결 단어는 알려주지 않습니다.
* **현장 은어와 소통 단절:** 표준 수어가 없기 때문에 공장마다 임의로 만든 '그들만의 은어(바디랭귀지)'를 사용하며, 노동자가 이직할 때마다 안전 교육을 처음부터 다시 받아야 하는 치명적인 사각지대가 발생합니다.
* **우리의 해결책 (대체 불가능성):** 세상의 모든 단어를 얕게 아는 클라우드 번역기가 아닙니다. 관리자가 우리 실습장에 딱 맞는 안전 수어를 직접 기계에 녹화(Teaching)해서 넣고, 학생들은 오프라인 엣지 환경에서 NPU와 로컬 LLM을 통해 정밀한 채점과 다정한 대화형 피드백을 받으며 완벽하게 훈련할 수 있는 '현장 맞춤형 수어 학습 플랫폼'입니다.

## 2. 아키텍처

본 시스템은 기기의 부하를 줄이고 지연 시간을 최소화하기 위해 **투트랙(Two-Track) 하이브리드 구조**와 6가지 모듈화된 기능을 채택했습니다.

* **엣지 컴퓨팅 (Raspberry Pi 5 + Hailo-10H NPU):**
  웹캠 영상을 받아 `MediaPipe`로 손과 몸의 75차원 3D 뼈대 좌표를 추출하여 자체 구현한 DTW 알고리즘으로 시계열 동작 정확도를 채점합니다. 특히 '연습 모드'에서는 기기 내 NPU에서 시각-언어 모델(`Qwen2-VL-2B`)을 온디바이스로 구동하여 정밀한 시각적 자세 교정 피드백을 제공합니다.
* **로컬 AI 서버 (노트북 연동):**
  '자율 모드'와 '대화 모드' 등 긴 문장 생성이 필요한 경우, 라즈베리파이가 1차 추출한 데이터를 동일 네트워크(192.168.137.1) 상의 노트북으로 전송합니다. 노트북의 순수 텍스트 언어 모델(`Qwen2.5:3b`)이 맥락에 맞는 칭찬과 상세한 피드백을 생성하여 반환합니다.
* **핵심 기능 (6가지 모드):**
  1. **정답지 스튜디오:** 관리자가 직접 새로운 수어 단어의 3D 뼈대 데이터(JSON)와 시연 영상을 추가하는 레코딩 스튜디오.
  2. **학습 모드:** 전문가 시연 영상과 수형 설명을 통해 기본 동작 숙지.
  3. **연습 모드:** 사용자의 동작을 NPU 비전 모델과 DTW로 분석하여 채점 및 교정.
  4. **확인 모드:** 7가지 미니게임(객관식, 초성 퀴즈, 서바이벌 등)으로 지루함 없이 복습.
  5. **자율 모드:** 자유로운 수어 동작을 인식해 로컬 LLM이 다정한 문장으로 번역.
  6. **AI와 대화:** STT(음성 인식)와 카메라를 융합하여 AI 어시스턴트와 심화 학습 진행.

## 3. 사용 스택

* **Hardware:** Raspberry Pi 5 (8GB), Hailo-10H AI HAT, USB 웹캠, 로컬 서버용 노트북
* **Software (GUI & Logic):** Python 3, PyQt5, OpenCV, NumPy (가상 키보드용 커스텀 한글 오토마타 자체 개발)
* **AI & Vision:** MediaPipe (Holistic 3D 뼈대 추출)
* **ETC:** Edge-TTS / gTTS (음성 합성), SpeechRecognition (음성 인식), Flask (기기 간 비동기 통신)

## 4. 실행방법

> ⚠️ **주의:** 본 프로젝트는 라즈베리파이5 NPU 하드웨어와 노트북이 동일 네트워크에 연결된 환경에 최적화되어 있습니다.

```bash
# 1. 저장소 클론 (라즈베리파이 환경)
git clone [https://github.com/k3810/sign-language-learner.git](https://github.com/k3810/sign-language-learner.git)
cd sign-language-learner

# 2. 필수 패키지 설치
pip install -r requirements.txt

# 3. 노트북(서버)에서 LLM API 서버 실행
python vlm_server.py

# 4. 통합 키오스크 런처 실행 (NPU 백그라운드 서버 & GUI 자동 동시 기동)
bash run_kiosk.sh

##5. AI 사용 내역
본 프로젝트는 시스템의 완성도를 높이고 코드 구현 및 최적화를 위해 다음과 같은 AI 기술을 적극 활용했습니다.

* **Google Gemini AI:** 프론트엔드 GUI(a.py), NPU 백엔드 서버(vlm_server.py), 데이터 구축 스튜디오(truth_studio.py), 통합 런처 등 본 프로젝트를 구성하는 모든 핵심 소스 코드의 작성, 디버깅, 아키텍처 설계에 Google Gemini AI를 적극 활용했습니다.

* **MediaPipe (Google):** 영상에서 사용자의 손가락과 신체 관절의 3D 좌표를 실시간으로 추적하는 데 사용했습니다.

* **Qwen2-VL-2B (Alibaba Cloud):** '연습 모드'에서 사용자의 수어 자세 이미지를 정밀 분석하기 위해 라즈베리파이 NPU(Hailo) 위에서 온디바이스로 구동했습니다.

* **Qwen2.5:3b (Alibaba Cloud):** '자율 모드'와 'AI 대화 모드'에서 대화형 피드백 문장을 생성하기 위해 노트북 로컬 서버 환경에서 구동했습니다.

##6. 라이선스
MIT License

Copyright (c) 2026 k3810

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
