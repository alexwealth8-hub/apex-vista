from dotenv import load_dotenv
load_dotenv()
import os
import psycopg
from psycopg_pool import ConnectionPool
DATABASE_URL = os.getenv("DATABASE_URL")
db_pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=1,
    max_size=5
)
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
import requests
from flask import Flask, render_template, request, redirect, session
import random
from flask import Flask, render_template, request, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import uuid


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

class PooledConnection:
    def __init__(self, pool):
        self.pool = pool
        self.conn = pool.getconn()

    def cursor(self, *args, **kwargs):
        return self.conn.cursor(*args, **kwargs)

    def commit(self):
        return self.conn.commit()

    def rollback(self):
        return self.conn.rollback()

    def close(self):
        if self.conn is not None:
            self.pool.putconn(self.conn)
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type:
                self.conn.rollback()
            else:
                self.conn.commit()
        finally:
            self.close()

    def __getattr__(self, name):
        return getattr(self.conn, name)


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")

    return PooledConnection(db_pool)

@app.route('/paystack-test')
def paystack_test():
    return "Paystack connection is ready!"

@app.route('/paystack/initialize', methods=['POST'])
def initialize_paystack():
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 401

    user_id = session['user_id']

    # Get the user's cart
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT product_id, quantity FROM cart WHERE \"user\"=%s",
            (user_id,)
        )
        cart_rows = cursor.fetchall()

    # Calculate total
    product_map = {p['id']: p for p in products}
    total = 0

    for product_id, quantity in cart_rows:
        product = product_map.get(int(product_id))

        if product:
            total += product['price'] * quantity

    if total <= 0:
        return jsonify({"error": "Cart is empty"}), 400

    # Paystack expects the amount in kobo
    amount = total * 100

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "email": user_id,
        "amount": amount,
        "currency": "NGN",
        "callback_url": "http://127.0.0.1:5000/payment/callback"
    }

    response = requests.post(
        "https://api.paystack.co/transaction/initialize",
        headers=headers,
        json=data
    )

    result = response.json()

    if result.get("status"):
        return jsonify({
            "authorization_url": result["data"]["authorization_url"]
        })

    return jsonify({
        "error": result.get("message", "Payment initialization failed")
    }), 400


# ✅ PRODUCTS (GLOBAL)
products = [
{"id": 1, "name": "Shoe", "price": 45000, "image": "shoe.jpg", "rating": 4, "tag": "sale"},
{"id": 2, "name": "Watch", "price": 75000, "image": "watch.jpg", "rating": 5, "tag": "new"},
{"id": 3, "name": "Bag", "price": 55000, "image": "bag.jpg", "rating": 4},
{"id": 4, "name": "Headphones", "price": 95000, "image": "headphones.jpg", "rating": 5},
{"id": 5, "name": "Cap", "price": 20000, "image": "cap.jpg", "rating": 3},
{"id": 6, "name": "Laptop", "price": 750000, "image": "laptop.jpg", "rating": 3},
{"id": 7, "name": "Phone", "price": 450000, "image": "phone.jpg", "rating": 5, "tag": "sale"},
{"id": 8, "name": "Sneakers", "price": 85000, "image": "sneakers.jpg", "rating": 5},
{"id": 9, "name": "Backpack", "price": 60000, "image": "backpack.jpg", "rating": 3},
{"id": 10, "name": "Sunglasses", "price": 35000, "image": "sunglasses.jpg", "rating": 5},
{"id": 11, "name": "Smart TV", "price": 950000, "image": "tv.jpg", "rating": 5},
{"id": 12, "name": "Mouse", "price": 45000, "image": "Mouse.jpg", "rating": 4, "tag": "hot"},
{"id": 13, "name": "Wireless Speaker", "price": 85000, "image": "Wireless Speaker.jpg", "rating": 4},
{"id": 14, "name": "SmartWatch", "price": 120000, "image": "smartwatch.jpg", "rating": 5},
{"id": 15, "name": "Bluetooth Earbuds", "price": 75000, "image": "Bluetooth Earbuds.jpg", "rating": 4}
]

def get_cart_count(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT SUM(quantity) FROM cart WHERE \"user\"=%s",
            (user_id,)
        )
        result = cursor.fetchone()[0]
        return result if result else 0

