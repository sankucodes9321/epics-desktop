FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV CUDA_VISIBLE_DEVICES=-1 TF_USE_LEGACY_KERAS=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 gstreamer1.0-tools gstreamer1.0-pipewire \
    gstreamer1.0-plugins-base && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-demo.txt ./
RUN pip install --no-cache-dir --no-compile --index-url https://download.pytorch.org/whl/cpu torch==2.6.0 && \
    pip install --no-cache-dir --no-compile -r requirements.txt
RUN useradd --create-home --uid 10001 zkauth
COPY main.py student_verifier.py ./
COPY privacy/ privacy/
COPY scripts/ scripts/
USER zkauth
ENTRYPOINT ["python", "main.py"]
CMD ["list-users"]
