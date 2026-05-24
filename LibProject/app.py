from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your_library_secret_session_key'


# Centralized Database Connection Helper Function Using mysql-connector
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        port=3307,  # Enforces your custom port configuration
        user="root",
        password="Password",  # <--- MAKE SURE TO TYPE YOUR ACTUAL PASSWORD HERE!
        database="Libra"
    )


# 1. LANDING PAGE (Serves signup&login.html)
@app.route('/')
def auth_page():
    return render_template('signup&login.html')


# SIGNUP PROCESSING ROUTE
@app.route('/signup', methods=['POST'])
def signup():
    fname = request.form.get('fname')
    lname = request.form.get('lname')
    admission_no = request.form.get('admission')
    email = request.form.get('email')
    password = request.form.get('password')

    hashed_password = generate_password_hash(password)

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        query = """
            INSERT INTO Students (First_name, Last_name, Admission_no, Email, Passwor_d) 
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(query, (fname, lname, admission_no, email, hashed_password))
        connection.commit()
        flash("Registration successful! Please login below.", "success")
        return redirect(url_for('auth_page') + '?panel=login')
    except Exception as e:
        connection.rollback()
        flash(f"Database error while saving account: {e}", "danger")
        return redirect(url_for('auth_page'))
    finally:
        cursor.close()
        connection.close()


# LOGIN PROCESSING ROUTE (REVERTED)
@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')

    connection = get_db_connection()
    cursor = connection.cursor()

    # Back to original query
    query = "SELECT Admission_no, First_name, Passwor_d FROM Students WHERE Email = %s"
    cursor.execute(query, (email,))
    user = cursor.fetchone()

    cursor.close()
    connection.close()

    if user and check_password_hash(user[2], password):
        session['user_id'] = user[0]
        session['user_name'] = user[1]
        return redirect(url_for('dashboard'))

    flash("Invalid Email address or Password mismatch.", "danger")
    return redirect(url_for('auth_page') + '?panel=login')


# 2. LIBRARY MAIN DASHBOARD
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash("Please log in to access your library system profile dashboard.", "danger")
        return redirect(url_for('auth_page') + '?panel=login')

    # Passing 'is_admin' to the HTML template
    return render_template('dashbord.html', user_name=session['user_name'], is_admin=session.get('is_admin'))


# 3. TEXTBOOK INTERFACE FORMS (Serves index.html for Adding/Borrowing)
@app.route('/forms')
def forms_page():
    if 'user_id' not in session:
        flash("Please log in to add or borrow items.", "danger")
        return redirect(url_for('auth_page') + '?panel=login')
    return render_template('index.html')


# 4. API ENDPOINT: SUBMIT NEW BOOK
@app.route('/api/books', methods=['POST'])
def add_book_api():
    data = request.get_json()
    title = data.get('title')
    author = data.get('author')
    isbn = data.get('isbn')
    category = data.get('category')
    quantity = data.get('copies')

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        query = """
            INSERT INTO Books (Book_title, Author, ISBN, Category, Quantity) 
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE Quantity = Quantity + %s
        """
        cursor.execute(query, (title, author, isbn, category, quantity, quantity))
        connection.commit()
        return jsonify({"message": "Book registered successfully"}), 200
    except Exception as e:
        connection.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        cursor.close()
        connection.close()


# 5. API ENDPOINT: LOG BORROW TRANSACTION
@app.route('/api/borrow', methods=['POST'])
def borrow_book_api():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized session context."}), 401

    data = request.get_json()
    isbn = data.get('isbn')
    issue_date_str = data.get('issueDate')

    issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d')
    due_date = issue_date + timedelta(days=14)
    admission_no = session['user_id']

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT Quantity FROM Books WHERE ISBN = %s", (isbn,))
        book_quantity = cursor.fetchone()

        if not book_quantity or book_quantity[0] < 1:
            return jsonify({"error": "Requested textbook out of stock allocations."}), 400

        insert_query = """
            INSERT INTO Transactions (Issue_Date, Due_Date, ISBN, Admission_no) 
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(insert_query,
                       (issue_date.strftime('%Y-%m-%d'), due_date.strftime('%Y-%m-%d'), isbn, admission_no))

        cursor.execute("UPDATE Books SET Quantity = Quantity - 1 WHERE ISBN = %s", (isbn,))

        connection.commit()
        return jsonify({"message": "Borrow logs synchronized cleanly!"}), 200
    except Exception as e:
        connection.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        cursor.close()
        connection.close()


# 6. SEARCH ROUTE
@app.route('/search')
def search():
    if 'user_id' not in session:
        return redirect(url_for('auth_page') + '?panel=login')

    query_string = request.args.get('q', '')

    connection = get_db_connection()
    cursor = connection.cursor()
    # Search for books where title, author, or ISBN matches the query
    search_query = """
        SELECT Book_title, Author, ISBN, Category, Quantity 
        FROM Books 
        WHERE Book_title LIKE %s OR Author LIKE %s OR ISBN LIKE %s
    """
    wildcard_query = f"%{query_string}%"
    cursor.execute(search_query, (wildcard_query, wildcard_query, wildcard_query))
    results = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template('search.html', results=results, query=query_string)


# 7. SYSTEM LOGS ROUTE
@app.route('/logs')
def logs():
    if 'user_id' not in session:
        return redirect(url_for('auth_page') + '?panel=login')

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)  # Using dictionary=True makes it easier
    cursor.execute("""
        SELECT t.Issue_Date, t.Due_Date, s.First_name, b.Book_title 
        FROM Transactions t
        JOIN Students s ON t.Admission_no = s.Admission_no
        JOIN Books b ON t.ISBN = b.ISBN
        ORDER BY t.Issue_Date DESC
    """)
    log_data = cursor.fetchall()
    cursor.close()
    connection.close()
    return render_template('logs.html', logs=log_data)


# 8. ADMIN PANEL ROUTE (OPEN ACCESS)
@app.route('/admin')
def admin_panel():
    if 'user_id' not in session:
        return redirect(url_for('auth_page') + '?panel=login')

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) FROM Books")
    total_books = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM Students")
    total_students = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM Transactions")
    total_borrows = cursor.fetchone()[0]

    cursor.close()
    connection.close()
    return render_template('admin.html', books=total_books, students=total_students, borrows=total_borrows)
# LOGOUT ROUTE
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth_page') + '?panel=login')


if __name__ == '__main__':
    app.run(debug=True)