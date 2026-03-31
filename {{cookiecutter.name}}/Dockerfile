# 베이스 이미지
FROM python:3.10-slim

# 작업 디렉토리 설정
WORKDIR /app

# 라이브러리 설치
COPY dist/stage/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 전체 코드 복사
# Host 폴더들을 컨테이너 내부 /app/ 하위로 복사
COPY dist/stage/ .

# 루트 경로 설정
ENV PYTHONPATH=/app/src:/app

# 일반 실행 명령
CMD ["python", "-m", "<module.run>", "--run_mode", "normal", "--env", "release"]
# FastAPI 실행 명령
# CMD ["uvicorn", "<module.run>", "--host", "0.0.0.0", "--port", "8000"]
