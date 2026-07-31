#!/bin/bash
echo "====================================================="
echo "   하이브리드 수어 인식 키오스크 통합 런처 가동"
echo "====================================================="

pkill -9 -f "vlm_server.py"
pkill -9 -f "a.py"

# 1. NPU 서버 백그라운드 실행 (로그는 vlm_server_run.log에 저장)
echo "[1/3] NPU 서버(vlm_server.py) 기동 중 (OS 전역 환경)..."
nohup bash -c 'while true; do /usr/bin/python3 /home/a/Sign_Kiosk/vlm_server.py; sleep 2; done' > /home/a/Sign_Kiosk/vlm_server_run.log 2>&1 &
SERVER_PID=$!

echo "[2/3] NPU AI 모델 로딩 대기 중 (포트 5000번 0.1초 단위 스마트 감지)..."
# 💡 [스마트 폴링 패치]: 무조건 12초를 기다리지 않고, 5000번 포트가 열리면 즉시 넘어갑니다. (최대 20초)
for i in {1..200}; do
    if /usr/bin/python3 -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(0.1); s.connect(('127.0.0.1', 5000)); s.close()" 2>/dev/null; then
        echo "-> NPU 서버 준비 완료! 즉시 화면을 실행합니다."
        break
    fi
    sleep 0.1
done

# 2. GUI 클라이언트 기동 (Conda 환경)
echo "[3/3] GUI 클라이언트(a.py) 기동 (Conda 환경)..."
source /home/a/miniforge3/bin/activate hailo10_env

# 💡 [핵심 패치]: python -u 옵션으로 버퍼링을 없애고, 모든 출력을 kiosk_app.log 파일로 실시간 기록합니다.
python -u /home/a/Sign_Kiosk/a.py > /home/a/Sign_Kiosk/kiosk_app.log 2>&1

echo "====================================================="
echo "클라이언트 종료 감지. NPU 서버를 셧다운합니다."
kill -9 $SERVER_PID
pkill -9 -f "vlm_server.py"
echo "시스템 완전 종료됨."