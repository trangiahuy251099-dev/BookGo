from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from models import db, User, Book, Cart, CartItem, Category, Order, OrderDetail, Notification, Subscriber
import os
import time
from werkzeug.utils import secure_filename
from functools import wraps
import re
import csv
from data_categories import categories_data

app = Flask(__name__)
app.secret_key = "bookgo_secret_key_2025"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///bookgo.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config['SESSION_PERMANENT'] = False

# Upload config
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db.init_app(app)

# ------------------- Decorators -------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Vui lòng đăng nhập', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Vui lòng đăng nhập', 'warning')
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if user.role != 'admin':
            flash('Bạn không có quyền', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

# ------------------- Helper -------------------
def get_or_create_cart(user_id):
    cart = Cart.query.filter_by(user_id=user_id).first()
    if not cart:
        cart = Cart(user_id=user_id)
        db.session.add(cart)
        db.session.commit()
    return cart

@app.context_processor
def inject_cart_count():
    if 'user_id' in session:
        cart = Cart.query.filter_by(user_id=session['user_id']).first()
        total = sum(item.quantity for item in cart.items) if cart else 0
        return dict(cart_total=total)
    return dict(cart_total=0)

@app.context_processor
def inject_categories():
    categories = Category.query.all()
    return dict(categories=categories)

@app.context_processor
def inject_notification_count():
    if 'user_id' in session:
        count = Notification.query.filter_by(user_id=session['user_id'], is_read=False).count()
        return dict(notif_count=count)
    return dict(notif_count=0)

# ------------------- Hàm loại bỏ dấu -------------------
def remove_accents(text):
    if not isinstance(text, str):
        text = str(text)
    text = text.lower()
    text = re.sub(r'[àáạảãâầấậẩẫăằắặẳẵ]', 'a', text)
    text = re.sub(r'[èéẹẻẽêềếệểễ]', 'e', text)
    text = re.sub(r'[ìíịỉĩ]', 'i', text)
    text = re.sub(r'[òóọỏõôồốộổỗơờớợởỡ]', 'o', text)
    text = re.sub(r'[ùúụủũưừứựửữ]', 'u', text)
    text = re.sub(r'[ỳýỵỷỹ]', 'y', text)
    text = re.sub(r'[đ]', 'd', text)
    text = re.sub(r'[^\w\s]', '', text)
    return text

# ------------------- Trang chủ -------------------
@app.route("/")
def index():
    books = Book.query.limit(10).all()
    return render_template("index.html", books=books)

# ------------------- API Xem Them -------------------
@app.route("/api/books")
def api_books():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 8, type=int)
    offset = (page - 1) * per_page
    books = Book.query.offset(offset).limit(per_page).all()
    data = []
    for book in books:
        data.append({
            "id": book.id,
            "title": book.title,
            "author": book.author,
            "price": book.price,
            "original_price": book.original_price,
            "cover": book.cover,
        })
    has_more = Book.query.offset(offset + per_page).limit(1).first() is not None
    return jsonify({"books": data, "has_more": has_more})

# ------------------- Chi tiết sách -------------------
@app.route("/book/<int:book_id>")
def book_detail(book_id):
    book = Book.query.get_or_404(book_id)
    return render_template("product_detail.html", book=book)
