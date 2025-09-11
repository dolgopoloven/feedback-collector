from flask_sqlalchemy import SQLAlchemy
from flask import Flask, render_template, request, redirect, url_for, session
from functools import wraps
from datetime import datetime

# Создаем экземпляр приложения Flask
app = Flask(__name__)

# Простейшая аутентификация для админки
app.config['ADMIN_CREDENTIALS'] = {
    'login': 'admin',
    'password': 'secret'  # Смените на свой пароль!
}

# Конфигурация Базы Данных
# SQLite будет использовать файл 'database.db' в нашей папке проекта
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Отключаем ненужные уведомления
app.config['SECRET_KEY'] = 'ваш-очень-секретный-ключ-тут'  # ← ОБЯЗАТЕЛЬНО ДОБАВЬТЕ


# Создаем экземпляр SQLAlchemy и связываем его с нашим приложением
db = SQLAlchemy(app)

# Определяем Модель (таблицу) для хранения оценок
class Assessment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    score = db.Column(db.Integer, nullable=False)  # Столбец для оценки (не может быть пустым)
    comment = db.Column(db.Text)                   # Столбец для комментария (может быть пустым)
    created_at = db.Column(db.DateTime, default=datetime.utcnow) # Дата создания, проставляется автоматически

    # Метод для красивого отображения объекта (для админки и отладки)
    def __repr__(self):
        return f'<Assessment {self.id} - Score: {self.score}>'

# Создаем таблицы в БД (выполняется один раз при первом запуске)
# Важно: Этот код должен быть выполнен ДО того, как начнут обрабатываться запросы.
with app.app_context():
    db.create_all()

# Базовый маршрут - Главная страница с формой оценки
@app.route('/')
def index():
    # Просто отображаем HTML-шаблон с формой
    return render_template('index.html')

# Маршрут для обработки данных из формы
@app.route('/submit', methods=['POST'])
def submit_score():
    # Получаем оценку из формы и преобразуем в число
    score = int(request.form['score'])
    
    # СОХРАНЯЕМ ЛЮБУЮ ОЦЕНКУ В БАЗУ ДАННЫХ СРАЗУ ЖЕ
    # Для оценок 9-10 комментария пока нет, он будет NULL
    new_assessment = Assessment(score=score)
    db.session.add(new_assessment)
    db.session.commit()

    # Проверяем оценку и решаем, что делать дальше
    if score >= 9:
        # Если оценка высокая, перенаправляем на страницу благодарности
        return redirect(url_for('thanks'))
    else:
        # Если оценка низкая, перенаправляем на страницу с формой обратной связи
        # Мы передаем ID сохраненной оценки, чтобы потом обновить ее комментарием
        return redirect(url_for('feedback', assessment_id=new_assessment.id))

# Маршрут для страницы сбора обратной связи (для низких оценок)
@app.route('/feedback')
def feedback():
    # Получаем ID оценки из параметра запроса (например, /feedback?assessment_id=1)
    assessment_id = request.args.get('assessment_id', type=int)
    # Находим эту оценку в базе
    assessment = Assessment.query.get_or_404(assessment_id)
    # Отображаем шаблон, передаем в него оценку
    return render_template('feedback.html', assessment=assessment)

# Маршрут для обработки самой обратной связи (комментария)
@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    # Получаем данные из формы
    assessment_id = int(request.form['assessment_id'])
    comment = request.form['comment']

    # НАХОДИМ существующую запись в БД и ОБНОВЛЯЕМ ее
    assessment = Assessment.query.get_or_404(assessment_id)
    assessment.comment = comment
    db.session.commit()

    return render_template('feedback_thanks.html')

# Маршрут для страницы благодарности и кнопок отзывов (для высоких оценок)
@app.route('/thanks')
def thanks():
    # Просто отображаем шаблон с кнопками
    return render_template('thanks.html')

# Страница входа для админа
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        login = request.form.get('login')
        password = request.form.get('password')
        if (login == app.config['ADMIN_CREDENTIALS']['login'] and 
            password == app.config['ADMIN_CREDENTIALS']['password']):
            # Если credentials верные, сохраняем в сессии
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin/login.html', error='Неверные логин или пароль')
    
    return render_template('admin/login.html')

# Выход из админки
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

# Декоратор для проверки авторизации админа
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Обновите маршрут админки, добавив декоратор защиты
@app.route('/admin')
@admin_required
def admin_dashboard():
    # Получаем параметры фильтрации из URL (если они есть)
    score_filter = request.args.get('score', type=int)
    date_from_str = request.args.get('date_from')
    date_to_str = request.args.get('date_to')
    
    # Начинаем с базового запроса "дай все оценки"
    query = Assessment.query
    
    # Применяем фильтр по оценке, если он задан
    if score_filter:
        query = query.filter(Assessment.score == score_filter)
    
    # Применяем фильтр по дате "ОТ", если он задан
    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d')
            query = query.filter(Assessment.created_at >= date_from)
        except ValueError:
            # Если дата неверного формата, просто игнорируем этот фильтр
            pass
    
    # Применяем фильтр по дате "ДО", если он задан
    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, '%Y-%m-%d')
            # Добавляем 1 день, чтобы включить весь указанный день
            date_to = date_to.replace(hour=23, minute=59, second=59)
            query = query.filter(Assessment.created_at <= date_to)
        except ValueError:
            # Если дата неверного формата, просто игнорируем этот фильтр
            pass
    
    # Выполняем запрос и сортируем по дате (сначала новые)
    assessments = query.order_by(Assessment.created_at.desc()).all()
    
    # Передаем все оценки и текущие значения фильтров в шаблон
    return render_template(
        'admin/dashboard.html', 
        assessments=assessments,
        current_score_filter=score_filter,
        current_date_from=date_from_str,
        current_date_to=date_to_str
    )

# Запуск приложения
if __name__ == '__main__':
    app.run(debug=True)