#!/bin/bash
# Conda 명령어 활성화를 위한 초기화
source ~/.bashrc
eval "$(conda shell.bash hook)"

# 사용자의 수어 학습기 가상환경 활성화
conda activate hailo10_env

echo "=========================================="
echo "로컬 NPU (vlm_server.py) 가동 상태 확인 중..."
echo "가상환경: $(conda info --envs | grep '*' | awk '{print $1}')"
echo "파이썬 경로: $(which python)"
echo "=========================================="

if ! pgrep -f "vlm_server.py" > /dev/null
then
    echo "NPU 백그라운드 서버 구동 시작..."
    python /home/a/Sign_Kiosk/vlm_server.py &
    sleep 5 
else
    echo "NPU 서버가 이미 실행 중입니다."
fi

echo "메인 수어 학습기 인터페이스를 호출합니다..."
python /home/a/Sign_Kiosk/a.py

echo "=========================================="
read -p "프로그램이 종료되었거나 에러가 발생했습니다. 창을 닫으려면 엔터 키를 누르세요..."
