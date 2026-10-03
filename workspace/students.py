from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .forms import StudentForm, ExamForm
from .models import Student, ExamRecord

@login_required
def student_list(request):
    archived = request.GET.get("archived") == "1"
    rows = Student.objects.filter(archived=archived)
    query = request.GET.get("q", "").strip()
    grade = request.GET.get("grade", "")
    if query:
        rows = rows.filter(name__icontains=query)
    if grade:
        rows = rows.filter(grade=grade)
    return render(request, "students/list.html", {"students":rows, "archived":archived, "q":query, "grade":grade, "grades":["高一","高二","高三","其他"]})

@login_required
def student_edit(request, pk=None):
    student = get_object_or_404(Student, pk=pk) if pk else None
    form = StudentForm(request.POST or None, instance=student)
    if request.method == "POST" and form.is_valid():
        student = form.save()
        messages.success(request, "学生档案已保存。")
        return redirect("student_detail", pk=student.pk)
    return render(request, "students/form.html", {"form":form, "student":student})

@login_required
def student_detail(request, pk):
    student = get_object_or_404(Student, pk=pk)
    return render(request, "students/detail.html", {"student":student, "exam_form":ExamForm(), "exams":student.exams.all()})

@login_required
@require_POST
def student_archive(request, pk):
    student = get_object_or_404(Student, pk=pk)
    student.archived = not student.archived
    student.save(update_fields=["archived"])
    messages.success(request, "已归档，历史数据保留。" if student.archived else "学生已恢复为在读。")
    return redirect("student_detail", pk=pk)

@login_required
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == "POST" and request.POST.get("confirm") == "on":
        student.delete()
        messages.success(request, "学生及关联记录已删除。")
        return redirect("student_list")
    return render(request, "students/delete.html", {"student":student})

@login_required
def exam_create(request, pk):
    student = get_object_or_404(Student, pk=pk)
    form = ExamForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        exam = form.save(commit=False)
        exam.student = student
        exam.save()
        messages.success(request, "考试记录已保存。")
        return redirect("student_detail", pk=pk)
    return render(request, "students/exam.html", {"student":student, "form":form})

@login_required
@require_POST
def exam_delete(request, pk, exam_pk):
    get_object_or_404(ExamRecord, student_id=pk, pk=exam_pk).delete()
    messages.success(request, "考试记录已删除。")
    return redirect("student_detail", pk=pk)
