import os

# Environment variables
EMAIL_API_KEY = os.environ.get('EMAIL_API_KEY')
BASE_URL = os.environ.get('BASE_URL')
APP_NAME = os.environ.get('APP_NAME')
APP_ID = os.environ.get('APP_ID')
FROM = os.environ.get('FROM')
MAX_RETRIES = int(os.environ.get('MAX_RETRIES'))
TIMEOUT = int(os.environ.get('TIMEOUT'))