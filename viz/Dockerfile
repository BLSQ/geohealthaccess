# This docker image requires these environment variables at runtime
# - AWS_ACCESS_KEY_ID
# - AWS_SECRET_ACCESS_KEY
# - STANDALONE=yes

FROM python:3.9.6

RUN apt-get update
RUN apt-get install -y libgeos-dev libgdal-dev

COPY requirements.txt .
RUN --mount=type=cache,mode=0755,target=/root/.cache/pip pip install -r requirements.txt

RUN mkdir /code
COPY app.py /code
COPY assets /code/assets

EXPOSE 8000
CMD python /code/app.py

WORKDIR /code
