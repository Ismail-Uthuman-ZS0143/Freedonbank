import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env BEFORE reading any environment variables
load_dotenv(dotenv_path=BASE_DIR.parent / '.env', override=False)

SECRET_KEY = os.environ.get('SESSION_SECRET', 'django-insecure-dev-key-cfs2')

DEBUG = os.environ.get('DJANGO_DEBUG', 'false').lower() == 'true'

ALLOWED_HOSTS = ['*']

# Step 4: customer-uploaded documents are written to disk here (not a DB
# blob), same choice as appstore's credit_file_server usecase.
UPLOAD_STORAGE_ROOT = os.environ.get(
    'UPLOAD_STORAGE_ROOT',
    str(BASE_DIR.parent / 'uploads'),
)

# Used to build a real, working upload link in the Step 3 email now that
# Step 4's portal actually exists (the mockup's own fake
# upload.freedombankva.com domain never resolves to anything).
FRONTEND_BASE_URL = os.environ.get('FRONTEND_BASE_URL', 'http://localhost:3005')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'accounts',
    'document_requests',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Same env-var convention as appstore/backend -- PGDATABASE etc, defaulting
# to the fbv database created for this project (peer auth over the local
# Unix socket, so PGPASSWORD/PGHOST can stay blank in dev).
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('PGDATABASE', 'fbv'),
        'USER': os.environ.get('PGUSER', 'ismail'),
        'PASSWORD': os.environ.get('PGPASSWORD', ''),
        'HOST': os.environ.get('PGHOST', ''),
        'PORT': os.environ.get('PGPORT', '5432'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/New_York'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_AUTHENTICATION_CLASSES': ['accounts.authentication.CsrfExemptSessionAuthentication'],
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
}

# Frontend (port 3005) proxies /api/* to this backend (port 8001) via a
# Next.js rewrite -- the browser only ever talks to the Next.js origin, so
# the session cookie is same-site from its perspective.
SESSION_COOKIE_SAMESITE = 'Lax'

# Django's default LOGGING config doesn't attach a console handler to
# app-level loggers (only to 'django'/'django.server'), so an app's
# logger.info() calls go nowhere silently. This makes them actually show up
# in the gunicorn console -- matters here since Step 3's "send" a secure
# request email logs instead of actually delivering it (no mail provider
# configured yet).
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}
