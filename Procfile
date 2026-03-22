release: python manage.py migrate
web: gunicorn config.wsgi --worker-class gevent --workers 3 --timeout 0
