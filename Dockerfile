FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JOBHUNTER_WORKSPACE=/app/workspace \
    TZ=Europe/Moscow

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY jobhunter ./jobhunter
RUN pip install --no-cache-dir .

# Данные пользователя монтируются снаружи: -v "$PWD/workspace:/app/workspace"
VOLUME ["/app/workspace"]
ENTRYPOINT ["jobhunter"]
CMD ["run"]
