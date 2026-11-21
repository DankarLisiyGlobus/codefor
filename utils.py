import os
import re
import base64
import uuid
import tempfile

from flask import session, current_app
from werkzeug.utils import secure_filename

from app_security import sniff_image_type, verify_image


def get_language():
    return session.get('language', current_app.config['DEFAULT_LANGUAGE'])


def load_translations(lang_code=None):
    if lang_code is None:
        lang_code = get_language()
    if lang_code not in current_app.config['AVAILABLE_LANGUAGES']:
        lang_code = current_app.config['DEFAULT_LANGUAGE']
    try:
        module = __import__(f'lang.{lang_code}', fromlist=['TRANSLATIONS'])
        return module.TRANSLATIONS
    except ImportError:
        module = __import__('lang.ru', fromlist=['TRANSLATIONS'])
        return module.TRANSLATIONS


def t(key, lang_code=None):
    return load_translations(lang_code).get(key, key)


def allowed_file(filename):
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in current_app.config['ALLOWED_EXTENSIONS']


def is_image_ext(filename):
    if '.' not in filename:
        return False
    return filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_IMAGE_EXT']


_SLUG_RE = re.compile(r'[^a-zA-Z0-9._-]+')


def _safe_name(name: str) -> str:
    name = secure_filename(name) or 'file'
    name = _SLUG_RE.sub('_', name)
    return name[:120]


def save_attachment(file, post_id, forced_type=None):
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        return None

    original = file.filename
    ext = original.rsplit('.', 1)[1].lower() if '.' in original else ''
    is_img = is_image_ext(original)
    file_type = forced_type or ('image' if is_img else 'file')

    if file_type == 'image':
        data = file.read()
        if len(data) > current_app.config['MAX_IMAGE_SIZE']:
            return None
        sniffed = sniff_image_type(data[:16])
        if not sniffed:
            return None
        if sniffed == 'jpg' and ext not in ('jpg', 'jpeg'):
            ext = 'jpeg'
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}') as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            if not verify_image(tmp_path):
                return None
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        b64 = base64.b64encode(data).decode('ascii')
        mime = f'image/{sniffed if sniffed != "jpg" else "jpeg"}'
        return {
            'type': 'image',
            'data': b64,
            'mime': mime,
            'filename': _safe_name(original),
            'original_filename': original,
            'size': len(data),
        }

    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'files', str(post_id))
    os.makedirs(folder, exist_ok=True)
    safe = _safe_name(original)
    stored = f'{uuid.uuid4().hex}_{safe}'
    filepath = os.path.join(folder, stored)
    file.save(filepath)
    size = os.path.getsize(filepath)
    return {
        'type': 'file',
        'path': f'{post_id}/{stored}',
        'filename': stored,
        'original_filename': original,
        'size': size,
    }