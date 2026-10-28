FROM python:3.12-slim
RUN useradd --uid 10001 mailq
WORKDIR /app
COPY mailq ./mailq
USER 10001
CMD ["python3", "-m", "mailq.cli", "serve"]
