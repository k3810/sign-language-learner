import sys
import io
import base64
import numpy as np
import os
import threading
import ssl
import re
import subprocess
import requests 
import time
from PIL import Image
from flask import Flask, request, jsonify
from gtts import gTTS

sys.path.append('/usr/lib/python3/dist-packages')
from hailo_platform import VDevice
from hailo_platform.genai import VLM

ssl._create_default_https_context = ssl._create_unverified_context
app = Flask(__name__)
vlm = None  

LAPTOP_IP = "192.168.137.1" 
PORT = "11434"
MODEL_ID = "qwen2.5:3b"  

def pre_warm_ollama():
    print(f"\n🔥 [초기 예열] {MODEL_ID} 순수 언어 모델을 메모리에 상주시키는 중...", flush=True)
    url = f"http://{LAPTOP_IP}:{PORT}/api/generate"
    payload = {"model": MODEL_ID, "prompt": "시스템 초기화 준비 완료.", "keep_alive": -1}
    try:
        requests.post(url, json=payload, timeout=60)
        print("🔥 [초기 예열 완료] 텍스트 전용 초고속 AI 모델 대기 완료.", flush=True)
    except Exception as e:
        print(f"⚠️ [초기 예열 실패]: {e}", flush=True)

def request_laptop_llm_server(prompt_text, req_type="default", target_word="", score=0, dtw_semantic=""):
    url = f"http://{LAPTOP_IP}:{PORT}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    messages = []
    
    # 💡 [핵심 수정] 1순위 단어에 집중하되, 피드백을 3~4문장으로 다정하고 풍부하게 작성하도록 규칙 변경
    if req_type in ["auto", "auto_known", "auto_unknown"]:
        system_msg = (
            "당신은 마이스터고 학생들이 청각장애인과 건청인의 소통을 돕기 위해 개발한 친절하고 따뜻한 'AI 수어 번역 어시스턴트'입니다. "
            "반드시 100% 한국어로만 자연스러운 대화체로 답변해 주세요.\n"
            "[절대 지켜야 할 규칙]\n"
            "1. 상황 정보에서 오직 '1순위' 단어 하나만 정답으로 간주하여 대답하세요.\n"
            "2. 2순위, 3순위 단어는 절대 입 밖으로 꺼내거나 언급하지 마십시오.\n"
            "3. '1순위', '점수' 같은 기계적인 단어를 쓰지 마세요.\n"
            "4. 너무 짧은 단답형을 피하고, 3~4문장 분량으로 풍성하게 대답해 주세요. 사용자의 동작에 대한 아낌없는 칭찬과 따뜻한 격려를 덧붙여 주면 아주 좋습니다.\n"
            "(답변 예시: 방금 보여주신 동작은 '사랑합니다' 수어입니다. 손동작을 아주 정확하고 예쁘게 표현해 주셨어요! 이 단어는 일상에서 마음을 전할 때 아주 유용하게 쓰이니 앞으로도 자신감 있게 사용해 보세요. 정말 훌륭합니다!)"
        )
        messages.append({"role": "system", "content": system_msg})
        augmented_prompt = (
            f"상황 정보: {dtw_semantic}\n\n"
            f"위 정보에서 1순위 결과만 바탕으로, 사용자에게 칭찬과 격려가 담긴 풍부하고 친절한 피드백(3~4문장)을 작성해 주세요. 2순위, 3순위는 무시하세요."
        )
        
    elif req_type == "gigong":
        system_msg = (
            "당신은 마이스터고 학생들이 개발한 따뜻하고 친절한 'AI 수어 번역 어시스턴트'입니다. "
            "반드시 100% 한국어로만 완전한 문장 형태로 답변해 주세요.\n"
            "[절대 지켜야 할 규칙]\n"
            "1. 사용자의 동작 분석 결과가 주어지면, 오직 '1순위' 동작 하나만을 기준으로 대화를 이어나가세요.\n"
            "2. 2순위, 3순위 동작은 절대 언급하지 마십시오.\n"
            "3. 점수나 순위 같은 기계적인 단어를 빼고, 현장 가이드처럼 자연스럽고 풍부하게 3~4문장 이내로 호응해주세요."
        )
        messages.append({"role": "system", "content": system_msg})
        augmented_prompt = (
            f"사용자 행동 및 대화 내용: {prompt_text}\n\n"
            f"상황 정보: {dtw_semantic}\n\n"
            f"위 정보를 종합하여 오직 1순위 동작에 대해서만 칭찬을 곁들여 친절하고 상세한 대화 문장으로 대답하세요."
        )
    else:
        augmented_prompt = prompt_text

    messages.append({"role": "user", "content": augmented_prompt})
        
    payload = {
        "model": MODEL_ID,
        "messages": messages,
        "temperature": 0.4, # 💡 다양한 어휘력을 발휘하여 풍성하게 대답하도록 창의성 지수 상향 조정
        "max_tokens": 200,
        "keep_alive": -1
    }
    
    try:
        print(f"\n📡 [네트워크] 노트북 LLM({LAPTOP_IP}:{PORT})으로 초고속 텍스트 추론 요청 중...", flush=True)
        response = requests.post(url, headers=headers, json=payload, timeout=150)
        response.raise_for_status() 
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"[ERROR] 노트북 서버 통신 지연: {e}"

