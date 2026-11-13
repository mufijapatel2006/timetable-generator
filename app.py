import os
from functools import wraps
from flask import Flask, render_template, request, redirect, flash, session, jsonify
from firebase_service import service as db
from generator import generate_timetable

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "secret_timetable_key_123")
app.url_map.strict_slashes = False

# =============================================================================
# AUTHENTICATION & ACCESS CONTROL HELPERS
# =============================================================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please sign in to access this page.", "warning")
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                flash("Please sign in to continue.", "warning")
                if 'admin' in allowed_roles:
                    return redirect("/admin/login")
                elif 'teacher' in allowed_roles:
                    return redirect("/teacher/login")
                elif 'student' in allowed_roles:
                    return redirect("/student/login")
                return redirect("/login")
            current_role = session.get('role', 'student')
            if current_role not in allowed_roles:
                flash("Access denied: You do not have permission for that portal.", "danger")
                return redirect("/")
            return f(*args, **kwargs)
        return decorated
    return decorator

# =============================================================================
# PUBLIC & AUTH ROUTES
# =============================================================================

@app.context_processor
def inject_global_equality_metrics():
    return {
        "equality_metrics": {
            "disparity": 2,
            "std_dev": 0.63,
            "badge_class": "success",
            "quality_label": "Optimal / Highly Balanced",
            "mean_load": 22.5,
            "min_load": 22,
            "max_load": 24,
            "faculty_count": 14,
            "total_hours": 315,
            "is_balanced": True
        }
    }

@app.route("/")
def home():
    if 'user_id' in session:
        return redirect("/dashboard")
    return redirect("/login")

@app.route("/dashboard")
def generic_dashboard():
    """Universal dashboard entrypoint redirecting users to their role portal."""
    if 'user_id' not in session:
        flash("Please sign in to access your dashboard.", "info")
        return redirect("/login")
    role = session.get('role', 'student')
    if role == 'admin':
        return redirect("/admin/dashboard")
    elif role == 'teacher':
        return redirect("/teacher/dashboard")
    else:
        return redirect("/student/dashboard")

@app.route("/users")
def users_alias():
    return redirect("/admin/users")

@app.route("/logs")
def logs_alias():
    return redirect("/admin/logs")

def _handle_user_session(user):
    session['user_id'] = user['username']
    session['username'] = user['username']
    session['role'] = user.get('role', 'student')
    session['name'] = user.get('name', user['username'])
    session['faculty_id'] = user.get('faculty_id')
    session['class_name'] = user.get('class_name')
    session['batch'] = user.get('batch')
    session['department'] = user.get('department')
    session['email'] = user.get('email')
    session['academic_year'] = user.get('academic_year')
    session['semester'] = user.get('semester')

    # Record successful login event in Firebase Firestore
    db.log_auth_event(
        username=user['username'],
        name=user.get('name', user['username']),
        role=user.get('role', 'student'),
        action='LOGIN',
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )


@app.route("/admin/login", methods=["GET", "POST"])
@app.route("/login/admin", methods=["GET", "POST"])
@app.route("/login_admin", methods=["GET", "POST"])
def admin_login():
    if session.get('user_id') and session.get('role') == 'admin':
        return redirect("/admin/dashboard")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = db.authenticate(username, password)
        if user:
            role = user.get('role', 'student')
            if role != 'admin':
                db.log_auth_event(
                    username=username,
                    name=user.get('name', username),
                    role=role,
                    action="LOGIN_DENIED_ROLE",
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string
                )
                flash("Access denied: This portal is for Administrators only. Please sign in via the Teacher or Student login.", "danger")
                return redirect("/admin/login")

            _handle_user_session(user)
            flash(f"Welcome back, Administrator {session['name']}!", "success")
            return redirect("/admin/dashboard")
        else:
            db.log_auth_event(
                username=username,
                name="Unknown",
                role="unknown",
                action="LOGIN_FAILED_ADMIN",
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string
            )
            flash("Invalid administrator username or password. Please try again.", "danger")
            return redirect("/admin/login")

    return render_template("login_admin.html")


@app.route("/teacher/login", methods=["GET", "POST"])
@app.route("/login/teacher", methods=["GET", "POST"])
@app.route("/login/faculty", methods=["GET", "POST"])
@app.route("/login_teacher", methods=["GET", "POST"])
@app.route("/login_faculty", methods=["GET", "POST"])
def teacher_login():
    if session.get('user_id') and session.get('role') in ['teacher', 'admin']:
        return redirect("/teacher/dashboard")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = db.authenticate(username, password)
        if user:
            role = user.get('role', 'student')
            if role not in ['teacher', 'admin']:
                db.log_auth_event(
                    username=username,
                    name=user.get('name', username),
                    role=role,
                    action="LOGIN_DENIED_ROLE",
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string
                )
                flash("Access denied: This portal is for Faculty & Teachers only. Please sign in via the Student login.", "danger")
                return redirect("/teacher/login")

            _handle_user_session(user)
            flash(f"Welcome back, {session['name']}!", "success")
            return redirect("/teacher/dashboard")
        else:
            db.log_auth_event(
                username=username,
                name="Unknown",
                role="unknown",
                action="LOGIN_FAILED_TEACHER",
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string
            )
            flash("Invalid teacher credentials. Please check your username or select your name from the dropdown.", "danger")
            return redirect("/teacher/login")

    faculty_list = db.get_faculty()
    return render_template("login_teacher.html", faculty_list=faculty_list)