@app.route('/')
def home():
    # Get and clean the search term
    search = request.args.get('search', '').strip()

    # Search products
    if search:
        query = search.lower()

        filtered_products = [
            p for p in products
            if query in p['name'].lower()
            or query in p.get('tag', '').lower()
        ]
    else:
        filtered_products = products

    # Shuffle products for Trending and New Arrivals
    shuffled = random.sample(products, len(products))

    trending_products = shuffled[:6]
    new_arrivals = shuffled[6:12]

       # Get logged-in user's ID
    user_id = session.get('user_id')

    cart_items = []
    cart_count = 0
    rows = []

    if user_id:
        with get_db_connection() as conn:
            c = conn.cursor()

            c.execute(
                "SELECT product_id, quantity FROM cart WHERE \"user\"=%s",
                (user_id,)
            )

            rows = c.fetchall()

    product_map = {p['id']: p for p in products}

    for pid, qty in rows:
            product = product_map.get(int(pid))

            if product:
                item = product.copy()
                item['quantity'] = qty

                cart_items.append(item)
                cart_count += qty

    return render_template(
        "index.html",
        products=filtered_products,
        trending_products=trending_products,
        new_arrivals=new_arrivals,
        cart_items=cart_items,
        cart_count=cart_count,
        mini_cart=cart_items,
        user=session.get('user'),
        search=search
    )

