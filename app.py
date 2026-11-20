from flask import Flask, render_template, redirect, url_for, request, flash, session, send_from_directory
from config import Config
from models import db, User, Post, Attachment
from utils import t, load_translations, get_language, save_attachment, allowed_file
import os
from functools import wraps
from werkzeug.utils import secure_filename
import base64


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    db.init_app(app)
    
    # Создаем таблицы
    with app.app_context():
        db.create_all()
        # Создаем админа по умолчанию если нет пользователей
        if not User.query.first():
            admin = User(
                username='admin',
                email='admin@codefor.com',
                display_name='Administrator',
                is_admin=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
    
    return app


app = create_app()


# Middleware для языка
@app.before_request
def set_language():
    if 'language' not in session:
        session['language'] = app.config['DEFAULT_LANGUAGE']
    
    # Передаем переводы во все шаблоны
    from flask import g
    g.translations = load_translations(session.get('language'))
    g.t = lambda key: g.translations.get(key, key)


# Контекстный процессор для передачи переменных в шаблоны
@app.context_processor
def inject_globals():
    return dict(
        current_user=getattr(session, 'user_id', None),
        language=session.get('language', 'ru'),
        t=lambda key: load_translations(session.get('language')).get(key, key)
    )


# ==================== АУТЕНТИФИКАЦИЯ ====================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Требуется авторизация', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Требуется авторизация', 'error')
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            flash('Доступ запрещен', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        display_name = request.form.get('display_name', '')
        bio = request.form.get('bio', '')
        github_url = request.form.get('github_url', '')
        
        # Проверка на существующего пользователя
        if User.query.filter_by(username=username).first():
            flash('Имя пользователя уже занято', 'error')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email уже зарегистрирован', 'error')
            return redirect(url_for('register'))
        
        user = User(
            username=username,
            email=email,
            display_name=display_name or username,
            bio=bio,
            github_url=github_url
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Регистрация успешна! Войдите.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if user.is_deleted:
                flash('Аккаунт удален', 'error')
                return redirect(url_for('login'))
            
            if user.is_banned:
                flash('Аккаунт забанен', 'error')
                return redirect(url_for('login'))
            
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            
            flash('Добро пожаловать!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверные данные', 'error')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('index'))


# ==================== ПОСТЫ ====================

@app.route('/')
@app.route('/page/<int:page>')
def index(page=1):
    # Показываем только не удаленные посты от не забаненных/удаленных пользователей
    posts = Post.query.join(User).filter(
        Post.is_deleted == False,
        User.is_banned == False,
        User.is_deleted == False
    ).order_by(Post.created_at.desc()).paginate(
        page=page, 
        per_page=app.config['POSTS_PER_PAGE'],
        error_out=False
    )
    
    return render_template('index.html', posts=posts)


@app.route('/post/new', methods=['GET', 'POST'])
@login_required
def new_post():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')  # HTML content
        
        if not title or not content:
            flash('Заполните все поля', 'error')
            return redirect(url_for('new_post'))
        
        post = Post(
            title=title,
            content=content,
            user_id=session['user_id']
        )
        
        db.session.add(post)
        db.session.flush()  # Получаем ID поста
        
        # Обработка прикрепленных файлов
        files = request.files.getlist('attachments')
        for file in files:
            if file and file.filename:
                # Определяем тип файла
                is_image = file.content_type and file.content_type.startswith('image/')
                file_type = 'image' if is_image else 'file'
                
                result = save_attachment(file, post.id, file_type)
                
                if result:
                    attachment = Attachment(
                        post_id=post.id,
                        filename=result['filename'],
                        original_filename=result['original_filename'],
                        file_type=file_type,
                        file_path=result.get('path', ''),
                        base64_data=result.get('data', '')
                    )
                    db.session.add(attachment)
        
        db.session.commit()
        flash('Пост создан!', 'success')
        return redirect(url_for('index'))
    
    return render_template('new_post.html')


@app.route('/post/<int:post_id>')
def view_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    # Проверяем доступность поста
    if post.is_deleted:
        if 'user_id' not in session:
            flash('Пост удален', 'error')
            return redirect(url_for('index'))
        
        user = User.query.get(session['user_id'])
        if not user or (not user.is_admin and post.user_id != session['user_id']):
            flash('Пост удален', 'error')
            return redirect(url_for('index'))
    
    attachments = Attachment.query.filter_by(post_id=post_id).all()
    
    return render_template('view_post.html', post=post, attachments=attachments)


@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    # Проверка прав
    user = User.query.get(session['user_id'])
    if post.user_id != session['user_id'] and not user.is_admin:
        flash('Нет прав', 'error')
        return redirect(url_for('view_post', post_id=post_id))
    
    post.is_deleted = True
    db.session.commit()
    flash('Пост удален', 'success')
    return redirect(url_for('index'))


# ==================== ПРОФИЛЬ ====================

@app.route('/profile/<username>')
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    
    # Проверяем доступность профиля
    if user.is_deleted:
        if 'user_id' not in session:
            flash('Профиль удален', 'error')
            return redirect(url_for('index'))
        
        current_user = User.query.get(session['user_id'])
        if not current_user or not current_user.is_admin:
            flash('Профиль удален', 'error')
            return redirect(url_for('index'))
    
    # Посты пользователя (только не удаленные для обычных пользователей)
    if user.is_deleted or user.is_banned:
        if 'user_id' in session:
            current_user = User.query.get(session['user_id'])
            if current_user and current_user.is_admin:
                posts = user.posts.order_by(Post.created_at.desc()).all()
            else:
                posts = []
        else:
            posts = []
    else:
        posts = user.posts.filter_by(is_deleted=False).order_by(Post.created_at.desc()).all()
    
    return render_template('profile.html', user=user, posts=posts)


@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        user.display_name = request.form.get('display_name', user.display_name)
        user.bio = request.form.get('bio', user.bio)
        user.github_url = request.form.get('github_url', user.github_url)
        
        db.session.commit()
        flash('Профиль обновлен', 'success')
        return redirect(url_for('profile', username=user.username))
    
    return render_template('edit_profile.html', user=user)


# ==================== АДМИН ПАНЕЛЬ ====================

@app.route('/admin')
@admin_required
def admin_panel():
    users = User.query.all()
    return render_template('admin/index.html', users=users)


@app.route('/admin/users/<int:user_id>/ban', methods=['POST'])
@admin_required
def ban_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_banned = not user.is_banned
    db.session.commit()
    
    status = 'забанен' if user.is_banned else 'разбанен'
    flash(f'Пользователь {status}', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_deleted = not user.is_deleted
    db.session.commit()
    
    status = 'удален' if user.is_deleted else 'восстановлен'
    flash(f'Пользователь {status}', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/posts/deleted')
@admin_required
def deleted_posts():
    posts = Post.query.filter_by(is_deleted=True).order_by(Post.updated_at.desc()).all()
    return render_template('admin/deleted_posts.html', posts=posts)


@app.route('/admin/posts/<int:post_id>/restore', methods=['POST'])
@admin_required
def restore_post(post_id):
    post = Post.query.get_or_404(post_id)
    post.is_deleted = False
    db.session.commit()
    flash('Пост восстановлен', 'success')
    return redirect(url_for('deleted_posts'))


@app.route('/admin/posts/<int:post_id>/delete', methods=['POST'])
@admin_required
def admin_delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    post.is_deleted = True
    db.session.commit()
    flash('Пост удален', 'success')
    return redirect(url_for('deleted_posts'))


# ==================== ЯЗЫКИ ====================

@app.route('/lang/<lang_code>')
def set_lang(lang_code):
    # Проверяем существование файла языка
    lang_file = os.path.join(os.path.dirname(__file__), 'lang', f'{lang_code}.py')
    if os.path.exists(lang_file):
        session['language'] = lang_code
    return redirect(request.referrer or url_for('index'))


# ==================== ЗАГРУЗКА ФАЙЛОВ ====================

@app.route('/uploads/files/<filename>')
def uploaded_file(filename):
    return send_from_directory(
        os.path.join(app.config['UPLOAD_FOLDER'], 'files'),
        filename
    )


if __name__ == '__main__':
    app.run(debug=True)