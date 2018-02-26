"""
Django settings for lastwill project.

Generated by 'django-admin startproject' using Django 1.11.4.

For more information on this file, see
https://docs.djangoproject.com/en/1.11/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.11/ref/settings/
"""

import os

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.realpath(__file__))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.11/howto/deployment/checklist/


# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['127.0.0.1']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
   
    'rest_framework',
    'rest_framework.authtoken',
    'allauth',
    'allauth.account',
    'rest_auth',
    'rest_auth.registration',
    'djcelery_email',

    'lastwill.main',
    'lastwill.contracts',
    'lastwill.other',
    'lastwill.profile',
    'lastwill.payments',
    'lastwill.deploy',
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

ROOT_URLCONF = 'lastwill.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'lastwill-frontend/dist'), os.path.join(BASE_DIR, 'templates')],
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

WSGI_APPLICATION = 'lastwill.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.11/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'lastwill_new',
        'USER': 'lastwill_new',
        'PASSWORD': 'lastwill_new',
        'HOST': 'localhost',
        'PORT': 5432,
        'CONN_MAX_AGE': None
    }
}



# Password validation
# https://docs.djangoproject.com/en/1.11/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/1.11/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.11/howto/static-files/


PROJECT_STATIC_ROOT = os.path.join(BASE_DIR, 'lastwill-frontend/dist/static')
STATIC_ROOT = os.path.join(ROOT, 'static_collect/')
STATIC_URL = '/static/'

MEDIA_ROOT = os.path.join(ROOT, 'media/')
MEDIA_URL = '/media/'

ADMIN_MEDIA_PREFIX = STATIC_URL + 'admin/'

STATICFILES_DIRS = (
    PROJECT_STATIC_ROOT,
)


SITE_ID = 1 
REST_SESSION_LOGIN = True

ACCOUNT_LOGOUT_ON_GET = True
ACCOUNT_CONFIRM_EMAIL_ON_GET = True
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_AUTHENTICATION_METHOD = 'username_email'
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True

REST_FRAMEWORK = { 
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': None, # return all objects if no limit specified
}

SIGNER='127.0.0.1:5000'
SOL_PATH = '/var/www/contracts_repos/lastwill/contracts/LastWillOraclize.sol'
ORACLIZE_PROXY = '0xf4c716ec3a201b960ca75a74452e663b00cf58b9'

REST_AUTH_REGISTER_SERIALIZERS = { 
    'REGISTER_SERIALIZER': 'lastwill.profile.serializers.UserRegisterSerializer',
}

SOLC = 'solc --optimize --combined-json abi,bin --allow-paths={}'

CONTRACTS_DIR = '/var/www/contracts_repos/'

# have to be writeable
CONTRACTS_TEMP_DIR = os.path.join(BASE_DIR, 'temp')

MESSAGE_QUEUE = 'notification'

REST_AUTH_SERIALIZERS = { 
        'LOGIN_SERIALIZER': 'lastwill.profile.serializers.UserLoginSerializer',
}


try:
    from lastwill.settings_local import *
except ImportError as exc:
    print("Can't load local settings")
