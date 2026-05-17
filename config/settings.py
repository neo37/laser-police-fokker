from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('SECRET_KEY', 'dev-key')
DEBUG = os.getenv('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.staticfiles',
    'laser',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
    ]},
}]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}
}

STATIC_URL = '/static/'
MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Laser settings from .env
GRBL_PORT        = os.getenv('GRBL_PORT', '/dev/ttyUSB0')
GRBL_BAUD        = int(os.getenv('GRBL_BAUD', 115200))
WORK_WIDTH_MM    = float(os.getenv('WORK_WIDTH_MM', 300))
WORK_HEIGHT_MM   = float(os.getenv('WORK_HEIGHT_MM', 300))
IMAGES_DIR       = os.getenv('IMAGES_DIR', str(BASE_DIR))
DEFAULT_POWER    = int(os.getenv('DEFAULT_POWER', 650))
DEFAULT_SPEED    = int(os.getenv('DEFAULT_SPEED', 2500))
DEFAULT_SPACING  = float(os.getenv('DEFAULT_LINE_SPACING', 0.12))
