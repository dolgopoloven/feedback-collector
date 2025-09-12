import secrets
import string
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Создаем экземпляр приложения Flask
app = Flask(__name__)

# Конфигурация
app.config['ADMIN_CREDENTIALS'] = {
    'login': 'admin',
    'password': 'secret'
}
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'Z0502Zz!'

# Инициализируем расширения
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Модели
class Specialist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f'<Specialist {self.id} - {self.name}>'

class AssessmentLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(50), unique=True, nullable=False)
    specialist_id = db.Column(db.Integer, db.ForeignKey('specialist.id'), nullable=False)
    specialist = db.relationship('Specialist', backref=db.backref('links', lazy=True))
    is_used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<AssessmentLink {self.token} - Used: {self.is_used}>'

class Assessment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    score = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    link_id = db.Column(db.Integer, db.ForeignKey('assessment_link.id'))
    assessment_link = db.relationship('AssessmentLink', backref=db.backref('assessment', uselist=False))
    
    def get_specialist(self):
        if self.assessment_link and self.assessment_link.specialist:
            return self.assessment_link.specialist
        return None

# Вспомогательные функции
def generate_token(length=20):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def init_database():
    with app.app_context():
        db.create_all()
        
        if not Specialist.query.first():
            test_specialists = [
                Specialist(name='Иванов Иван', position='Старший менеджер'),
                Specialist(name='Петрова Анна', position='Консультант'),
                Specialist(name='Сидоров Алексей', position='Специалист по качеству')
            ]
            
            for specialist in test_specialists:
                db.session.add(specialist)
            db.session.commit()
            print('Тестовые специалисты добавлены')

# Инициализируем базу данных
init_database()

# Декораторы
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Маршруты
@app.route('/')
def index():
    return render_template('welcome.html')

@app.route('/assessment/<token>')
def assessment(token):
    assessment_link = AssessmentLink.query.filter_by(token=token).first_or_404()
    
    if assessment_link.is_used:
        return render_template('link_used.html'), 410
    
    if assessment_link.expires_at and assessment_link.expires_at < datetime.utcnow():
        return render_template('link_expired.html'), 410
    
    return render_template('index.html', 
                         specialist=assessment_link.specialist,
                         token=token)

@app.route('/submit/<token>', methods=['POST'])
def submit_score(token):
    assessment_link = AssessmentLink.query.filter_by(token=token, is_used=False).first_or_404()
    score = int(request.form['score'])
    
    new_assessment = Assessment(score=score)
    db.session.add(new_assessment)
    
    assessment_link.is_used = True
    assessment_link.assessment = new_assessment
    new_assessment.assessment_link = assessment_link
    
    db.session.commit()

    if score >= 9:
        return redirect(url_for('thanks'))
    else:
        return redirect(url_for('feedback', assessment_id=new_assessment.id))

@app.route('/feedback')
def feedback():
    assessment_id = request.args.get('assessment_id', type=int)
    assessment = Assessment.query.get_or_404(assessment_id)
    return render_template('feedback.html', assessment=assessment)

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    assessment_id = int(request.form['assessment_id'])
    comment = request.form['comment']
    assessment = Assessment.query.get_or_404(assessment_id)
    assessment.comment = comment
    db.session.commit()
    return render_template('feedback_thanks.html')

@app.route('/thanks')
def thanks():
    return render_template('thanks.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        login = request.form.get('login')
        password = request.form.get('password')
        if (login == app.config['ADMIN_CREDENTIALS']['login'] and 
            password == app.config['ADMIN_CREDENTIALS']['password']):
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin/login.html', error='Неверные логин или пароль')
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    score_filter = request.args.get('score', type=int)
    specialist_filter = request.args.get('specialist', type=int)
    date_from_str = request.args.get('date_from')
    date_to_str = request.args.get('date_to')
    
    query = Assessment.query
    
    if score_filter:
        query = query.filter(Assessment.score == score_filter)
    
    if specialist_filter:
        query = query.join(AssessmentLink).filter(AssessmentLink.specialist_id == specialist_filter)
    
    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d')
            query = query.filter(Assessment.created_at >= date_from)
        except ValueError:
            pass
    
    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, '%Y-%m-%d')
            date_to = date_to.replace(hour=23, minute=59, second=59)
            query = query.filter(Assessment.created_at <= date_to)
        except ValueError:
            pass
    
    assessments = query.order_by(Assessment.created_at.desc()).all()
    specialists = Specialist.query.filter_by(is_active=True).order_by(Specialist.name).all()
    
    total_assessments = len(assessments)
    average_score = round(sum(a.score for a in assessments) / total_assessments, 2) if total_assessments > 0 else 0
    
    specialist_stats = {}
    if specialist_filter:
        specialist = Specialist.query.get(specialist_filter)
        if specialist:
            specialist_scores = [a.score for a in assessments]
            specialist_stats = {
                'name': specialist.name,
                'total': len(specialist_scores),
                'average': round(sum(specialist_scores) / len(specialist_scores), 2) if specialist_scores else 0,
                'min': min(specialist_scores) if specialist_scores else 0,
                'max': max(specialist_scores) if specialist_scores else 0
            }
    
    return render_template(
        'admin/dashboard.html', 
        assessments=assessments,
        specialists=specialists,
        total_assessments=total_assessments,
        average_score=average_score,
        specialist_stats=specialist_stats,
        current_score_filter=score_filter,
        current_specialist_filter=specialist_filter,
        current_date_from=date_from_str,
        current_date_to=date_to_str
    )

@app.route('/admin/generate-link', methods=['GET', 'POST'])
@admin_required
def generate_link():
    specialists = Specialist.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        specialist_id = request.form.get('specialist_id')
        days_valid = int(request.form.get('days_valid', 7))
        
        specialist = Specialist.query.get_or_404(specialist_id)
        token = generate_token()
        expires_at = datetime.utcnow() + timedelta(days=days_valid)
        
        new_link = AssessmentLink(
            token=token,
            specialist_id=specialist.id,
            expires_at=expires_at
        )
        
        db.session.add(new_link)
        db.session.commit()
        
        full_url = f"{request.url_root}assessment/{token}"
        
        return render_template('admin/link_generated.html', 
                             link=full_url, 
                             specialist=specialist,
                             expires_at=expires_at)
    
    return render_template('admin/generate_link.html', specialists=specialists)

@app.route('/admin/specialists')
@admin_required
def manage_specialists():
    specialists = Specialist.query.all()
    return render_template('admin/specialists.html', specialists=specialists)

@app.route('/admin/specialists/add', methods=['GET', 'POST'])
@admin_required
def add_specialist():
    if request.method == 'POST':
        name = request.form.get('name')
        position = request.form.get('position')
        
        if name:
            new_specialist = Specialist(name=name, position=position)
            db.session.add(new_specialist)
            db.session.commit()
            return redirect(url_for('manage_specialists'))
    
    return render_template('admin/add_specialist.html')

@app.route('/admin/specialists/<int:id>/toggle')
@admin_required
def toggle_specialist(id):
    specialist = Specialist.query.get_or_404(id)
    specialist.is_active = not specialist.is_active
    db.session.commit()
    return redirect(url_for('manage_specialists'))

@app.route('/db')
@admin_required
def view_database():
    specialists = Specialist.query.all()
    assessment_links = AssessmentLink.query.all()
    assessments = Assessment.query.all()
    
    return render_template('admin/db_view.html',
                         specialists=specialists,
                         assessment_links=assessment_links,
                         assessments=assessments)

if __name__ == '__main__':
    app.run(debug=True)