"""Browser-based registration and administrator account creation."""
import re
import secrets
from functools import wraps

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from pymysql.err import IntegrityError
from werkzeug.security import generate_password_hash

from db import execute_db, query_db

accounts = Blueprint('accounts', __name__)
ROLE_LABELS = {
    'district_admin': 'District Administrator',
    'ministry': 'Nodal Ministry / MP',
    'auditor': 'Auditor',
    'vendor': 'Vendor / Contractor',
    'citizen': 'Citizen / Public',
}


def can_manage_users():
    """Only an existing administrator with access to all districts may add users."""
    user = session.get('user')
    if not user or user.get('role') != 'district_admin':
        return False
    row = query_db('SELECT role, district FROM users WHERE user_id=%s', [user['user_id']], one=True)
    return bool(row and row['role'] == 'district_admin' and not row['district'])


def csrf_token():
    if 'account_csrf' not in session:
        session['account_csrf'] = secrets.token_urlsafe(32)
    return session['account_csrf']


def valid_csrf():
    expected = session.get('account_csrf', '')
    supplied = request.form.get('csrf_token', '')
    return bool(expected and secrets.compare_digest(expected, supplied))


def create_account(form, public=False):
    """Validate and insert an account; public registration always creates a citizen."""
    username = form.get('username', '').strip()
    name = form.get('full_name', '').strip()
    password = form.get('password', '')
    role = 'citizen' if public else form.get('role', '')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,50}', username):
        return 'Username must contain 3-50 letters, numbers, dots, underscores or hyphens.'
    if not name or len(name) > 100:
        return 'Enter a full name of up to 100 characters.'
    if not 8 <= len(password) <= 128:
        return 'Password must contain 8-128 characters.'
    if password != form.get('confirm_password', ''):
        return 'Passwords do not match.'
    if role not in ROLE_LABELS:
        return 'Choose a valid role.'
    district = mp_id = vendor_id = None
    if not public:
        scope = form.get('scope', '').strip()
        if role == 'district_admin':
            if len(scope) > 100:
                return 'District must contain at most 100 characters.'
            district = scope or None
        elif role == 'ministry':
            if len(scope) > 50:
                return 'MP identifier must contain at most 50 characters.'
            mp_id = scope or None
        elif role == 'vendor':
            if not scope or len(scope) > 100:
                return 'A vendor needs a vendor identifier of up to 100 characters.'
            vendor_id = scope
    try:
        execute_db('INSERT INTO users (username,password_hash,full_name,role,district,mp_id,vendor_id) '
                   'VALUES (%s,%s,%s,%s,%s,%s,%s)',
                   [username, generate_password_hash(password), name, role, district, mp_id, vendor_id])
    except IntegrityError as exc:
        if exc.args[0] == 1062:
            return 'That username is already taken. Choose another username.'
        raise
    return None


@accounts.route('/signup', methods=['GET', 'POST'])
def signup():
    if session.get('user'):
        return redirect(url_for('dashboard_page'))
    error = None
    status = 200
    if request.method == 'POST':
        if not valid_csrf():
            error = 'Your form expired. Please try again.'
            status = 400
        else:
            error = create_account(request.form, public=True)
            if error:
                status = 400
            else:
                session['account_notice'] = 'Account created successfully. Log in with your new username and password.'
                return redirect(url_for('login_page'))
    return render_template('signup.html', error=error, token=csrf_token(), values=request.form), status


@accounts.route('/users', methods=['GET', 'POST'])
def manage_users():
    if not session.get('user'):
        return redirect(url_for('login_page', next='/users'))
    if not can_manage_users():
        return render_template('users_denied.html', active_page='users'), 403
    error = None
    status = 200
    if request.method == 'POST':
        if not valid_csrf():
            error = 'Your form expired. Please try again.'
            status = 400
        else:
            error = create_account(request.form)
            if error:
                status = 400
            else:
                session['users_notice'] = 'User added successfully. They can now log in.'
                return redirect(url_for('accounts.manage_users'))
    users = query_db('SELECT username,full_name,role,district,mp_id,vendor_id,created_at '
                     'FROM users ORDER BY created_at DESC,user_id DESC')
    return render_template('users.html', active_page='users', error=error,
                           notice=session.pop('users_notice', None), users=users,
                           role_labels=ROLE_LABELS, token=csrf_token(), values=request.form), status