# 🛍️ PRODUCT DETAILS
@app.route("/product/<int:product_id>")
def product_details(product_id):

    product_map = {p["id"]: p for p in products}

    product = product_map.get(product_id)

    if not product:
        return "Product not found", 404

    wishlist = session.get("wishlist", [])

    in_wishlist = product_id in wishlist

    return render_template(
        "product.html",
        product=product,
        in_wishlist=in_wishlist
    )

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():

    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 401

    data = request.get_json()

    product_id = int(data.get('product_id'))
    quantity = int(data.get('quantity', 1))

    if quantity < 1:
        quantity = 1

    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT quantity
        FROM cart
        WHERE "user"=%s AND product_id=%s
        """,
        (user_id, product_id)
    )

    row = cursor.fetchone()

    if row:

        cursor.execute(
            """
            UPDATE cart
            SET quantity = quantity + %s
            WHERE "user"=%s AND product_id=%s
            """,
            (quantity, user_id, product_id)
        )

    else:

        cursor.execute(
            """
            INSERT INTO cart ("user", product_id, quantity)
            VALUES (%s, %s, %s)
            """,
            (user_id, product_id, quantity)
        )

    conn.commit()

    cursor.execute(
        "SELECT SUM(quantity) FROM cart WHERE \"user\"=%s",
        (user_id,)
    )

    count = cursor.fetchone()[0] or 0

    conn.close()

    return jsonify({
        "success": True,
        "cart_count": count
    })

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM users WHERE email=%s",
            (email,)
        )
        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            return "User already exists!"

        hashed_password = generate_password_hash(password)
        cursor.execute(
            """
            INSERT INTO users (email, password, name)
            VALUES (%s, %s, %s)
            """,
            (email, hashed_password, name)
        )

        conn.commit()
        conn.close()

        return redirect('/login')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, email, password, name FROM users WHERE email=%s",
            (email,)
        )
        user = cursor.fetchone()

        if user:
            stored_password = user[2]

            # Check if the password is already securely hashed
            if stored_password.startswith(("scrypt:", "pbkdf2:")):
                password_valid = check_password_hash(
                    stored_password,
                    password
                )

            else:
                # Existing account with an old plaintext password
                password_valid = stored_password == password

                if password_valid:
                    # Upgrade the old password to a secure hash
                    new_password = generate_password_hash(password)

                    cursor.execute(
                        "UPDATE users SET password=%s WHERE id=%s",
                        (new_password, user[0])
                    )
                    conn.commit()

            if password_valid:
                conn.close()

                session['user'] = user[3]
                session['user_id'] = user[1]

                return redirect('/')

        conn.close()
        return "Invalid credentials"

    return render_template('login.html')

@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session:
        return redirect('/login')

    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not current_password or not new_password or not confirm_password:
            return "All fields are required"

        if new_password != confirm_password:
            return "New passwords do not match"

        if len(new_password) < 8:
            return "New password must be at least 8 characters long"

        user_id = session['user_id']

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, password FROM users WHERE email=%s",
            (user_id,)
        )
        user = cursor.fetchone()

        if not user:
            conn.close()
            return "User not found"

        stored_password = user[1]

        # Verify the current password
        if stored_password.startswith(("scrypt:", "pbkdf2:")):
            password_valid = check_password_hash(
                stored_password,
                current_password
            )
        else:
            password_valid = stored_password == current_password

        if not password_valid:
            conn.close()
            return "Current password is incorrect"

        # Save the new password securely
        hashed_password = generate_password_hash(new_password)

        cursor.execute(
            "UPDATE users SET password=%s WHERE id=%s",
            (hashed_password, user[0])
        )

        conn.commit()
        conn.close()

        return redirect('/')

    return render_template('change_password.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('user_id', None)
    return redirect('/')

# ❌ REMOVE ITEM FROM CART
@app.route('/remove_item', methods=['POST'])
def remove_item():
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 401

    data = request.get_json()
    product_id = int(data.get('product_id'))
    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM cart WHERE \"user\"=%s AND product_id=%s",
        (user_id, product_id)
    )

    conn.commit()

    # ✅ GET UPDATED CART BEFORE CLOSING
    cursor.execute(
    "SELECT product_id, quantity FROM cart WHERE \"user\"=%s",
    (user_id,)
)
    rows = cursor.fetchall()

    conn.close()

    product_map = {p['id']: p for p in products}

    updated_cart = []
    total = 0
    total_items = 0

    for pid, qty in rows:
        product = product_map.get(int(pid))
        if product:
            subtotal = product['price'] * qty
            total += subtotal
            total_items += qty

            updated_cart.append({
                "id": product['id'],
                "name": product['name'],
                "price": product['price'],
                "image": product['image'],
                "quantity": qty,
                "subtotal": subtotal
            })

    return jsonify({
        "status": "removed",
        "cart": updated_cart,
        "total": total,
        "cart_count": total_items
    })

# ❤️ VIEW WISHLIST
@app.route('/wishlist')
def view_wishlist():

    wishlist_items = []

    product_map = {p['id']: p for p in products}

    for product_id in session.get('wishlist', []):
        if product_id in product_map:
            wishlist_items.append(product_map[product_id])

    return render_template(
        'wishlist.html',
        wishlist=wishlist_items
    )



# REMOVE FROM WISHLIST
@app.route('/remove_from_wishlist/<int:product_id>')
def remove_from_wishlist(product_id):

    wishlist = session.get('wishlist', [])

    if product_id in wishlist:
        wishlist.remove(product_id)

    session['wishlist'] = wishlist

    return redirect('/wishlist')

# WISHLIST
@app.route('/add_to_wishlist/<int:product_id>')
def add_to_wishlist(product_id):

    if 'wishlist' not in session:
        session['wishlist'] = []

    wishlist = session['wishlist']

    if product_id not in wishlist:
        wishlist.append(product_id)

    session['wishlist'] = wishlist

    return redirect('/')


@app.route('/update_quantity', methods=['POST'])
def update_quantity():
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 401

    data = request.get_json()

    if not data or 'product_id' not in data or 'action' not in data:
        return jsonify({"error": "Invalid request"}), 400

    product_id = int(data.get('product_id'))
    action = data.get('action')
    user_id = session['user_id']

    removed_id = None

    with get_db_connection() as conn:
        cursor = conn.cursor()

        if action == "increase":
            cursor.execute(
                'UPDATE cart SET quantity = quantity + 1 WHERE "user"=%s AND product_id=%s',
                (user_id, product_id)
            )

        elif action == "decrease":
            cursor.execute(
                'SELECT quantity FROM cart WHERE "user"=%s AND product_id=%s',
                (user_id, product_id)
            )

            row = cursor.fetchone()

            if row and row[0] > 1:
                cursor.execute(
                    'UPDATE cart SET quantity = quantity - 1 WHERE "user"=%s AND product_id=%s',
                    (user_id, product_id)
                )

        else:
            return jsonify({"error": "Invalid action"}), 400

        # GET UPDATED CART
        cursor.execute(
            'SELECT product_id, quantity FROM cart WHERE "user"=%s',
            (user_id,)
        )

        rows = cursor.fetchall()

    product_map = {p['id']: p for p in products}

    updated_cart = []
    total = 0
    total_items = 0

    for pid, qty in rows:
        product = product_map.get(int(pid))

        if product:
            subtotal = product['price'] * qty
            total += subtotal
            total_items += qty

            updated_cart.append({
                "id": product['id'],
                "name": product['name'],
                "price": product['price'],
                "image": product['image'],
                "quantity": qty,
                "subtotal": subtotal
            })

    return jsonify({
        "cart": updated_cart,
        "total": total,
        "cart_count": total_items,
        "removed_id": removed_id
    })

@app.route('/cart')
def cart():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT product_id, quantity
        FROM cart
        WHERE "user" = %s
    """, (user_id,))

    rows = cursor.fetchall()
    conn.close()

    product_map = {p['id']: p for p in products}

    cart_items = []
    total = 0

    for pid, qty in rows:
        product = product_map.get(int(pid))
        if product:
            subtotal = product['price'] * qty
            total += subtotal

            cart_items.append({
                "id": product['id'],
                "name": product['name'],
                "price": product['price'],
                "image": product['image'],
                "quantity": qty,
                "subtotal": subtotal
            })

    return render_template("cart.html", cart=cart_items, total=total)