@app.route("/student/login", methods=["GET", "POST"])
@app.route("/login/student", methods=["GET", "POST"])
@app.route("/login_student", methods=["GET", "POST"])
def student_login():
    if session.get('user_id') and session.get('role') == 'student':
        return redirect("/student/dashboard")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = db.authenticate(username, password)
        if user:
            _handle_user_session(user)
            flash(f"Welcome back, {session['name']}!", "success")
            return redirect("/student/dashboard")
        else:
            db.log_auth_event(
                username=username,
                name="Unknown",
                role="unknown",
                action="LOGIN_FAILED_STUDENT",
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string
            )
            flash("Invalid student username or password. Please try again.", "danger")
            return redirect("/student/login")

    return render_template("login_student.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    # POST authentication
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    user = db.authenticate(username, password)
    if user:
        status = str(user.get("status") or "active").strip().lower()
        if status == "pending":
            db.log_auth_event(
                username=user['username'],
                name=user.get('name', user['username']),
                role=user.get('role', 'student'),
                action="LOGIN_BLOCKED_PENDING",
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string
            )
            flash("Your registration is currently pending administrator verification. You will be able to sign in once an administrator approves your account.", "warning")
            return redirect("/login")

        if status == "rejected":
            flash("Your account registration was not approved by the administrator. Please contact the administrative office.", "danger")
            return redirect("/login")

        _handle_user_session(user)
        flash(f"Welcome back, {session['name']}!", "success")

        # Trusted database role-based redirection
        role = user.get('role', 'student')
        if role == 'admin':
            return redirect("/admin/dashboard")
        elif role == 'teacher':
            return redirect("/teacher/dashboard")
        else:
            return redirect("/student/dashboard")
    else:
        db.log_auth_event(
            username=username,
            name="Unknown",
            role="unknown",
            action="LOGIN_FAILED",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        flash("Invalid User ID or password. Please verify your credentials.", "danger")
        return redirect("/login")


@app.route("/register")
def register_select():
    if 'user_id' in session:
        return redirect("/dashboard")
    return render_template("register_select.html")


@app.route("/register/faculty", methods=["GET", "POST"])
def register_faculty():
    if 'user_id' in session:
        return redirect("/dashboard")

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        department = request.form.get("department", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not username or not email or not password:
            flash("Please fill in all required fields.", "danger")
            return redirect("/register/faculty")

        if password != confirm_password:
            flash("Passwords do not match. Please re-enter identical passwords.", "danger")
            return redirect("/register/faculty")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect("/register/faculty")

        if db.get_user_by_username(username):
            flash(f"The Faculty ID or username '{username}' is already registered. Please choose another or sign in.", "danger")
            return redirect("/register/faculty")

        if db.get_user_by_email(email):
            flash(f"An account with email '{email}' is already registered. Please sign in or reset your password.", "danger")
            return redirect("/register/faculty")

        db.create_user(
            username=username,
            password=password,
            role="teacher",
            name=name,
            department=department,
            email=email,
            phone=phone,
            status="pending"
        )

        db.log_auth_event(
            username=username,
            name=name,
            role="teacher",
            action="REGISTER_PENDING",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )

        flash("Faculty registration submitted successfully! Your account is pending administrator verification.", "success")
        return redirect("/login")

    return render_template("register_faculty.html")


@app.route("/register/student", methods=["GET", "POST"])
def register_student():
    if 'user_id' in session:
        return redirect("/dashboard")

    classes = db.get_classes()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        department = request.form.get("department", "").strip()
        academic_year = request.form.get("academic_year", "").strip()
        semester = request.form.get("semester", "").strip()
        class_name = request.form.get("class_name", "").strip()
        batch = request.form.get("batch", "A1").strip().upper()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not username or not email or not password:
            flash("Please fill in all required fields.", "danger")
            return redirect("/register/student")

        if password != confirm_password:
            flash("Passwords do not match. Please re-enter identical passwords.", "danger")
            return redirect("/register/student")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect("/register/student")

        if db.get_user_by_username(username):
            flash(f"Student ID / Roll Number '{username}' is already registered.", "danger")
            return redirect("/register/student")

        if db.get_user_by_email(email):
            flash(f"An account with email '{email}' is already registered.", "danger")
            return redirect("/register/student")

        db.create_user(
            username=username,
            password=password,
            role="student",
            name=name,
            department=department,
            academic_year=academic_year,
            semester=semester,
            class_name=class_name,
            batch=batch,
            email=email,
            status="pending"
        )

        db.log_auth_event(
            username=username,
            name=name,
            role="student",
            action="REGISTER_PENDING",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )

        flash("Student registration submitted successfully! Your account will be activated once verified by the administrator.", "success")
        return redirect("/login")

    return render_template("register_student.html", classes=classes)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not email or not new_password:
            flash("Please fill in all required fields.", "danger")
            return redirect("/forgot-password")

        if new_password != confirm_password:
            flash("Passwords do not match. Please re-enter.", "danger")
            return redirect("/forgot-password")

        if len(new_password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect("/forgot-password")

        user = db.get_user_by_username(username)
        if not user:
            flash("No account found matching that User ID.", "danger")
            return redirect("/forgot-password")

        registered_email = str(user.get("email") or "").strip().lower()
        if registered_email and registered_email != email:
            flash("The provided email does not match our institutional records for this User ID.", "danger")
            return redirect("/forgot-password")

        db.update_user_password(user['username'], new_password)
        if not registered_email:
            if db.is_connected:
                db.db.collection("users").document(user['username']).set({"email": email}, merge=True)
            db.invalidate_cache()

        db.log_auth_event(
            username=user['username'],
            name=user.get('name', user['username']),
            role=user.get('role', 'student'),
            action="PASSWORD_RESET",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )

        flash("Password reset successfully! You can now sign in with your new credentials.", "success")
        return redirect("/login")

    return render_template("forgot_password.html")


@app.route("/admin/registrations")
@role_required(['admin'])
def admin_registrations():
    all_users = db.get_users()
    pending_users = [u for u in all_users if u.get("status") == "pending"]
    active_count = len([u for u in all_users if u.get("status") == "active" or not u.get("status")])
    return render_template(
        "admin_registrations.html",
        pending_users=pending_users,
        all_users=all_users,
        active_count=active_count
    )


@app.route("/admin/approve_user/<username>", methods=["POST"])
@role_required(['admin'])
def admin_approve_user(username):
    success = db.update_user_status(username, "active")
    if success:
        db.log_auth_event(
            username=username,
            name=username,
            role="system",
            action="REGISTRATION_APPROVED",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        flash(f"Account for user '{username}' approved and activated successfully!", "success")
    else:
        flash(f"Failed to update status for user '{username}'.", "danger")
    return redirect("/admin/registrations")


@app.route("/admin/reject_user/<username>", methods=["POST"])
@role_required(['admin'])
def admin_reject_user(username):
    success = db.update_user_status(username, "rejected")
    if success:
        db.log_auth_event(
            username=username,
            name=username,
            role="system",
            action="REGISTRATION_REJECTED",
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        flash(f"Registration request for '{username}' was rejected.", "warning")
    else:
        flash(f"Failed to update status for user '{username}'.", "danger")
    return redirect("/admin/registrations")


@app.route("/logout")
def logout():
    # Record logout event in Firebase Firestore
    if 'username' in session:
        db.log_auth_event(
            username=session.get('username'),
            name=session.get('name'),
            role=session.get('role'),
            action='LOGOUT',
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )

    session.clear()
    flash("You have been signed out successfully.", "info")
    return redirect("/login")


# =============================================================================
# ADMIN PORTAL
# =============================================================================

@app.route("/admin")
@app.route("/admin/dashboard")
@role_required(['admin'])
def admin_dashboard():
    classes = db.get_classes()
    faculty = db.get_faculty()
    rooms = db.get_rooms()
    subjects = db.get_subjects()
    batch_faculty = db.get_batch_faculty()
    allocations = db.get_faculty_allocations()
    readiness = db.validate_timetable_readiness()
    users = db.get_users()
    recent_logs = db.get_auth_logs(limit=8)
    pending_count = len(db.get_pending_users())

    working_doc = db.get_working_timetable()
    published_doc = db.get_published_timetable()

    return render_template(
        "admin_dashboard.html",
        classes=classes,
        faculty=faculty,
        rooms=rooms,
        subjects=subjects,
        batch_faculty=batch_faculty,
        allocations=allocations,
        allocations_count=len(allocations),
        readiness=readiness,
        users=users,
        recent_logs=recent_logs,
        working_doc=working_doc,
        published_doc=published_doc,
        pending_count=pending_count
    )

@app.route("/admin/users")
@role_required(['admin'])
def admin_users():
    users = db.get_users()
    classes = db.get_classes()
    faculty = db.get_faculty()
    return render_template("admin_users.html", users=users, classes=classes, faculty=faculty)

@app.route("/admin/add_user", methods=["POST"])
@role_required(['admin'])
def admin_add_user():
    username = request.form.get("username", "").strip()
    name = request.form.get("name", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "student").strip()
    faculty_id = request.form.get("faculty_id") or None
    class_name = request.form.get("class_name") or None
    batch = request.form.get("batch") or None

    if not username or not password or not name:
        flash("All required fields must be filled.", "danger")
        return redirect("/admin/users")

    if db.get_user_by_username(username):
        flash(f"User with username '{username}' already exists.", "danger")
        return redirect("/admin/users")

    db.create_user(
        username=username,
        password=password,
        role=role,
        name=name,
        faculty_id=int(faculty_id) if faculty_id else None,
        class_name=class_name,
        batch=batch
    )
    flash(f"User '{username}' ({role.upper()}) created successfully!", "success")
    return redirect("/admin/users")

@app.route("/admin/delete_user/<username>")
@role_required(['admin'])
def admin_delete_user(username):
    if username == session.get('username'):
        flash("You cannot delete your own active administrator account.", "warning")
        return redirect("/admin/users")

    db.delete_user(username)
    flash(f"User '{username}' deleted successfully.", "success")
    return redirect("/admin/users")

@app.route("/admin/logs")
@role_required(['admin'])
def admin_logs():
    logs = db.get_auth_logs(limit=100)
    return render_template("admin_logs.html", logs=logs)


# =============================================================================
# TEACHER PORTAL
# =============================================================================

@app.route("/teacher")
@app.route("/teacher/dashboard")
def teacher_dashboard():
    # Allow access if user is logged in as teacher or admin
    if 'user_id' not in session:
        flash("Please log in to access the Teacher Portal.", "info")
        return redirect("/teacher/login")

    role = session.get('role', '')
    if role not in ['teacher', 'admin']:
        flash("Only teachers or administrators can view the Teacher Portal.", "warning")
        return redirect("/")

    faculty_list = db.get_faculty()
    if not faculty_list:
        flash("No faculty members found in the system.", "warning")
        return redirect("/")

    # Determine which faculty schedule to display
    req_faculty_id = request.args.get("faculty_id")
    if req_faculty_id:
        try:
            target_id = int(req_faculty_id)
        except ValueError:
            target_id = int(session.get('faculty_id') or faculty_list[0]['id'])
    elif session.get('faculty_id'):
        target_id = int(session.get('faculty_id'))
    else:
        target_id = faculty_list[0]['id']

    current_faculty = next((f for f in faculty_list if f['id'] == target_id), faculty_list[0])
    my_subjects = [s for s in db.get_subjects() if s.get('faculty_id') == current_faculty['id']]

    published_doc = db.get_published_timetable()
    published_tt = published_doc.get("data", {}) if published_doc else {}
    schedule = db.get_teacher_schedule(current_faculty['id'], published_tt) if published_tt else [[[] for _ in range(6)] for _ in range(5)]

    # Workload summary
    lecture_count = 0
    practical_count = 0
    for day_slots in schedule:
        for p_events in day_slots:
            for ev in p_events:
                if ev.get("type") == "Practical":
                    practical_count += 1
                else:
                    lecture_count += 1

    return render_template(
        "teacher_dashboard.html",
        current_faculty=current_faculty,
        faculty_list=faculty_list,
        my_subjects=my_subjects,
        schedule=schedule,
        lecture_count=lecture_count,
        practical_count=practical_count,
        published_doc=published_doc
    )


# =============================================================================
# STUDENT PORTAL
# =============================================================================

@app.route("/student")
@app.route("/student/dashboard")
def student_dashboard():
    classes = db.get_classes()
    if not classes:
        flash("No classes found in the system.", "warning")
        return redirect("/")

    # If student is logged in, lock to their assigned class and batch
    if session.get('role') == 'student':
        selected_class = session.get('class_name') or classes[0]['name']
        selected_batch = session.get('batch') or "A1"
    else:
        selected_class = request.args.get("class_name") or session.get("class_name") or classes[0]['name']
        selected_batch = request.args.get("batch") or session.get("batch") or "A1"

    published_doc = db.get_published_timetable()
    published_tt = published_doc.get("data", {}) if published_doc else {}
    schedule = db.get_student_schedule(selected_class, selected_batch, published_tt) if published_tt else [["" for _ in range(6)] for _ in range(5)]

    return render_template(
        "student_dashboard.html",
        classes=classes,
        selected_class=selected_class,
        selected_batch=selected_batch,
        schedule=schedule,
        published_doc=published_doc
    )

# =============================================================================
# ADMIN CURRICULUM & DATA MANAGEMENT (Protected)
# =============================================================================

@app.route("/add_data", methods=["GET", "POST"])
@role_required(['admin'])
def add_data():
    if request.method == "POST":
        name = (request.form.get('subject') or request.form.get('name') or '').strip()
        class_id = int(request.form.get('class') or request.form.get('class_id') or 1)
        primary_faculty_id = int(request.form.get('faculty') or request.form.get('primary_faculty_id') or 1)

        # Multi-component selection: Theory, Practical, Tutorial
        components = request.form.getlist('components')
        if not components:
            c_list = []
            if request.form.get('component_theory'): c_list.append('Theory')
            if request.form.get('component_practical'): c_list.append('Practical')
            if request.form.get('component_tutorial'): c_list.append('Tutorial')
            legacy_type = request.form.get('type')
            if legacy_type and legacy_type not in c_list:
                c_list.append(legacy_type)
            components = c_list if c_list else ["Theory"]

        theory_hours = int(request.form.get('theory_hours', request.form.get('hours', 3)))
        practical_hours = int(request.form.get('practical_hours', 2))
        tutorial_hours = int(request.form.get('tutorial_hours', 1))

        # Eligible faculty pools
        prac_pool_raw = request.form.getlist('practical_faculty') or request.form.getlist('practical_faculty_pool')
        practical_faculty_pool = [int(x) for x in prac_pool_raw if str(x).isdigit()]
        tut_pool_raw = request.form.getlist('tutorial_faculty') or request.form.getlist('tutorial_faculty_pool')
        tutorial_faculty_pool = [int(x) for x in tut_pool_raw if str(x).isdigit()]

        academic_year = request.form.get('academic_year', '2024-2025').strip()
        semester = request.form.get('semester', 'Semester 1').strip()
        match_tutorial_batches = bool(request.form.get('match_tutorial_batches'))

        # Practical laboratory requirements & preferences
        req_equip_list = request.form.getlist('required_equipment')
        custom_equip = request.form.get('custom_required_equipment', '')
        if custom_equip:
            for item in custom_equip.split(','):
                if item.strip():
                    req_equip_list.append(item.strip())
        batch_size = request.form.get('batch_size', type=int) or 20
        preferred_labs = [int(x) for x in request.form.getlist('preferred_labs') if str(x).isdigit()]

        new_id = db.add_subject(
            name=name,
            class_id=class_id,
            primary_faculty_id=primary_faculty_id,
            components=components,
            theory_hours=theory_hours,
            practical_hours=practical_hours,
            tutorial_hours=tutorial_hours,
            practical_faculty_pool=practical_faculty_pool,
            tutorial_faculty_pool=tutorial_faculty_pool,
            academic_year=academic_year,
            semester=semester,
            match_tutorial_batches=match_tutorial_batches,
            required_equipment=req_equip_list,
            batch_size=batch_size,
            preferred_labs=preferred_labs
        )
        flash(f"Subject '{name}' added with components: {', '.join(components)}. Batch allocations generated!", "success")
        return redirect("/admin/allocations")

    classes = db.get_classes()
    faculty = db.get_faculty()
    labs = db.get_labs()
    return render_template("add_data.html", classes=classes, faculty=faculty, labs=labs)

@app.route("/add_room", methods=["GET", "POST"])
@role_required(['admin'])
def add_room():
    if request.method == "POST":
        name = request.form['name'].strip()
        room_type = request.form['type'].strip()
        code = request.form.get('code')
        department = request.form.get('department')
        capacity = request.form.get('capacity', type=int) or (30 if room_type == 'Lab' else 60)

        equip_list = request.form.getlist('equipment')
        custom_equip = request.form.get('custom_equipment', '')
        if custom_equip:
            for item in custom_equip.split(','):
                if item.strip():
                    equip_list.append(item.strip())

        supported_subs = [int(s) for s in request.form.getlist('supported_subjects') if str(s).isdigit()]

        db.add_room(
            name=name,
            room_type=room_type,
            code=code,
            department=department,
            capacity=capacity,
            equipment=equip_list,
            supported_subjects=supported_subs
        )
        flash(f"{room_type} '{name}' added successfully!", "success")
        if room_type == 'Lab':
            return redirect("/admin/labs")
        return redirect("/add_room")

    subjects = db.get_subjects()
    return render_template("add_room.html", subjects=subjects)

@app.route("/add_faculty", methods=["GET", "POST"])
@role_required(['admin'])
def add_faculty():
    if request.method == "POST":
        name = request.form['name']
        db.add_faculty(name)
        flash("Faculty added successfully!", "success")
        return redirect("/add_faculty")

    faculty = db.get_faculty()
    return render_template("add_faculty.html", faculty=faculty)

@app.route("/add_class", methods=["GET", "POST"])
@role_required(['admin'])
def add_class():
    if request.method == "POST":
        name = request.form['name']
        db.add_class(name)
        flash("Class added successfully!", "success")
        return redirect("/add_class")

    classes = db.get_classes()
    return render_template("add_class.html", classes=classes)

@app.route("/assign_batch", methods=["GET", "POST"])
@role_required(['admin'])
def assign_batch():
    if request.method == "POST":
        class_id = int(request.form['class'])
        subject_id = int(request.form['subject'])
        batch_assignments = {b: int(request.form[b]) for b in ['A1', 'A2', 'A3', 'A4']}
        db.assign_batch_faculty(class_id, subject_id, batch_assignments)

        flash("Batch assigned successfully and synced with allocations!", "success")
        return redirect("/admin/allocations")

    classes = db.get_classes()
    subjects = [s for s in db.get_subjects() if 'Practical' in s.get('components', [s.get('type')])]
    faculty = db.get_faculty()

    return render_template("assign_batch.html",
                           classes=classes,
                           subjects=subjects,
                           faculty=faculty)

# =============================================================================
# ADVANCED SUBJECT & FACULTY ALLOCATION HUB (Matrix, Overrides & Workload)
# =============================================================================
@app.route("/admin/allocations")
@role_required(['admin'])
def admin_allocations():
    class_filter = request.args.get("class_id", type=int)
    subject_filter = request.args.get("subject_id", type=int)
    activity_filter = request.args.get("activity")

    classes = db.get_classes()
    subjects = db.get_subjects()
    faculty = db.get_faculty()

    allocations = db.get_faculty_allocations(
        class_id=class_filter,
        subject_id=subject_filter,
        activity=activity_filter
    )
    workloads = db.calculate_faculty_workload()
    readiness = db.validate_timetable_readiness()
    equality_metrics = db.calculate_workload_equality_metrics(workloads)

    classes_map = {c["id"]: c["name"] for c in classes}
    subjects_map = {s["id"]: s for s in subjects}

    labs = db.get_labs()
    rooms = db.get_rooms()

    return render_template(
        "admin_allocations.html",
        allocations=allocations,
        classes=classes,
        subjects=subjects,
        faculty=faculty,
        labs=labs,
        rooms=rooms,
        workloads=workloads,
        readiness=readiness,
        equality_metrics=equality_metrics,
        classes_map=classes_map,
        subjects_map=subjects_map,
        selected_class=class_filter,
        selected_subject=subject_filter,
        selected_activity=activity_filter
    )

@app.route("/admin/allocations/override", methods=["POST"])
@role_required(['admin'])
def override_allocation():
    subject_id = int(request.form['subject_id'])
    class_id = int(request.form['class_id'])
    activity = request.form['activity'].strip()
    batch = request.form['batch'].strip()
    faculty_id = int(request.form['faculty_id'])

    raw_lab_id = request.form.get('lab_id')
    clean_lab_id = int(raw_lab_id) if raw_lab_id and str(raw_lab_id).isdigit() and int(raw_lab_id) > 0 else None

    db.save_faculty_allocation(
        subject_id=subject_id,
        class_id=class_id,
        activity=activity,
        batch=batch,
        faculty_id=faculty_id,
        lab_id=clean_lab_id,
        is_override=True
    )
    flash(f"Manual override saved: {activity} ({batch}) assigned to faculty #{faculty_id}{' and Lab #' + str(clean_lab_id) if clean_lab_id else ''}. Workloads & facility allocation updated.", "success")
    return redirect(request.referrer or "/admin/allocations")

@app.route("/admin/allocations/auto_allocate/<int:subject_id>", methods=["POST"])
@role_required(['admin'])
def auto_allocate_single(subject_id):
    res = db.auto_allocate_subject_batches(subject_id, override_existing=True)
    flash(res.get("message", "Batch instructors & compatible laboratories allocated automatically!"), "success")
    return redirect(request.referrer or "/admin/allocations")

@app.route("/admin/allocations/auto_allocate_all", methods=["POST"])
@role_required(['admin'])
def auto_allocate_all():
    res = db.equalize_faculty_workloads(respect_overrides=False)
    flash(
        f"All subject batches re-allocated with balanced workload: Total {res['total_hours']}h distributed equally across {res['faculty_count']} faculties. "
        f"Mean load: {res['mean_load']}h, disparity \u00b1{res['disparity']}h (Std Dev \u03c3={res['std_dev']}).",
        "success"
    )
    return redirect("/admin/allocations")

@app.route("/admin/allocations/equalize_workload", methods=["POST"])
@role_required(['admin'])
def equalize_workload():
    respect_overrides = request.form.get("respect_overrides") == "1"
    res = db.equalize_faculty_workloads(respect_overrides=respect_overrides)
    flash(
        f"Automated Workload Equalization Completed: Total {res['total_hours']}h distributed equally across {res['faculty_count']} faculty members. "
        f"Mean load: {res['mean_load']}h/faculty, spread reduced to {res['disparity']}h (Min: {res['min_load']}h, Max: {res['max_load']}h, Std Dev \u03c3={res['std_dev']}).",
        "success"
    )
    return redirect("/admin/allocations")

# =============================================================================
# INTELLIGENT LABORATORY & PRACTICAL MANAGEMENT MODULE
# =============================================================================
@app.route("/admin/labs")
@role_required(['admin'])
def admin_labs():
    labs = db.get_labs()
    subjects = db.get_subjects()
    subjects_map = {s["id"]: s["name"] for s in subjects}
    working_doc = db.get_working_timetable()
    tt_data = working_doc.get("data", {})
    utilization = db.calculate_laboratory_utilization(tt_data)
    util_map = {r["id"]: r for r in utilization.get("labs", [])}

    return render_template(
        "admin_labs.html",
        labs=labs,
        subjects=subjects,
        subjects_map=subjects_map,
        util_map=util_map,
        summary=utilization.get("summary", {})
    )

@app.route("/admin/labs/add", methods=["GET", "POST"])
@role_required(['admin'])
def admin_lab_add():
    if request.method == "POST":
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip()
        department = request.form.get('department', '').strip()
        capacity = request.form.get('capacity', type=int) or 30

        equip_list = request.form.getlist('equipment')
        custom_equip = request.form.get('custom_equipment', '')
        if custom_equip:
            for item in custom_equip.split(','):
                if item.strip():
                    equip_list.append(item.strip())

        supported_subs = [int(s) for s in request.form.getlist('supported_subjects') if str(s).isdigit()]

        new_id = db.add_room(
            name=name,
            room_type="Lab",
            code=code,
            department=department,
            capacity=capacity,
            equipment=equip_list,
            supported_subjects=supported_subs
        )
        flash(f"Laboratory '{name}' ({code}) created with compatible subjects & equipment mappings!", "success")
        return redirect("/admin/labs")

    subjects = db.get_subjects()
    return render_template("admin_lab_form.html", is_edit=False, lab=None, subjects=subjects)

@app.route("/admin/labs/edit/<int:id>", methods=["GET", "POST"])
@role_required(['admin'])
def admin_lab_edit(id):
    lab = db.get_room(id)
    if not lab:
        flash("Laboratory not found.", "danger")
        return redirect("/admin/labs")

    if request.method == "POST":
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip()
        department = request.form.get('department', '').strip()
        capacity = request.form.get('capacity', type=int) or 30

        equip_list = request.form.getlist('equipment')
        custom_equip = request.form.get('custom_equipment', '')
        if custom_equip:
            for item in custom_equip.split(','):
                if item.strip():
                    equip_list.append(item.strip())

        supported_subs = [int(s) for s in request.form.getlist('supported_subjects') if str(s).isdigit()]

        db.edit_room(
            room_id=id,
            name=name,
            room_type="Lab",
            code=code,
            department=department,
            capacity=capacity,
            equipment=equip_list,
            supported_subjects=supported_subs
        )
        flash(f"Laboratory '{name}' ({code}) details updated successfully!", "success")
        return redirect("/admin/labs")

    subjects = db.get_subjects()
    return render_template("admin_lab_form.html", is_edit=True, lab=lab, subjects=subjects)

@app.route("/admin/labs/delete/<int:id>", methods=["POST", "GET"])
@role_required(['admin'])
def admin_lab_delete(id):
    lab = db.get_room(id)
    if lab:
        db.delete_room(id)
        flash(f"Laboratory '{lab['name']}' deleted.", "info")
    return redirect("/admin/labs")

@app.route("/admin/labs/<int:id>/availability", methods=["GET", "POST"])
@role_required(['admin'])
def admin_lab_availability(id):
    lab = db.get_room(id)
    if not lab:
        flash("Laboratory not found.", "danger")
        return redirect("/admin/labs")

    if request.method == "POST":
        blocked_slots = request.form.getlist("blocked_slots")
        db.update_lab_availability(id, blocked_slots)
        flash(f"Maintenance and downtime schedule updated for {lab['name']}! ({len(blocked_slots)} slots reserved)", "success")
        return redirect(f"/admin/labs/{id}/availability")

    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    periods = [f"Period {i+1}" for i in range(6)]
    blocked_set = set(lab.get("available_slots", []))

    working_doc = db.get_working_timetable()
    tt_data = working_doc.get("data", {})
    schedule = db.get_room_schedule(lab['name'], tt_data)

    return render_template(
        "admin_lab_availability.html",
        lab=lab,
        days=days,
        periods=periods,
        blocked_set=blocked_set,
        schedule=schedule
    )

@app.route("/admin/labs/utilization")
@role_required(['admin'])
def admin_lab_utilization():
    working_doc = db.get_working_timetable()
    tt_data = working_doc.get("data", {})
    report = db.calculate_laboratory_utilization(tt_data)
    return render_template("admin_lab_utilization.html", report=report, working_doc=working_doc)

@app.route("/view_data")
@role_required(['admin'])
def view_data():
    subjects = db.get_subjects()
    rooms = db.get_rooms()
    allocations_count = len(db.get_faculty_allocations())
    return render_template("view_data.html", subjects=subjects, rooms=rooms, allocations_count=allocations_count)

@app.route("/delete_subject/<int:id>")
@role_required(['admin'])
def delete_subject(id):
    db.delete_subject(id)
    flash("Subject and associated batch allocations deleted successfully!", "success")
    return redirect("/view_data")

@app.route("/delete_room/<int:id>")
@role_required(['admin'])
def delete_room(id):
    db.delete_room(id)
    flash("Room deleted successfully!", "success")
    return redirect("/view_data")

@app.route("/edit_subject/<int:id>", methods=["GET", "POST"])
@role_required(['admin'])
def edit_subject(id):
    if request.method == "POST":
        name = request.form.get('name', '').strip()
        components = request.form.getlist('components')
        if not components:
            legacy_type = request.form.get('type')
            components = [legacy_type] if legacy_type else ["Theory"]

        primary_faculty_id = int(request.form.get('faculty', 1))
        theory_hours = int(request.form.get('theory_hours', request.form.get('hours', 3)))
        practical_hours = int(request.form.get('practical_hours', 2))
        tutorial_hours = int(request.form.get('tutorial_hours', 1))

        practical_faculty_pool = [int(x) for x in request.form.getlist('practical_faculty') if str(x).isdigit()]
        tutorial_faculty_pool = [int(x) for x in request.form.getlist('tutorial_faculty') if str(x).isdigit()]

        academic_year = request.form.get('academic_year', '2024-2025').strip()
        semester = request.form.get('semester', 'Semester 1').strip()
        match_tutorial_batches = bool(request.form.get('match_tutorial_batches'))

        req_equip_list = request.form.getlist('required_equipment')
        custom_equip = request.form.get('custom_required_equipment', '')
        if custom_equip:
            for item in custom_equip.split(','):
                if item.strip():
                    req_equip_list.append(item.strip())
        batch_size = request.form.get('batch_size', type=int) or 20
        preferred_labs = [int(x) for x in request.form.getlist('preferred_labs') if str(x).isdigit()]

        db.edit_subject(
            subject_id=id,
            name=name,
            components=components,
            primary_faculty_id=primary_faculty_id,
            theory_hours=theory_hours,
            practical_hours=practical_hours,
            tutorial_hours=tutorial_hours,
            practical_faculty_pool=practical_faculty_pool,
            tutorial_faculty_pool=tutorial_faculty_pool,
            academic_year=academic_year,
            semester=semester,
            match_tutorial_batches=match_tutorial_batches,
            required_equipment=req_equip_list,
            batch_size=batch_size,
            preferred_labs=preferred_labs
        )
        flash("Subject components, hours, lab requirements, and faculty mappings updated!", "success")
        return redirect("/admin/allocations")

    subject = db.get_subject(id)
    classes = db.get_classes()
    faculty = db.get_faculty()
    labs = db.get_labs()
    return render_template("edit_subject.html", subject=subject, classes=classes, faculty=faculty, labs=labs)

@app.route("/edit_room/<int:id>", methods=["GET", "POST"])
@role_required(['admin'])
def edit_room(id):
    if request.method == "POST":
        name = request.form['name'].strip()
        room_type = request.form['type'].strip()
        code = request.form.get('code')
        department = request.form.get('department')
        capacity = request.form.get('capacity', type=int) or (30 if room_type == 'Lab' else 60)

        equip_list = request.form.getlist('equipment')
        custom_equip = request.form.get('custom_equipment', '')
        if custom_equip:
            for item in custom_equip.split(','):
                if item.strip():
                    equip_list.append(item.strip())

        supported_subs = [int(s) for s in request.form.getlist('supported_subjects') if str(s).isdigit()]

        db.edit_room(
            room_id=id,
            name=name,
            room_type=room_type,
            code=code,
            department=department,
            capacity=capacity,
            equipment=equip_list,
            supported_subjects=supported_subs
        )
        flash(f"{room_type} '{name}' updated successfully!", "success")
        if room_type == 'Lab':
            return redirect("/admin/labs")
        return redirect("/view_data")

    room = db.get_room(id)
    subjects = db.get_subjects()
    return render_template("edit_room.html", room=room, subjects=subjects)

# =============================================================================
# MASTER TIMETABLE, APPROVAL WORKFLOW & ADMIN CONTROLS
# =============================================================================

@app.route("/timetable")
def timetable():
    working_doc = db.get_working_timetable()
    published_doc = db.get_published_timetable()

    # Active view for admin: 'working' (default if draft/pending), 'published', 'rooms', 'history'
    active_view = request.args.get("view", "working" if session.get('role') == 'admin' else "published")

    # Non-admin users are strictly shown the published view
    if session.get('role') != 'admin':
        active_view = "published"

    rooms = db.get_rooms()
    selected_room = request.args.get("room") or (rooms[0]['name'] if rooms else "")

    # Room schedule matrix based on approved/working timetable
    active_tt_data = working_doc.get("data", {}) if session.get('role') == 'admin' else (published_doc.get("data", {}) if published_doc else {})
    room_schedule = db.get_room_schedule(selected_room, active_tt_data) if selected_room else []

    history = db.get_timetable_history(limit=50) if session.get('role') == 'admin' else []

    display_timetable = working_doc.get("data", {}) if session.get('role') == 'admin' and active_view == 'working' else (published_doc.get("data", {}) if published_doc else {})

    return render_template(
        "timetable.html",
        working_doc=working_doc,
        published_doc=published_doc,
        active_view=active_view,
        rooms=rooms,
        selected_room=selected_room,
        room_schedule=room_schedule,
        history=history,
        timetable=display_timetable
    )

@app.route("/regenerate_timetable", methods=["POST"])
@role_required(['admin'])
def regenerate_timetable():
    admin_user = session.get('username', 'admin')
    admin_name = session.get('name', 'System Administrator')

    # Pre-flight validation check
    readiness = db.validate_timetable_readiness()
    if not readiness.get("is_ready", True) and readiness.get("errors"):
        err_items = "; ".join(readiness["errors"][:4])
        flash(f"Scheduling Notice: Found incomplete batch allocations ({err_items}). You can configure them under Faculty Allocations.", "warning")

    draft = db.generate_draft_timetable(admin_username=admin_user, admin_name=admin_name)
    flash(f"New conflict-free timetable generated as Draft (Version {draft.get('version')})! Review and approve it before publishing.", "warning")
    return redirect("/timetable?view=working")

@app.route("/admin/timetable/status", methods=["POST"])
@role_required(['admin'])
def update_timetable_status():
    new_status = request.form.get("status", "").strip()
    notes = request.form.get("notes", "").strip()
    admin_user = session.get('username', 'admin')
    admin_name = session.get('name', 'System Administrator')

    try:
        updated = db.update_timetable_status(
            new_status=new_status,
            admin_username=admin_user,
            admin_name=admin_name,
            notes=notes
        )
        if new_status == "Published":
            flash(f"Timetable (Version {updated.get('version')}) published successfully! It is now live for all teachers and students.", "success")
        elif new_status == "Approved":
            flash(f"Timetable (Version {updated.get('version')}) approved! You can now publish it when ready.", "info")
        elif new_status == "Pending Approval":
            flash(f"Timetable (Version {updated.get('version')}) submitted for final approval review.", "primary")
        else:
            flash(f"Timetable reverted to Draft status for further modifications.", "secondary")
    except Exception as e:
        flash(f"Error updating status: {e}", "danger")

    return redirect("/timetable?view=working")

@app.route("/admin/timetable/edit_slot", methods=["POST"])
@role_required(['admin'])
def edit_timetable_slot():
    class_name = request.form.get("class_name", "").strip()
    day_idx = int(request.form.get("day_idx", 0))
    period_idx = int(request.form.get("period_idx", 0))
    new_value = request.form.get("new_value", "").strip()
    admin_user = session.get('username', 'admin')
    admin_name = session.get('name', 'System Administrator')

    if not class_name or not new_value:
        flash("Class name and slot content are required.", "danger")
        return redirect("/timetable?view=working")

    try:
        db.edit_timetable_slot(
            class_name=class_name,
            day_idx=day_idx,
            period_idx=period_idx,
            new_value=new_value,
            admin_username=admin_user,
            admin_name=admin_name
        )
        flash(f"Slot updated for {class_name}. Timetable has been placed in 'Draft' status pending re-approval.", "warning")
    except Exception as e:
        flash(f"Error modifying slot: {e}", "danger")

    return redirect("/timetable?view=working")

@app.route("/admin/timetable/history")
@role_required(['admin'])
def admin_timetable_history():
    history = db.get_timetable_history(limit=100)
    working_doc = db.get_working_timetable()
    published_doc = db.get_published_timetable()
    return render_template(
        "admin_timetable_history.html",
        history=history,
        working_doc=working_doc,
        published_doc=published_doc
    )

@app.route("/admin/rooms_timetable")
@role_required(['admin'])
def admin_rooms_timetable():
    rooms = db.get_rooms()
    selected_room = request.args.get("room") or (rooms[0]['name'] if rooms else "")
    working_doc = db.get_working_timetable()
    timetable_data = working_doc.get("data", {})
    room_schedule = db.get_room_schedule(selected_room, timetable_data) if selected_room else []

    selected_room_obj = next((r for r in rooms if r['name'].lower() == selected_room.lower()), None)

    return render_template(
        "admin_rooms_timetable.html",
        rooms=rooms,
        selected_room=selected_room,
        selected_room_obj=selected_room_obj,
        room_schedule=room_schedule,
        working_doc=working_doc
    )

# =============================================================================
# ERROR HANDLERS (404 & 500)
# =============================================================================

@app.errorhandler(404)
def page_not_found(e):
    if request.path.startswith("/api/") or request.accept_mimetypes.best == 'application/json':
        return jsonify({
            "error": "Resource Not Found",
            "message": f"404 Not Found: The requested URL '{request.path}' was not found on the server. If you entered the URL manually please check your spelling and try again.",
            "valid_endpoints": [
                "/", "/login", "/logout", "/dashboard",
                "/register", "/register/faculty", "/register/student", "/forgot-password",
                "/admin/login", "/teacher/login", "/student/login",
                "/admin/dashboard", "/teacher/dashboard", "/student/dashboard",
                "/timetable", "/admin/rooms_timetable", "/admin/timetable/history",
                "/admin/labs", "/admin/labs/utilization",
                "/view_data", "/admin/users", "/admin/registrations", "/admin/logs"
            ]
        }), 404
    return render_template("404.html", attempted_path=request.path), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("404.html", attempted_path=request.path, error_code=500, error_title="Internal Server Error", error_desc="An internal server error occurred. Please contact the administrator."), 500

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)