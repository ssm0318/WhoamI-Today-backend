FROM python:3.9

WORKDIR /whoami/WhoAmI-Today-backend

COPY adoorback/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DJANGO_SETTINGS_MODULE=adoorback.settings.development
ENV DATABASE_HOST='localhost'
ENV DATABASE_PORT=5432
ENV DATABASE_USER='postgres'
ENV DATABASE_NAME='adoor'
ENV DATABASE_PWD='adoor2020:)'
ENV SECRET_KEY="((5+vsn)pefc7()9_x2oud)po=@0=@gf0=8j)lrk*(*sy47c+='"
ENV EMAIL_HOST_PASSWORD='ryixbjcspwkeppxv'

EXPOSE 8000

CMD ["bash", "-c", "python adoorback/manage.py makemigrations \
        && python adoorback/manage.py migrate && python adoorback/manage.py \
        update_translation_fields && /home/ubuntu/venv3.9/bin/uwsgi --ini \
        /home/ubuntu/adoor/backend/adoorback/.config/uwsgi/uwsgi.ini"]