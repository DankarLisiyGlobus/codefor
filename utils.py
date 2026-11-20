import os
import base64
from flask import session, current_app
from werkzeug.utils import secure_filename


def get_language():
    """Получить текущий язык из сессии"""
    return session.get('language', current_app.config['DEFAULT_LANGUAGE'])


def load_translations(lang_code=None):
    """Загрузить переводы для указанного языка"""
    if lang_code is None:
        lang_code = get_language()
    
    try:
        module = __import__(f'lang.{lang_code}', fromlist=['TRANSLATIONS'])
        return module.TRANSLATIONS
    except ImportError:
        # Fallback на русский
        module = __import__('lang.ru', fromlist=['TRANSLATIONS'])
        return module.TRANSLATIONS


def t(key, lang_code=None):
    """Перевести строку"""
    translations = load_translations(lang_code)
    return translations.get(key, key)


def allowed_file(filename):
    """Проверить расширение файла"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def save_attachment(file, post_id, file_type='file'):
    """Сохранить прикрепленный файл"""
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        
        if file_type == 'image':
            # Сохраняем как base64 для отображения в посте
            file_data = file.read()
            base64_data = base64.b64encode(file_data).decode('utf-8')
            return {
                'type': 'base64',
                'data': base64_data,
                'filename': filename,
                'original_filename': file.filename
            }
        else:
            # Сохраняем как файл для скачивания
            upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'files')
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            return {
                'type': 'file',
                'path': f'/uploads/files/{filename}',
                'filename': filename,
                'original_filename': file.filename
            }
    
    return None