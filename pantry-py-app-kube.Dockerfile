
# Stage 1: Build the application
FROM python:3.11.14-trixie AS build-app

WORKDIR /usr/src/py-app

# Python environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies for compilation
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY ./py-project/requirements/ ./requirements/

# Build wheels for production dependencies
RUN pip wheel --no-cache-dir --wheel-dir /wheels \
    -r requirements/prod.txt

# Copy application source
COPY ./py-project/ .


# Stage 2: Run DEV
FROM python:3.11.14-trixie AS dev

ENV HOME=/home/pantry
ENV APP_DIR=/home/pantry/py-project
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN addgroup --system pantry && \
    adduser --system --group --home $HOME pantry && \
    mkdir -p $APP_DIR

WORKDIR $APP_DIR

COPY --from=build-app /wheels /wheels
COPY --from=build-app /usr/src/py-app/requirements/ ./requirements/

RUN pip install --no-cache-dir \
    --no-index \
    --find-links /wheels \
    -r requirements/dev.txt

COPY --chown=pantry:pantry --from=build-app \
    /usr/src/py-app/ .

USER pantry
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# Stage 3: Run PROD
FROM python:3.11.14-trixie AS prod-runtime

ENV HOME=/home/pantry
ENV APP_DIR=/home/pantry/py-project
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create non-root user
RUN addgroup --system pantry && \
    adduser --system --group --home $HOME pantry && \
    mkdir -p $APP_DIR

WORKDIR $APP_DIR

# Copy wheels and requirements
COPY --from=build-app /wheels /wheels
COPY --from=build-app /usr/src/py-app/requirements/ ./requirements/

# Install production dependencies
RUN pip install --no-cache-dir \
    --no-index \
    --find-links /wheels \
    -r requirements/prod.txt && \
    rm -rf /wheels

# Copy application
COPY --chown=pantry:pantry --from=build-app \
    /usr/src/py-app/ .

# Run as non-root
USER pantry

EXPOSE 8000

# Start Django application using Gunicorn
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]

