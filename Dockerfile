# Official Python 3.13.9 slim-bookworm multi-platform manifest, pinned by digest.
FROM python:3.13.9-slim-bookworm@sha256:b685a4fa58bb19d1814d78a1ec0f0208f351452724f78b20212c984d6e124a34
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /bot
COPY bot.py mechfight.py ./
COPY sentinel ./sentinel
USER 65534:65534
ENTRYPOINT ["python3", "-u", "/bot/bot.py"]
