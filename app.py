from flask import (Flask, render_template, redirect, url_for, request, flash,
                   session, send_from_directory, g, abort, jsonify)
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import safe_join
from sqlalchemy.orm import joinedload
from functools import wraps
import os
import re
import logging

from config import Config
from models import db, User, Post, Attachment, Comment, Like, Tag
from utils import save_attachment, load_translations
from app_security import (markdown_to_safe_html, sanitize_plain, safe_github_url,
                          is_safe_url, rate_limiter, ascii_filename)
from extensions import csrf

log = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    csrf.init_app(app)

    with app.app_context():
        db.create_all()
        if not User.query.first():
            admin = User(
                username='admin',
                email='admin@codefor.com',
                display_name='Administrator',
                is_admin=True,
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
    return app


app = create_app()


# ==================== SESSION / LANG / GLOBALS ====================

@app.before_request
def validate_session_and_lang():
    # 1) Валидация сессии: если user_id указывает на удалённого/забаненного/несуществующего
    uid = session.get('user_id')
    if uid is not None:
        u = db.session.get(User, uid)
        if u is None or u.is_banned or u.is_deleted:
            session.clear()
            # не флашим на сам login, чтобы не дублировать сообщение
            if request.endpoint not in ('login', 'register', 'static'):
                flash('Сессия сброшена: аккаунт недоступен', 'error')
                return redirect(url_for('login'))

    # 2) Язык
    if 'language' not in session:
        session['language'] = app.config['DEFAULT_LANGUAGE']
    g.translations = load_translations(session.get('language'))
    g.t = lambda key: g.translations.get(key, key)


@app.context_processor
def inject_globals():
    lang = session.get('language', app.config['DEFAULT_LANGUAGE'])
    tr = load_translations(lang)
    uid = session.get('user_id')
    current_user = db.session.get(User, uid) if uid else None
    return dict(
        current_user_id=uid,
        current_user=current_user,
        language=lang,
        t=lambda key: tr.get(key, key),
    )


@app.errorhandler(RequestEntityTooLarge)
def too_large(e):
    flash('Файл слишком большой (макс. 16 МБ на запрос)', 'error')
    return redirect(request.referrer or url_for('index')), 413


@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403


@app.errorhandler(500)
def server_error(e):
    log.exception('500 error')
    return render_template('errors/500.html'), 500


# ==================== DECORATORS ====================

def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        if 'user_id' not in session:
            flash('Требуется авторизация', 'error')
            return redirect(url_for('login', next=request.path))
        return f(*a, **kw)
    return w


def admin_required(f):
    @wraps(f)
    def w(*a, **kw):
        if 'user_id' not in session:
            flash('Требуется авторизация', 'error')
            return redirect(url_for('login'))
        u = db.session.get(User, session['user_id'])
        if not u or not u.is_admin or u.is_deleted:
            flash('Доступ запрещен', 'error')
            return redirect(url_for('index'))
        return f(*a, **kw)
    return w


# ==================== AUTH ====================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = sanitize_plain(request.form.get('username', ''), 80)
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        display_name = sanitize_plain(request.form.get('display_name', ''), 100)
        bio = sanitize_plain(request.form.get('bio', ''), app.config['BIO_MAX'])
        github_url = request.form.get('github_url', '').strip()

        if not username or not email or not password:
            flash('Заполните обязательные поля', 'error')
            return redirect(url_for('register'))
        if len(password) < 8:
            flash('Пароль должен быть не короче 8 символов', 'error')
            return redirect(url_for('register'))
        if '@' not in email or len(email) > 120:
            flash('Некорректный email', 'error')
            return redirect(url_for('register'))
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
            github_url=safe_github_url(github_url) or '',
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
        ip = request.remote_addr or 'unknown'
        if not rate_limiter.allow(f'login:{ip}', app.config['LOGIN_RATE_LIMIT'],
                                  app.config['LOGIN_RATE_WINDOW']):
            flash('Слишком много попыток. Подождите.', 'error')
            return redirect(url_for('login'))

        username = sanitize_plain(request.form.get('username', ''), 80)
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            if user.is_deleted:
                flash('Аккаунт удален', 'error')
                return redirect(url_for('login'))
            if user.is_banned:
                flash('Аккаунт забанен', 'error')
                return redirect(url_for('login'))
            session.permanent = True
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            rate_limiter.reset(f'login:{ip}')
            flash('Добро пожаловать!', 'success')
            nxt = request.args.get('next') or request.form.get('next')
            if nxt and nxt.startswith('/') and not nxt.startswith('//'):
                return redirect(nxt)
            return redirect(url_for('index'))
        flash('Неверные данные', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('index'))


# ==================== POSTS ====================

@app.route('/')
@app.route('/page/<int:page>')
def index(page=1):
    q = Post.query.join(User).filter(
        Post.is_deleted == False,
        User.is_banned == False,
        User.is_deleted == False,
    ).order_by(Post.created_at.desc())

    search = request.args.get('q', '').strip()[:100]
    tag_name = request.args.get('tag', '').strip()[:50]

    if search:
        like = f'%{search}%'
        q = q.filter(db.or_(Post.title.ilike(like), Post.content.ilike(like)))
    if tag_name:
        q = q.join(Post.tags).filter(Tag.name == tag_name)

    posts = q.options(
        joinedload(Post.author),
        joinedload(Post.repost_of).joinedload(Post.author),
    ).paginate(page=page, per_page=app.config['POSTS_PER_PAGE'], error_out=False)

    liked_ids = set()
    if session.get('user_id'):
        liked_ids = {l.post_id for l in Like.query.filter_by(user_id=session['user_id']).all()}

    return render_template('index.html', posts=posts, search=search,
                           tag_name=tag_name, liked_ids=liked_ids)


def _parse_tags(raw: str) -> list[Tag]:
    names = re.split(r'[\s,]+', (raw or '').lower())
    out, seen = [], set()
    for n in names:
        n = sanitize_plain(n, 50)
        if not n or n in seen:
            continue
        seen.add(n)
        tag = Tag.query.filter_by(name=n).first()
        if not tag:
            tag = Tag(name=n)
            db.session.add(tag)
            db.session.flush()
        out.append(tag)
    return out[:10]


@app.route('/post/new', methods=['GET', 'POST'])
@login_required
def new_post():
    if request.method == 'POST':
        title = sanitize_plain(request.form.get('title', ''),
                               app.config['POST_TITLE_MAX'])
        content_md = request.form.get('content', '')
        tags_raw = request.form.get('tags', '')

        if not title or not content_md.strip():
            flash('Заполните заголовок и содержание', 'error')
            return redirect(url_for('new_post'))
        if len(content_md) > app.config['POST_CONTENT_MAX']:
            flash('Слишком длинный пост', 'error')
            return redirect(url_for('new_post'))

        try:
            post = Post(
                title=title,
                content=content_md,
                content_html=markdown_to_safe_html(content_md),
                user_id=session['user_id'],
            )
            db.session.add(post)
            db.session.flush()

            for tag in _parse_tags(tags_raw):
                post.tags.append(tag)

            for file in request.files.getlist('attachments'):
                if file and file.filename:
                    result = save_attachment(file, post.id)
                    if not result:
                        flash(f'Файл отклонён: {file.filename}', 'error')
                        continue
                    db.session.add(Attachment(
                        post_id=post.id,
                        filename=result['filename'],
                        original_filename=result['original_filename'],
                        file_type=result['type'],
                        mime=result.get('mime'),
                        file_path=result.get('path', ''),
                        base64_data=result.get('data', ''),
                        size=result.get('size', 0),
                    ))

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            log.exception('new_post failed')
            flash(f'Ошибка при сохранении: {e}', 'error')
            return redirect(url_for('new_post'))

        flash('Пост создан!', 'success')
        return redirect(url_for('view_post', post_id=post.id))

    return render_template('new_post.html')


@app.route('/post/<int:post_id>')
def view_post(post_id):
    post = Post.query.options(
        joinedload(Post.author),
        joinedload(Post.repost_of).joinedload(Post.author),
    ).get_or_404(post_id)

    user = db.session.get(User, session['user_id']) if session.get('user_id') else None
    is_admin = bool(user and user.is_admin)

    if post.is_deleted and not (user and (is_admin or post.user_id == user.id)):
        flash('Пост удален', 'error')
        return redirect(url_for('index'))
    if (post.author.is_banned or post.author.is_deleted) and not is_admin:
        if not (user and post.user_id == user.id):
            flash('Автор недоступен', 'error')
            return redirect(url_for('index'))

    attachments = Attachment.query.filter_by(post_id=post_id).all()
    comments = (Comment.query.filter_by(post_id=post_id, is_deleted=False)
                .options(joinedload(Comment.author))
                .order_by(Comment.created_at.asc()).all())

    liked = False
    if user:
        liked = Like.query.filter_by(post_id=post_id, user_id=user.id).first() is not None

    return render_template('view_post.html', post=post, attachments=attachments,
                           comments=comments, liked=liked)


@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    user = db.session.get(User, session['user_id'])
    if post.user_id != user.id and not user.is_admin:
        flash('Нет прав', 'error')
        return redirect(url_for('view_post', post_id=post_id))
    post.is_deleted = True
    db.session.commit()
    flash('Пост удален', 'success')
    return redirect(url_for('index'))


@app.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def toggle_like(post_id):
    post = Post.query.get_or_404(post_id)
    if post.is_deleted:
        abort(404)
    user_id = session['user_id']
    existing = Like.query.filter_by(post_id=post_id, user_id=user_id).first()
    if existing:
        db.session.delete(existing)
        liked = False
    else:
        db.session.add(Like(post_id=post_id, user_id=user_id))
        liked = True
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(liked=liked, count=Like.query.filter_by(post_id=post_id).count())
    return redirect(request.referrer or url_for('view_post', post_id=post_id))


@app.route('/post/<int:post_id>/repost', methods=['POST'])
@login_required
def repost(post_id):
    original = Post.query.get_or_404(post_id)
    if original.is_deleted:
        abort(404)
    if original.user_id == session['user_id']:
        flash('Нельзя репостить свой пост', 'error')
        return redirect(url_for('view_post', post_id=post_id))

    # Уже репостил?
    existing = Post.query.filter_by(
        user_id=session['user_id'], repost_of_id=original.id, is_deleted=False
    ).first()
    if existing:
        flash('Вы уже репостили этот пост', 'error')
        return redirect(url_for('view_post', post_id=existing.id))

    rp = Post(
        title=original.title,
        content=original.content,
        content_html=original.content_html,
        user_id=session['user_id'],
        repost_of_id=original.id,
    )
    db.session.add(rp)
    db.session.commit()
    flash('Репост создан', 'success')
    return redirect(url_for('view_post', post_id=rp.id))


@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    if post.is_deleted:
        abort(404)
    content = sanitize_plain(request.form.get('content', ''),
                             app.config['COMMENT_MAX'])
    if not content:
        flash('Пустой комментарий', 'error')
        return redirect(url_for('view_post', post_id=post_id))
    db.session.add(Comment(post_id=post_id, user_id=session['user_id'], content=content))
    db.session.commit()
    flash('Комментарий добавлен', 'success')
    return redirect(url_for('view_post', post_id=post_id) + '#comments')


@app.route('/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    c = Comment.query.get_or_404(comment_id)
    user = db.session.get(User, session['user_id'])
    if c.user_id != user.id and not user.is_admin:
        abort(403)
    c.is_deleted = True
    db.session.commit()
    flash('Комментарий удалён', 'success')
    return redirect(url_for('view_post', post_id=c.post_id) + '#comments')


@app.route('/post/<int:post_id>/export.md')
def export_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.is_deleted:
        abort(404)
    md = (f'# {post.title}\n\n'
          f'_by @{post.author.username} on {post.created_at:%Y-%m-%d}_\n\n'
          f'{post.content}\n')
    return app.response_class(
        md, mimetype='text/markdown; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="post-{post.id}.md"'},
    )


# ==================== PROFILE ====================

@app.route('/profile/<username>')
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    current = db.session.get(User, session['user_id']) if session.get('user_id') else None
    is_admin = bool(current and current.is_admin)

    if user.is_deleted and not is_admin:
        if not (current and current.id == user.id):
            flash('Профиль удален', 'error')
            return redirect(url_for('index'))

    if user.is_deleted or user.is_banned:
        if is_admin:
            posts = user.posts.order_by(Post.created_at.desc()).all()
        elif current and current.id == user.id:
            posts = user.posts.filter_by(is_deleted=False).order_by(Post.created_at.desc()).all()
        else:
            posts = []
    else:
        posts = user.posts.filter_by(is_deleted=False).order_by(Post.created_at.desc()).all()

    return render_template('profile.html', user=user, posts=posts)


@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    user = db.session.get(User, session['user_id'])
    if request.method == 'POST':
        user.display_name = sanitize_plain(request.form.get('display_name', ''),
                                           100) or user.username
        user.bio = sanitize_plain(request.form.get('bio', ''),
                                  app.config['BIO_MAX'])
        gh = request.form.get('github_url', '').strip()
        user.github_url = safe_github_url(gh) or ''
        avatar = request.form.get('avatar_url', '').strip()
        user.avatar_url = avatar if is_safe_url(avatar) else ''
        db.session.commit()
        flash('Профиль обновлен', 'success')
        return redirect(url_for('profile', username=user.username))
    return render_template('edit_profile.html', user=user)


# ==================== ADMIN ====================

@app.route('/admin')
@admin_required
def admin_panel():
    users = User.query.order_by(User.id.asc()).all()
    return render_template('admin/index.html', users=users)


@app.route('/admin/users/<int:user_id>/ban', methods=['POST'])
@admin_required
def ban_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Нельзя банить админа', 'error')
        return redirect(url_for('admin_panel'))
    user.is_banned = not user.is_banned
    db.session.commit()
    flash(f'Пользователь {"забанен" if user.is_banned else "разбанен"}', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Нельзя удалить админа', 'error')
        return redirect(url_for('admin_panel'))
    user.is_deleted = not user.is_deleted
    db.session.commit()
    flash(f'Пользователь {"удален" if user.is_deleted else "восстановлен"}', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/posts/deleted')
@admin_required
def deleted_posts():
    posts = (Post.query.filter_by(is_deleted=True)
             .options(joinedload(Post.author))
             .order_by(Post.updated_at.desc()).all())
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
    return redirect(url_for('view_post', post_id=post_id))


# ==================== API ====================

@app.route('/api/preview', methods=['POST'])
@login_required
def preview_markdown():
    data = request.get_json(silent=True) or {}
    md = (data.get('content') or '')[:app.config['POST_CONTENT_MAX']]
    return jsonify(html=markdown_to_safe_html(md))


# ==================== LANG ====================

@app.route('/lang/<lang_code>')
def set_lang(lang_code):
    if lang_code in app.config['AVAILABLE_LANGUAGES']:
        lang_file = os.path.join(os.path.dirname(__file__), 'lang', f'{lang_code}.py')
        if os.path.exists(lang_file):
            session['language'] = lang_code
    ref = request.referrer
    if ref and ref.startswith(request.host_url):
        return redirect(ref)
    return redirect(url_for('index'))


# ==================== UPLOADS ====================

@app.route('/uploads/files/<int:post_id>/<path:filename>')
def uploaded_file(post_id, filename):
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'files', str(post_id))
    safe = safe_join(folder, filename)
    if not safe or not os.path.isfile(safe):
        abort(404)
    resp = send_from_directory(folder, filename, as_attachment=True)
    resp.headers['Content-Disposition'] = (
        f'attachment; filename="{ascii_filename(filename)}"'
    )
    return resp


if __name__ == '__main__':
    app.run(debug=True)