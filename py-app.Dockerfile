# Stage 1: Build the application
FROM python:3.11.14-trixie AS build-app
WORKDIR /usr/src/py-app

# No create .pyc files and all the logs are directly to stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system depencies for compilate
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc

# Cache wheel files
COPY ./py-project/requirements/ ./requirements/

# Download all dependencies (prod include dev dependencies). In prod install all dependencies, in dev install only dev dependencies
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r  ./requirements/prod.txt

COPY ./py-project/ .

# Stage 2: Run DEV
FROM python:3.11.14-trixie AS dev

# Create user who will run the application.
ENV HOME=/home/pantry
ENV APP_DIR=/home/pantry/py-project
RUN addgroup --system pantry && adduser --system --group pantry --home $HOME
RUN mkdir -p $APP_DIR

WORKDIR $APP_DIR

COPY --from=build-app /wheels /wheels
COPY --from=build-app   /usr/src/py-app/requirements/ ./requirements/
RUN pip install --upgrade pip
RUN pip install --no-cache-dir \
    --no-index \
    --find-links /wheels \
    -r requirements/dev.txt

COPY --chown=pantry:pantry --from=build-app  /usr/src/py-app/ .

RUN python manage.py migrate
# RUN python manage.py createsuperuser

# Stage 2: Run PROD

# ENTRYPOINT ["./entrypoint.sh"]