#!/bin/bash
if [ "$DATABASE_ENGINE" = "django.db.backends.postgresql" ]
then
        echo "Waiting for postgesql to start ..."
        while ! nc -z $DB_HOST $DB_PORT; do
                sleep 0.1
        done
        echo "Postgresql is runnging"
fi
exec "$@"
