import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///codefor.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Настройки загрузки файлов
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max file size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt', 'zip', 'py', 'js', 'html', 'css'}
    
    # Посты на странице
    POSTS_PER_PAGE = 20
    
    # Языки по умолчанию
    DEFAULT_LANGUAGE = 'ru'