class DefensiveVLMWrapper:
    def translate_vision_to_korean(self, raw_english: str) -> str:
        if raw_english.startswith("[ERROR]"): return "오류로 인해 동작을 파악할 수 없는"
        match = re.search(r'[A-I]', raw_english.upper())
        if match:
            choice = match.group(0)
            mapping = {'A': "손을 이마나 머리 위쪽으로 올린", 'B': "손을 눈, 코, 귀 등 얼굴 상단에 둔", 'C': "손을 턱이나 입 주변으로 가져간", 'D': "손을 가슴이나 어깨 쪽으로 둔", 'E': "손을 배(복부) 쪽으로 내린", 'F': "두 손을 마주 대거나 교차하여 상호작용하는", 'G': "한 손을 몸에 닿지 않게 허공에 띄운", 'H': "두 손을 몸에 닿지 않게 허공에 띄운", 'I': "손을 무릎이나 허리 아래로 편안하게 내린"}
            return mapping.get(choice, "손과 팔의 위치가 포착된")
        return "손과 팔의 위치가 포착된"

    def structure_practice_mode(self, english_vision: str, score: int, target: str, desc: str) -> str:
        if english_vision.startswith("[ERROR]"): return "자세 분석을 완료하지 못했습니다."
        korean_vision = self.translate_vision_to_korean(english_vision)
        if score == 0 and korean_vision == "손을 무릎이나 허리 아래로 편안하게 내린": return f"아직 동작이 인식되지 않았습니다. '{target}' 수어 동작을 취해 주세요."
        if score >= 95: return f"정확도 {score}점 완벽합니다. {korean_vision} 모습이며 '{target}' 수어의 정석입니다."
        elif score >= 80: return f"정확도 {score}점 훌륭합니다. 현재 {korean_vision} 모습이 확인됩니다."
        elif score >= 60: return f"정확도 {score}점 방향성을 잘 잡으셨습니다. 현재 {korean_vision} 모습으로 인식됩니다."
        else: return f"정확도 {score}점입니다. {korean_vision} 상태입니다. 올바른 자세는 '{desc}'입니다."

wrapper = DefensiveVLMWrapper()