@app.route('/checkout')
def checkout():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]

    conn = get_db_connection()
    cursor = conn.cursor()

    # ✅ FIXED: use user_id
    cursor.execute(
        "SELECT product_id, quantity FROM cart WHERE \"user\" = %s",
        (user_id,)
    )
    cart_rows = cursor.fetchall()

    items = []
    total = 0

    # ✅ Use product list (NOT DB products table)
    product_map = {p['id']: p for p in products}

    for product_id, quantity in cart_rows:
        product = product_map.get(int(product_id))

        if product:
            items.append({
                "product_name": product['name'],
                "price": product['price'],
                "quantity": quantity
            })

            total += product['price'] * quantity

    conn.close()

    return render_template(
        "checkout.html",
        cart_items=items,
        total=total
    )


@app.route("/payment/callback")
def payment_callback():

    reference = request.args.get("reference")

    if not reference:
        return "Payment reference missing.", 400

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"
    }

    response = requests.get(
        f"https://api.paystack.co/transaction/verify/{reference}",
        headers=headers
    )

    result = response.json()

    if not result.get("status"):
        return "Unable to verify payment.", 400

    transaction = result.get("data", {})

    if transaction.get("status") != "success":
        return "Payment was not successful.", 400

    # Get logged-in user
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]

    # Get user's cart
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT product_id, quantity FROM cart WHERE \"user\"=%s",
            (user_id,)
        )

        cart_rows = cursor.fetchall()

        product_map = {p['id']: p for p in products}

        order_number = "AV-" + uuid.uuid4().hex[:8].upper()

        for product_id, quantity in cart_rows:

            product = product_map.get(int(product_id))

            if product:
                cursor.execute(
                    """
                    INSERT INTO orders
                    ("user", product_name, price, quantity, order_number)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        product["name"],
                        product["price"],
                        quantity,
                        order_number
                    )
                )

        # Clear cart after successful payment
        cursor.execute(
            "DELETE FROM cart WHERE \"user\"=%s",
            (user_id,)
        )

        conn.commit()

    return redirect("/success")

@app.route("/success")
def success():
    return render_template("success.html")

@app.route("/orders")
def orders():

    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, product_name, price, quantity, order_number
            FROM orders
            WHERE "user"=%s
            ORDER BY id DESC
            """,
            (user_id,)
        )

        order_items = cursor.fetchall()

    return render_template(
        "orders.html",
        order_items=order_items
    )

@app.route('/cancel')
def cancel():
    return "Payment Cancelled ❌"

def init_db():
    with get_db_connection() as db:
        cursor = db.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            "user" TEXT,
            product_id TEXT,
            quantity INTEGER
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            "user" TEXT,
            product_name TEXT,
            price REAL,
            quantity INTEGER,
            order_number TEXT
        )
        """)

        db.commit()

init_db()

# ▶️ RUN APP
if __name__ == "__main__":
    app.run(debug=False)