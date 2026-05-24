from flask import Flask, render_template, request, redirect, flash
from db import get_db
from generator import generate_timetable

app = Flask(__name__)
app.secret_key = "secret123"

@app.route("/")
def home():
    return render_template("home.html")

# -------------------------------
# ADD SUBJECT
# -------------------------------
@app.route("/add_data", methods=["GET", "POST"])
def add_data():
    db = get_db()
    cursor = db.cursor()

    if request.method == "POST":
        cursor.execute("""
            INSERT INTO subjects (name,type,hours,class_id,faculty_id)
            VALUES (%s,%s,%s,%s,%s)
        """, (
            request.form['subject'],
            request.form['type'],
            request.form['hours'],
            request.form['class'],
            request.form['faculty']
        ))

        db.commit()
        flash("Subject added successfully!", "success")
        return redirect("/add_data")

    cursor.execute("SELECT * FROM classes")
    classes = cursor.fetchall()

    cursor.execute("SELECT * FROM faculty")
    faculty = cursor.fetchall()

    return render_template("add_data.html", classes=classes, faculty=faculty)

# -------------------------------
# ADD ROOM
# -------------------------------
@app.route("/add_room", methods=["GET","POST"])
def add_room():
    db = get_db()
    cursor = db.cursor()

    if request.method == "POST":
        cursor.execute("INSERT INTO rooms (name,type) VALUES (%s,%s)",
                       (request.form['name'], request.form['type']))
        db.commit()

        flash("Room added successfully!", "success")
        return redirect("/add_room")

    return render_template("add_room.html")

# -------------------------------
# ADD FACULTY PAGE
# -------------------------------

@app.route("/add_faculty", methods=["GET","POST"])
def add_faculty():
    db = get_db()
    cursor = db.cursor()

    if request.method == "POST":
        name = request.form['name']

        cursor.execute("INSERT INTO faculty (name) VALUES (%s)", (name,))
        db.commit()

        flash("Faculty added successfully!", "success")
        return redirect("/add_faculty")

    cursor.execute("SELECT * FROM faculty")
    faculty = cursor.fetchall()

    return render_template("add_faculty.html", faculty=faculty)

# -------------------------------
# ADD CLASS
# -------------------------------

@app.route("/add_class", methods=["GET","POST"])
def add_class():
    db = get_db()
    cursor = db.cursor()

    if request.method == "POST":
        name = request.form['name']

        cursor.execute("INSERT INTO classes (name) VALUES (%s)", (name,))
        db.commit()

        flash("Class added successfully!", "success")
        return redirect("/add_class")

    cursor.execute("SELECT * FROM classes")
    classes = cursor.fetchall()

    return render_template("add_class.html", classes=classes)

# -------------------------------
# ASSIGN BATCH
# -------------------------------

@app.route("/assign_batch", methods=["GET","POST"])
def assign_batch():
    db = get_db()
    cursor = db.cursor()

    if request.method == "POST":
        class_id = request.form['class']
        subject_id = request.form['subject']

        # Delete old assignment (avoid duplicates)
        cursor.execute("""
            DELETE FROM batch_faculty 
            WHERE class_id=%s AND subject_id=%s
        """, (class_id, subject_id))

        for batch in ['A1','A2','A3','A4']:
            faculty_id = request.form[batch]

            cursor.execute("""
                INSERT INTO batch_faculty (class_id, subject_id, batch, faculty_id)
                VALUES (%s,%s,%s,%s)
            """, (class_id, subject_id, batch, faculty_id))

        db.commit()

        flash("Batch assigned successfully!", "success")
        return redirect("/assign_batch")

    # Load data
    cursor.execute("SELECT * FROM classes")
    classes = cursor.fetchall()

    cursor.execute("SELECT * FROM subjects WHERE type='Practical'")
    subjects = cursor.fetchall()

    cursor.execute("SELECT * FROM faculty")
    faculty = cursor.fetchall()

    return render_template("assign_batch.html",
                           classes=classes,
                           subjects=subjects,
                           faculty=faculty)

# -------------------------------
# VIEW DATA
# -------------------------------
@app.route("/view_data")
def view_data():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM subjects")
    subjects = cursor.fetchall()

    cursor.execute("SELECT * FROM rooms")
    rooms = cursor.fetchall()

    return render_template("view_data.html", subjects=subjects, rooms=rooms)

# -------------------------------
# DELETE
# -------------------------------
@app.route("/delete_subject/<int:id>")
def delete_subject(id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("DELETE FROM subjects WHERE id=%s", (id,))
    db.commit()

    flash("Subject deleted successfully!", "success")
    return redirect("/view_data")

@app.route("/delete_room/<int:id>")
def delete_room(id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("DELETE FROM rooms WHERE id=%s", (id,))
    db.commit()

    flash("Room deleted successfully!", "success")
    return redirect("/view_data")

# -------------------------------
# EDIT SUBJECT
# -------------------------------
@app.route("/edit_subject/<int:id>", methods=["GET","POST"])
def edit_subject(id):
    db = get_db()
    cursor = db.cursor()

    if request.method == "POST":
        cursor.execute("""
            UPDATE subjects SET name=%s,type=%s,hours=%s WHERE id=%s
        """, (
            request.form['name'],
            request.form['type'],
            request.form['hours'],
            id
        ))
        db.commit()

        flash("Subject updated!", "success")
        return redirect("/view_data")

    cursor.execute("SELECT * FROM subjects WHERE id=%s", (id,))
    subject = cursor.fetchone()

    return render_template("edit_subject.html", subject=subject)

# -------------------------------
# EDIT ROOM
# -------------------------------
@app.route("/edit_room/<int:id>", methods=["GET","POST"])
def edit_room(id):
    db = get_db()
    cursor = db.cursor()

    if request.method == "POST":
        cursor.execute("""
            UPDATE rooms SET name=%s,type=%s WHERE id=%s
        """, (
            request.form['name'],
            request.form['type'],
            id
        ))
        db.commit()

        flash("Room updated!", "success")
        return redirect("/view_data")

    cursor.execute("SELECT * FROM rooms WHERE id=%s", (id,))
    room = cursor.fetchone()

    return render_template("edit_room.html", room=room)

# -------------------------------
# TIMETABLE
# -------------------------------
@app.route("/timetable")
def timetable():
    db = get_db()
    tt = generate_timetable(db)
    return render_template("timetable.html", timetable=tt)

if __name__ == "__main__":
    app.run(debug=True)