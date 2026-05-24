CREATE DATABASE timetable_database;
USE timetable_database;

CREATE TABLE classes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50)
);

CREATE TABLE faculty (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100)
);

CREATE TABLE subjects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100),
    type ENUM('Theory','Practical'),
    hours INT,
    class_id INT,
    faculty_id INT,
    FOREIGN KEY (class_id) REFERENCES classes(id),
    FOREIGN KEY (faculty_id) REFERENCES faculty(id)
);

CREATE TABLE rooms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50),
    type ENUM('Classroom','Lab')
);

CREATE TABLE batch_faculty (
    id INT AUTO_INCREMENT PRIMARY KEY,
    class_id INT,
    subject_id INT,
    batch VARCHAR(10),
    faculty_id INT,
    FOREIGN KEY (class_id) REFERENCES classes(id),
    FOREIGN KEY (subject_id) REFERENCES subjects(id),
    FOREIGN KEY (faculty_id) REFERENCES faculty(id)
);

CREATE TABLE batch_subject (
    id INT AUTO_INCREMENT PRIMARY KEY,

    class_id INT,
    batch VARCHAR(10),

    subject_id INT,
    faculty_id INT,

    group_no INT DEFAULT 1,

    FOREIGN KEY (class_id) REFERENCES classes(id),
    FOREIGN KEY (subject_id) REFERENCES subjects(id),
    FOREIGN KEY (faculty_id) REFERENCES faculty(id)
);