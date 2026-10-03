from django.contrib.auth import views as auth
from django.urls import path
from . import views, students
urlpatterns = [
    path("students/", students.student_list, name="student_list"),
    path("students/new/", students.student_edit, name="student_new"),
    path("students/<int:pk>/", students.student_detail, name="student_detail"),
    path("students/<int:pk>/edit/", students.student_edit, name="student_edit"),
    path("students/<int:pk>/archive/", students.student_archive, name="student_archive"),
    path("students/<int:pk>/delete/", students.student_delete, name="student_delete"),
    path("students/<int:pk>/exams/new/", students.exam_create, name="exam_new"),
    path("students/<int:pk>/exams/<int:exam_pk>/delete/", students.exam_delete, name="exam_delete"),
    path("", views.home, name="home"),
    path("health/", views.health, name="health"),
    path("login/", auth.LoginView.as_view(), name="login"),
    path("logout/", auth.LogoutView.as_view(), name="logout"),
]
