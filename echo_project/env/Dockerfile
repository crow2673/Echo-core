FROM python:3.12-slim

WORKDIR /echo_project

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV TZ=UTC
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY . .

CMD ["python", "pipelines/preprocess.py"]