@app.route("/admin/update-images")
@admin_required
def update_images():
    import csv
    with open('books.csv', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            book = Book.query.filter_by(title=row['title']).first()
            if book:
                book.cover = row['cover']
        db.session.commit()
    return "Đã cập nhật ảnh cho tất cả sách."

# ------------------- Tìm kiếm -------------------
@app.route("/search")
def search():
    keyword = request.args.get("q", "").strip()
    if not keyword:
        return redirect(url_for("index"))
    keyword_norm = remove_accents(keyword)
    books = Book.query.all()
    results = []
    for book in books:
        if (keyword_norm in remove_accents(book.title) or 
            keyword_norm in remove_accents(book.author)):
            results.append(book)
    return render_template("search_results.html", keyword=keyword, results=results)

@app.route("/api/search-suggest")
def search_suggest():
    keyword = request.args.get("q", "").strip()
    if not keyword or len(keyword) < 2:
        return jsonify({"suggestions": []})
    keyword_norm = remove_accents(keyword)
    # Lấy tất cả sách (không giới hạn)
    books = Book.query.all()
    suggestions = []
    for book in books:
        if keyword_norm in remove_accents(book.title):
            suggestions.append({
                "id": book.id,
                "title": book.title,
                "cover": book.cover,
                "price": book.price
            })
    # Chỉ trả về tối đa 10 gợi ý để tránh quá tải
    return jsonify({"suggestions": suggestions[:10]})

# ------------------- Danh mục -------------------
@app.route("/category/<slug>")
def category_books(slug):
    category = Category.query.filter_by(slug=slug).first_or_404()
    books = Book.query.filter_by(category_id=category.id).all()
    return render_template("category_books.html", category=category, books=books)

# ------------------- Giỏ hàng -------------------
@app.route("/add-to-cart/<int:book_id>")
@login_required
def add_to_cart(book_id):
    book = Book.query.get_or_404(book_id)
    cart = get_or_create_cart(session['user_id'])
    item = CartItem.query.filter_by(cart_id=cart.id, book_id=book_id).first()
    if item:
        item.quantity += 1
    else:
        item = CartItem(cart_id=cart.id, book_id=book_id, quantity=1)
        db.session.add(item)
    db.session.commit()
    flash(f'Đã thêm "{book.title}" vào giỏ', 'success')
    return redirect(request.referrer or url_for("index"))

@app.route("/cart")
@login_required
def cart():
    cart = get_or_create_cart(session['user_id'])
    items = []
    total = 0
    for item in cart.items:
        sub = item.book.price * item.quantity
        total += sub
        items.append({"book": item.book, "quantity": item.quantity, "subtotal": sub})
    return render_template("cart.html", cart_items=items, total=total)

@app.route("/update-cart/<int:book_id>/<int:quantity>")
@login_required
def update_cart(book_id, quantity):
    cart = get_or_create_cart(session['user_id'])
    item = CartItem.query.filter_by(cart_id=cart.id, book_id=book_id).first()
    if item:
        if quantity <= 0:
            db.session.delete(item)
        else:
            item.quantity = quantity
        db.session.commit()
    return redirect(url_for("cart"))

@app.route("/clear-cart")
@login_required
def clear_cart():
    cart = get_or_create_cart(session['user_id'])
    for item in cart.items:
        db.session.delete(item)
    db.session.commit()
    flash("Đã xóa giỏ hàng", "info")
    return redirect(url_for("index"))

# ------------------- Đơn hàng -------------------
@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    cart = get_or_create_cart(session['user_id'])
    if not cart.items:
        flash("Giỏ hàng trống", "warning")
        return redirect(url_for("cart"))
    if request.method == "POST":
        fullname = request.form.get("fullname")
        phone = request.form.get("phone")
        address = request.form.get("address")
        province = request.form.get("province")
        district = request.form.get("district")
        ward = request.form.get("ward")
        note = request.form.get("note")
        payment_method = request.form.get("payment_method")
        coupon = request.form.get("coupon")
        
        full_address = f"{address}, {ward}, {district}, {province}"
        if not fullname or not phone or not address:
            flash("Vui lòng nhập đầy đủ thông tin", "danger")
            return redirect(url_for("checkout"))
        
        user = User.query.get(session['user_id'])
        if user:
            user.fullname = fullname
            user.phone = phone
            user.address = full_address
            db.session.commit()
        
        total = 0
        for item in cart.items:
            total += item.book.price * item.quantity
        
        order = Order(
            user_id=session['user_id'],
            total_price=total,
            address=full_address,
            phone=phone,
            note=note
        )
        db.session.add(order)
        db.session.flush()
        for item in cart.items:
            detail = OrderDetail(order_id=order.id, book_id=item.book_id, quantity=item.quantity, price=item.book.price)
            db.session.add(detail)
        for item in cart.items:
            db.session.delete(item)
        db.session.commit()
        flash("Đặt hàng thành công!", "success")
        return redirect(url_for("order_history"))
    
    # GET
    user = User.query.get(session['user_id'])
    items = []
    total = 0
    for item in cart.items:
        sub = item.book.price * item.quantity
        total += sub
        items.append({"book": item.book, "quantity": item.quantity, "subtotal": sub})
    return render_template("checkout.html", cart_items=items, total=total, user=user)

@app.route("/orders")
@login_required
def order_history():
    orders = Order.query.filter_by(user_id=session['user_id']).order_by(Order.order_date.desc()).all()
    return render_template("order_history.html", orders=orders)

@app.route("/order/<int:order_id>")
@login_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != session['user_id'] and session.get('role') != 'admin':
        flash("Bạn không có quyền xem đơn hàng này", "danger")
        return redirect(url_for("index"))
    return render_template("order_detail.html", order=order)
@app.route("/update-profile", methods=["POST"])
@login_required
def update_profile():
    user = User.query.get(session['user_id'])
    user.address = request.form.get("address")
    user.phone = request.form.get("phone")
    db.session.commit()
    flash("Cập nhật thông tin thành công", "success")
    return redirect(url_for("profile"))

# ------------------- Admin đơn hàng -------------------
@app.route("/admin/orders")
@admin_required
def admin_orders():
    orders = Order.query.order_by(Order.order_date.desc()).all()
    return render_template("admin_orders.html", orders=orders)

@app.route("/admin/order/<int:order_id>/status", methods=["POST"])
@admin_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get("status")
    old_status = order.status
    if new_status in ["Đang xử lý", "Đang giao", "Đã giao", "Hủy"]:
        order.status = new_status
        db.session.commit()
        if old_status != new_status:
            message = f"Đơn hàng #{order.id} đã chuyển sang trạng thái: {new_status}"
            link = url_for('order_detail', order_id=order.id)
            notif = Notification(user_id=order.user_id, message=message, link=link)
            db.session.add(notif)
            db.session.commit()
        flash("Cập nhật trạng thái thành công", "success")
    else:
        flash("Trạng thái không hợp lệ", "danger")
    return redirect(url_for("admin_orders"))

# ------------------- Thông báo -------------------
@app.route("/notifications")
@login_required
def get_notifications():
    notifs = Notification.query.filter_by(user_id=session['user_id']).order_by(Notification.created_at.desc()).all()
    for n in notifs:
        if not n.is_read:
            n.is_read = True
    db.session.commit()
    return render_template("notifications.html", notifs=notifs)

@app.route("/api/notifications/unread-count")
@login_required
def unread_notification_count():
    count = Notification.query.filter_by(user_id=session['user_id'], is_read=False).count()
    return jsonify({"count": count})

# ------------------- Đăng ký bản tin -------------------
@app.route("/subscribe", methods=["POST"])
def subscribe():
    email = request.form.get("email")
    if not email:
        flash("Vui lòng nhập email", "danger")
        return redirect(request.referrer or url_for("index"))
    if Subscriber.query.filter_by(email=email).first():
        flash("Email này đã đăng ký nhận bản tin rồi.", "info")
    else:
        sub = Subscriber(email=email)
        db.session.add(sub)
        db.session.commit()
        flash("Đăng ký nhận bản tin thành công! Cảm ơn bạn.", "success")
    return redirect(request.referrer or url_for("index"))

# ------------------- Đăng ký / Đăng nhập -------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        fullname = request.form.get("fullname")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm = request.form.get("confirm_password")
        if not all([username, fullname, email, password]):
            flash("Vui lòng nhập đủ thông tin", "danger")
            return redirect(url_for("register"))
        if password != confirm:
            flash("Mật khẩu xác nhận không khớp", "danger")
            return redirect(url_for("register"))
        if User.query.filter_by(username=username).first():
            flash("Tên đăng nhập đã tồn tại", "danger")
            return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("Email đã được sử dụng", "danger")
            return redirect(url_for("register"))
        user = User(username=username, fullname=fullname, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Đăng ký thành công! Hãy đăng nhập.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            flash(f"Chào mừng {user.fullname}!", "success")
            return redirect(url_for("index"))
        flash("Sai tên đăng nhập hoặc mật khẩu", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Đã đăng xuất", "info")
    return redirect(url_for("index"))

@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    user = User.query.get(session['user_id'])
    if request.method == "POST":
        old = request.form.get("old_password")
        new = request.form.get("new_password")
        confirm = request.form.get("confirm_password")
        if not user.check_password(old):
            flash("Mật khẩu cũ không đúng", "danger")
            return redirect(url_for("change_password"))
        if new != confirm:
            flash("Xác nhận mật khẩu mới không khớp", "danger")
            return redirect(url_for("change_password"))
        if len(new) < 6:
            flash("Mật khẩu mới tối thiểu 6 ký tự", "danger")
            return redirect(url_for("change_password"))
        user.set_password(new)
        db.session.commit()
        flash("Đổi mật khẩu thành công! Vui lòng đăng nhập lại.", "success")
        session.clear()
        return redirect(url_for("login"))
    return render_template("change_password.html")

@app.route("/profile")
@login_required
def profile():
    user = User.query.get(session['user_id'])
    return render_template("profile.html", user=user)

# ------------------- Quản lý sách (Admin) -------------------
@app.route("/admin/books")
@admin_required
def admin_books():
    books = Book.query.all()
    return render_template("admin_books.html", books=books)

@app.route("/admin/add-book", methods=["GET", "POST"])
@admin_required
def add_book():
    if request.method == "POST":
        title = request.form.get("title")
        author = request.form.get("author")
        price = int(request.form.get("price"))
        original_price = int(request.form.get("original_price"))
        description = request.form.get("description")
        pages = request.form.get("pages")
        pages = int(pages) if pages else None
        publisher = request.form.get("publisher")
        category_id = request.form.get("category_id")
        cover_url = request.form.get("cover_url")
        file = request.files.get("cover_file")
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{int(time.time())}{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            cover_url = url_for('static', filename=f'uploads/{filename}')
        elif not cover_url:
            cover_url = "https://picsum.photos/id/20/300/400"
        book = Book(title=title, author=author, price=price, original_price=original_price,
                    cover=cover_url, description=description, pages=pages, publisher=publisher)
        if category_id:
            book.category_id = int(category_id)
        db.session.add(book)
        db.session.commit()
        flash("Thêm sách thành công", "success")
        return redirect(url_for("admin_books"))
    return render_template("add_book.html")

@app.route("/admin/edit-book/<int:book_id>", methods=["GET", "POST"])
@admin_required
def edit_book(book_id):
    book = Book.query.get_or_404(book_id)
    if request.method == "POST":
        book.title = request.form.get("title")
        book.author = request.form.get("author")
        book.price = int(request.form.get("price"))
        book.original_price = int(request.form.get("original_price"))
        book.description = request.form.get("description")
        pages = request.form.get("pages")
        book.pages = int(pages) if pages else None
        book.publisher = request.form.get("publisher")
        category_id = request.form.get("category_id")
        book.category_id = int(category_id) if category_id else None
        cover_url = request.form.get("cover_url")
        file = request.files.get("cover_file")
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{int(time.time())}{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            book.cover = url_for('static', filename=f'uploads/{filename}')
        elif cover_url:
            book.cover = cover_url
        db.session.commit()
        flash("Cập nhật sách thành công", "success")
        return redirect(url_for("admin_books"))
    return render_template("edit_book.html", book=book)

@app.route("/admin/delete-book/<int:book_id>")
@admin_required
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    db.session.delete(book)
    db.session.commit()
    flash("Xóa sách thành công", "success")
    return redirect(url_for("admin_books"))

# ------------------- Các trang tĩnh -------------------
@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

# ------------------- Seed dữ liệu -------------------
def seed_data():
    if User.query.count() == 0:
        admin = User(username="admin", fullname="Quản trị viên", email="admin@bookgo.com", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)
        user = User(username="user1", fullname="Người dùng", email="user@bookgo.com", role="user")
        user.set_password("123456")
        db.session.add(user)
        db.session.commit()
        print("Đã tạo tài khoản admin/admin123 và user1/123456")
    if Category.query.count() == 0:
        for cat in categories_data:
            db.session.add(Category(name=cat['name'], slug=cat['slug']))
        db.session.commit()
        print("Đã thêm danh mục mẫu.")
    if Book.query.count() == 0:
        try:
            with open('books.csv', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        category = Category.query.filter_by(slug=row['category_slug']).first()
                        category_id = category.id if category else None
                        # Chuyển đổi an toàn
                        price_str = row['price'].strip()
                        original_price_str = row['original_price'].strip()
                        pages_str = row['pages'].strip()
                        book = Book(
                            title=row['title'],
                            author=row['author'],
                            price=int(price_str) if price_str.isdigit() else 0,
                            original_price=int(original_price_str) if original_price_str.isdigit() else 0,
                            cover=row['cover'],
                            description=row['description'],
                            pages=int(pages_str) if pages_str.isdigit() else None,
                            publisher=row['publisher'],
                            category_id=category_id
                        )
                        db.session.add(book)
                    except Exception as e:
                        print(f"Lỗi dòng: {row} -> {e}")
                        continue
                db.session.commit()
                print("Đã thêm sách từ file CSV.")
        except FileNotFoundError:
            print("Không tìm thấy file books.csv, bỏ qua import sách.")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_data()
    app.run(debug=True)