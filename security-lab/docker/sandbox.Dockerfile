FROM python:3.11-slim-bookworm
WORKDIR /app
RUN pip install --no-cache-dir flask==3.0.2
COPY sandbox/demo_app /app
ENV FLASK_RUN_HOST=0.0.0.0
EXPOSE 8080
CMD ["python", "-m", "flask", "--app", "app", "run", "-p", "8080"]