def play_audio(text):
    try:
        audio_path = "/tmp/ai_feedback.mp3"
        safe_text = text.replace('\n', ' ').strip()
        EDGE_TTS_BIN = "/home/a/miniforge3/envs/hailo10_env/bin/edge-tts"
        result = subprocess.run([EDGE_TTS_BIN, "--voice", "ko-KR-SunHiNeural", "--text", safe_text, "--write-media", audio_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode != 0: 
            tts = gTTS(text=safe_text, lang='ko'); tts.save(audio_path)
        os.system(f"cvlc --play-and-exit {audio_path} 2>/dev/null")
    except Exception as e:
        print(f"[*] 음성 출력 실패: {e}", flush=True)

@app.route('/generate', methods=['POST'])
def generate():
    global vlm
    data = request.json
    req_type = data.get('request_type', 'default')
    target = data.get('target_word', '수어 동작')
    desc = data.get('correct_description', '설명 없음')
    dtw_semantic = data.get('dtw_semantic_analysis', '센서 데이터 없음')
    try: score = int(data.get('dtw_score', 0))
    except ValueError: score = 0
    prompt_text = data.get('prompt', '')
    
    print("\n" + "="*70, flush=True)
    print(f"📡 [서버 로그] 신규 요청 수신! (모드: {req_type})", flush=True)

    raw_result_text = ""
    
    if req_type == "practice":
        final_prompt = (
            "Analyze the person's hand gesture in the image and choose EXACTLY ONE option that best describes the location of the hands:\n"
            "A. Touching or near the FOREHEAD or TOP OF HEAD.\n"
            "B. Touching or near the EYES, NOSE, or EARS.\n"
            "C. Touching or near the CHIN, LIPS, or JAW.\n"
            "D. Touching or near the CHEST or SHOULDERS.\n"
            "E. Touching or near the STOMACH or BELLY.\n"
            "F. TWO HANDS touching or interacting with each other.\n"
            "G. ONE HAND held up independently in the air.\n"
            "H. TWO HANDS held up independently in the air.\n"
            "I. Hands RESTING DOWN near the lap or waist (No action).\n"
            "Answer ONLY with a single letter (A, B, C, D, E, F, G, H, or I)."
        )
        try:
            image_b64 = data.get('image', None)
            formatted_messages = []
            frames = []
            if image_b64:
                img_data = base64.b64decode(image_b64)
                image = Image.open(io.BytesIO(img_data)).convert('RGB')
                image = image.resize((336, 336), Image.Resampling.BILINEAR)
                frames.append(np.array(image))
                formatted_messages.append({"role": "user", "content": [{"type": "image"}, {"type": "text", "text": final_prompt}]})
            else:
                formatted_messages.append({"role": "user", "content": [{"type": "text", "text": final_prompt}]})
            
            raw_result = vlm.generate(prompt=formatted_messages, frames=frames, temperature=0.1, max_generated_tokens=5)
            for chunk in raw_result: raw_result_text += chunk
        except Exception as e:
            raw_result_text = "[ERROR] NPU 연산 실패"
            
    else:
        try:
            raw_result_text = request_laptop_llm_server(prompt_text, req_type, target, score, dtw_semantic)
            print("\n" + "▼"*25 + f" [노트북 {MODEL_ID} 모델 응답 결과] " + "▼"*25, flush=True)
            print(raw_result_text, flush=True)
            print("\n" + "▲"*80 + "\n", flush=True)
        except Exception as e:
            raw_result_text = f"[ERROR] 노트북 통신 실패: {e}"
        
    clean_english = raw_result_text.replace("<|im_start|>", "").replace("<|im_end|>", "").strip()
    
    if req_type == "practice": final_text = wrapper.structure_practice_mode(clean_english, score, target, desc)
    else: final_text = clean_english
            
    threading.Thread(target=play_audio, args=(final_text,)).start()
    return jsonify({'result': final_text})

if __name__ == '__main__':
    threading.Thread(target=pre_warm_ollama, daemon=True).start()
    MODEL_PATH = "/usr/local/hailo/resources/models/hailo10h/Qwen2-VL-2B-Instruct.hef"
    try:
        with VDevice() as target_vdevice:
            vlm = VLM(model_path=MODEL_PATH, vdevice=target_vdevice)
            print("🚀 하이브리드 서버 기동 완료 (Port 5000)", flush=True)
            app.run(host='0.0.0.0', port=5000, threaded=False)
    except Exception as e: print(f"❌ [에러]: {e}", flush=True)