#!/bin/bash
if [ "$DB_ENGINE" = "django.db.backends.postgresql" ]
then
        echo "Waiting for running database.."
        while ! nc -z $POSTGRES_HOST $POSTGRES_PORT; do
                sleep 0.1
        done
        echo "Postgresql is runnging"
fi
exec "$@"
