import os
from celery import Celery

# Get Redis URL from environment variable
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

celery_app = Celery('tasks', broker=redis_url, backend=redis_url)
celery_app.conf.update(
    broker_connection_retry_on_startup=True,
)

@celery_app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
