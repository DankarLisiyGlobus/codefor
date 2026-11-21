import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///codefor.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    PERMANENT_SESSION_LIFETIME = timedelta(days=14)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') == 'production'

    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    MAX_IMAGE_SIZE = 5 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'txt', 'zip',
                          'py', 'js', 'html', 'css', 'md', 'json'}
    ALLOWED_IMAGE_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

    POSTS_PER_PAGE = 20
    COMMENTS_PER_PAGE = 50

    DEFAULT_LANGUAGE = 'ru'
    AVAILABLE_LANGUAGES = ('ru', 'en')

    WTF_CSRF_TIME_LIMIT = None

    LOGIN_RATE_LIMIT = 10
    LOGIN_RATE_WINDOW = 60 * 5

    POST_TITLE_MAX = 200
    POST_CONTENT_MAX = 200_000
    COMMENT_MAX = 5_000
    BIO_MAX = 1_000