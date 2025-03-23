# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import markdown
import bleach
from bleach.sanitizer import ALLOWED_TAGS, ALLOWED_ATTRIBUTES

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///macros.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

downloads_dir = os.path.join(app.root_path, 'static', 'downloads')
os.makedirs(downloads_dir, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Configure allowed HTML tags for descriptions
ALLOWED_TAGS.extend(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'li', 'code', 'pre', 'hr', 'br'])
ALLOWED_ATTRIBUTES['a'] = ['href', 'title', 'class']
ALLOWED_ATTRIBUTES['img'] = ['src', 'alt', 'title', 'class']

# Database models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    date_registered = db.Column(db.DateTime, default=datetime.utcnow)
    purchases = db.relationship('Purchase', backref='customer', lazy=True)

class Macro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    file_path = db.Column(db.String(200), nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    purchases = db.relationship('Purchase', backref='product', lazy=True)
    
    def format_description(self):
        """Convert Markdown to HTML and sanitize it"""
        html = markdown.markdown(self.description)
        return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    macro_id = db.Column(db.Integer, db.ForeignKey('macro.id'), nullable=False)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    download_count = db.Column(db.Integer, default=0)

# Flask-Login user loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def home():
    macros = Macro.query.all()
    return render_template('home.html', macros=macros)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/macro/<int:macro_id>')
def macro_detail(macro_id):
    macro = Macro.query.get_or_404(macro_id)
    return render_template('macro_detail.html', macro=macro)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Check if user already exists
        user_exists = User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first()
        if user_exists:
            flash('Username or email already exists!')
            return redirect(url_for('register'))
        
        # Create new user
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        
        flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    purchases = Purchase.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', purchases=purchases)

@app.route('/purchase/<int:macro_id>', methods=['GET', 'POST'])
@login_required
def purchase(macro_id):
    macro = Macro.query.get_or_404(macro_id)
    
    # Check if already purchased
    existing_purchase = Purchase.query.filter_by(user_id=current_user.id, macro_id=macro_id).first()
    if existing_purchase:
        flash('You already own this macro!')
        return redirect(url_for('dashboard'))
    
    if request.method == 'GET':
        # Show payment page with PayPal button
        return render_template('purchase.html', macro=macro)
    
    # For POST request (PayPal IPN or success)
    # In a real app, you'd verify the PayPal payment here
    # For this demo, we'll assume payment is successful
    
    new_purchase = Purchase(user_id=current_user.id, macro_id=macro_id)
    db.session.add(new_purchase)
    db.session.commit()
    
    flash('Purchase successful!')
    return redirect(url_for('dashboard'))

@app.route('/paypal_success/<int:macro_id>')
@login_required
def paypal_success(macro_id):
    # Create the purchase record
    macro = Macro.query.get_or_404(macro_id)
    new_purchase = Purchase(user_id=current_user.id, macro_id=macro_id)
    db.session.add(new_purchase)
    db.session.commit()
    
    flash('Payment successful! You can now download your macro.')
    return redirect(url_for('dashboard'))

@app.route('/download/<int:purchase_id>')
@login_required
def download_macro(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    
    # Verify ownership
    if purchase.user_id != current_user.id:
        flash('Unauthorized access')
        return redirect(url_for('dashboard'))
    
    # Update download count
    purchase.download_count += 1
    db.session.commit()
    
    # Get the macro file path
    file_path = purchase.product.file_path
    
    # For security, let's make sure we're only serving files from a specific directory
    downloads_dir = os.path.join(app.root_path, 'static', 'downloads')
    filename = os.path.basename(file_path)
    
    # Send the file to the user
    return send_from_directory(
        directory=downloads_dir,
        path=filename,
        as_attachment=True,
        download_name=f"{purchase.product.name}.razer"
    )

# Updated/Added Admin routes
@app.route('/admin')
@login_required
def admin():
    # Simple admin check - in a real app, use proper role-based access
    if current_user.username != "MiniDuncan":
        flash('Unauthorized access')
        return redirect(url_for('home'))
    
    macros = Macro.query.all()
    
    # Get statistics
    total_users = User.query.count()
    total_sales = Purchase.query.count()
    total_revenue = db.session.query(db.func.sum(Macro.price)).join(Purchase).scalar() or 0
    
    return render_template('admin.html', 
                          macros=macros, 
                          total_users=total_users,
                          total_sales=total_sales,
                          total_revenue=total_revenue)

@app.route('/admin/add_macro', methods=['GET', 'POST'])
@login_required
def add_macro():
    # Check if the current user is MiniDuncan
    if current_user.username != "MiniDuncan":
        flash('Unauthorized access')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])
        
        # Handle file upload
        if 'macro_file' not in request.files:
            flash('No file part')
            return redirect(request.url)
            
        file = request.files['macro_file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
            
        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join('static', 'downloads', filename)
            file.save(os.path.join(app.root_path, file_path))
            
            new_macro = Macro(name=name, description=description, price=price, file_path=file_path)
            db.session.add(new_macro)
            db.session.commit()
            
            flash('Macro added successfully!')
            return redirect(url_for('admin'))
    
    return render_template('add_macro.html')

@app.route('/admin/edit_macro/<int:macro_id>', methods=['GET', 'POST'])
@login_required
def edit_macro(macro_id):
    # Check if the current user is MiniDuncan
    if current_user.username != "MiniDuncan":
        flash('Unauthorized access')
        return redirect(url_for('home'))
        
    macro = Macro.query.get_or_404(macro_id)
    
    if request.method == 'POST':
        macro.name = request.form['name']
        macro.description = request.form['description']
        macro.price = float(request.form['price'])
        
        # Handle file upload if a new file is provided
        if 'macro_file' in request.files and request.files['macro_file'].filename:
            file = request.files['macro_file']
            filename = secure_filename(file.filename)
            file_path = os.path.join('static', 'downloads', filename)
            
            # Delete old file if needed
            old_filename = os.path.basename(macro.file_path)
            old_file_path = os.path.join(app.root_path, 'static', 'downloads', old_filename)
            if os.path.exists(old_file_path) and old_filename != filename:
                try:
                    os.remove(old_file_path)
                except:
                    pass
                
            file.save(os.path.join(app.root_path, file_path))
            macro.file_path = file_path
        
        db.session.commit()
        flash('Macro updated successfully!')
        return redirect(url_for('admin'))
    
    return render_template('edit_macro.html', macro=macro)

@app.route('/admin/delete_macro/<int:macro_id>', methods=['POST'])
@login_required
def delete_macro(macro_id):
    # Check if the current user is MiniDuncan
    if current_user.username != "MiniDuncan":
        flash('Unauthorized access')
        return redirect(url_for('home'))
        
    macro = Macro.query.get_or_404(macro_id)
    
    # Delete associated file
    try:
        filename = os.path.basename(macro.file_path)
        file_path = os.path.join(app.root_path, 'static', 'downloads', filename)
        if os.path.exists(file_path):
            os.remove(file_path)
    except:
        pass
    
    # Delete associated purchases
    Purchase.query.filter_by(macro_id=macro_id).delete()
    
    # Delete the macro
    db.session.delete(macro)
    db.session.commit()
    flash('Macro deleted successfully!')
    return redirect(url_for('admin'))

@app.route('/admin/sales')
@login_required
def admin_sales():
    # Check if the current user is MiniDuncan
    if current_user.username != "MiniDuncan":
        flash('Unauthorized access')
        return redirect(url_for('home'))
    
    purchases = Purchase.query.all()
    return render_template('admin_sales.html', purchases=purchases)

# Register a template filter for rendering Markdown
@app.template_filter('markdown')
def convert_markdown(text):
    html = markdown.markdown(text)
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)