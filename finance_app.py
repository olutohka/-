from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///finances.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    transactions = db.relationship('Transaction', backref='user', lazy=True)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(10), nullable=False)  # 'income' или 'expense'
    description = db.Column(db.String(200))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
@login_required
def index():
    transactions = Transaction.query.filter_by(user_id=current_user.id).all()
    
    # Подготовка данных для графика
    df = pd.DataFrame([{
        'date': t.date,
        'amount': t.amount if t.type == 'income' else -t.amount,
        'category': t.category,
        'type': t.type
    } for t in transactions])
    
    if not df.empty:
        # График баланса по времени
        fig_balance = px.line(df.groupby('date')['amount'].sum().cumsum(),
                            title='Динамика баланса')
        balance_chart = fig_balance.to_html()
        
        # Круговая диаграмма расходов по категориям
        expenses = df[df['type'] == 'expense'].groupby('category')['amount'].sum()
        fig_expenses = px.pie(values=expenses.values, names=expenses.index,
                            title='Структура расходов')
        expenses_chart = fig_expenses.to_html()
    else:
        balance_chart = expenses_chart = None
    
    total_income = sum(t.amount for t in transactions if t.type == 'income')
    total_expenses = sum(t.amount for t in transactions if t.type == 'expense')
    balance = total_income - total_expenses
    
    return render_template('index.html',
                         transactions=transactions,
                         balance=balance,
                         balance_chart=balance_chart,
                         expenses_chart=expenses_chart)

@app.route('/add_transaction', methods=['GET', 'POST'])
@login_required
def add_transaction():
    if request.method == 'POST':
        transaction = Transaction(
            date=datetime.strptime(request.form['date'], '%Y-%m-%d'),
            amount=float(request.form['amount']),
            category=request.form['category'],
            type=request.form['type'],
            description=request.form['description'],
            user_id=current_user.id
        )
        db.session.add(transaction)
        db.session.commit()
        flash('Транзакция добавлена успешно')
        return redirect(url_for('index'))
    return render_template('add_transaction.html')

@app.route('/export')
@login_required
def export_data():
    transactions = Transaction.query.filter_by(user_id=current_user.id).all()
    df = pd.DataFrame([{
        'Дата': t.date,
        'Приход': t.amount if t.type == 'income' else 0,
        'Расход': t.amount if t.type == 'expense' else 0,
        'Наименование': t.description
    } for t in transactions])
    
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False)
    writer.save()
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='transactions.xlsx'
    )

@app.route('/import', methods=['POST'])
@login_required
def import_data():
    if 'file' not in request.files:
        flash('Файл не выбран')
        return redirect(url_for('index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('Файл не выбран')
        return redirect(url_for('index'))
    
    try:
        df = pd.read_excel(file)
        for _, row in df.iterrows():
            if row['Приход'] > 0:
                transaction = Transaction(
                    date=row['Дата'],
                    amount=row['Приход'],
                    type='income',
                    description=row['Наименование'],
                    category='Импортированные доходы',
                    user_id=current_user.id
                )
            else:
                transaction = Transaction(
                    date=row['Дата'],
                    amount=row['Расход'],
                    type='expense',
                    description=row['Наименование'],
                    category='Импортированные расходы',
                    user_id=current_user.id
                )
            db.session.add(transaction)
        db.session.commit()
        flash('Данные успешно импортированы')
    except Exception as e:
        flash(f'Ошибка при импорте данных: {str(e)}')
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
