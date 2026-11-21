from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(100))
    bio = db.Column(db.Text)
    github_url = db.Column(db.String(200))
    avatar_url = db.Column(db.String(300))
    is_admin = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    posts = db.relationship('Post', backref='author', lazy='dynamic',
                            cascade='all, delete-orphan',
                            foreign_keys='Post.user_id')
    comments = db.relationship('Comment', backref='author', lazy='dynamic',
                               cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='user', lazy='dynamic',
                            cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active_account(self) -> bool:
        return not self.is_banned and not self.is_deleted

    @property
    def post_count(self):
        return self.posts.filter_by(is_deleted=False).count()

    @property
    def comment_count(self):
        return self.comments.filter_by(is_deleted=False).count()

    def __repr__(self):
        return f'<User {self.username}>'


class Post(db.Model):
    __tablename__ = 'posts'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    content_html = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    # Репост: ссылка на оригинальный пост
    repost_of_id = db.Column(db.Integer, db.ForeignKey('posts.id', ondelete='SET NULL'),
                             nullable=True, index=True)
    is_deleted = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    repost_of = db.relationship(
        'Post', remote_side=[id],
        backref=db.backref('reposts', lazy='dynamic'),
    )

    attachments = db.relationship('Attachment', backref='post', lazy='dynamic',
                                  cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='post', lazy='dynamic',
                               cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='post', lazy='dynamic',
                            cascade='all, delete-orphan')
    tags = db.relationship('Tag', secondary='post_tags', backref='posts', lazy='dynamic')

    @property
    def is_repost(self) -> bool:
        return self.repost_of_id is not None

    @property
    def like_count(self):
        return self.likes.count()

    @property
    def comment_count(self):
        return self.comments.filter_by(is_deleted=False).count()

    @property
    def repost_count(self):
        return self.reposts.filter_by(is_deleted=False).count()

    def __repr__(self):
        return f'<Post {self.id} {self.title[:30]}>'


class Attachment(db.Model):
    __tablename__ = 'attachments'

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    filename = db.Column(db.String(200), nullable=False)
    original_filename = db.Column(db.String(200), nullable=False)
    file_type = db.Column(db.String(50))
    mime = db.Column(db.String(100))
    file_path = db.Column(db.String(300))
    base64_data = db.Column(db.Text)
    size = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Comment(db.Model):
    __tablename__ = 'comments'

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Comment {self.id} on post {self.post_id}>'


class Like(db.Model):
    __tablename__ = 'likes'
    __table_args__ = (db.UniqueConstraint('post_id', 'user_id', name='uq_post_user_like'),)

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Tag(db.Model):
    __tablename__ = 'tags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)

    def __repr__(self):
        return f'<Tag #{self.name}>'


post_tags = db.Table(
    'post_tags',
    db.Column('post_id', db.Integer, db.ForeignKey('posts.id', ondelete='CASCADE'),
              primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id', ondelete='CASCADE'),
              primary_key=True),
)