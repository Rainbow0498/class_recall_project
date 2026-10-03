from datetime import time
from types import SimpleNamespace
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .ai import AIError, generate_feedback
from .forms import FeedbackForm, NotesForm, PreferencesForm
from .models import Student, Lesson, LessonFeedback, FeedbackSettings

class StaleEdit(Exception):
    pass


def preferences():
    return FeedbackSettings.objects.get_or_create(pk=1)[0]


@login_required
def lesson_detail(request,pk):
    lesson=get_object_or_404(Lesson.objects.select_related("student"),pk=pk)
    saved=LessonFeedback.objects.filter(lesson=lesson).first()
    progress=lesson.progress_snapshot or {key:getattr(lesson.student,key) for key in ("curriculum","chapter","content")}
    initial={"text":saved.text if saved else "", "version":lesson.version,"next_goal":lesson.next_goal,**progress}
    data=request.POST.copy() if request.method=="POST" else None
    if data is not None and data.get("save_mode")=="progress": data["update_progress"]="on"
    form=FeedbackForm(data,initial=initial)
    response_status=200
    if request.method=="POST" and form.is_valid():
        if lesson.status=="cancelled":
            form.add_error(None,"课程已取消，请先恢复课程再保存反馈。")
            response_status=409
        else:
            try:
                with transaction.atomic():
                    changes={"status":"completed","next_goal":form.cleaned_data["next_goal"],"version":F("version")+1}
                    if form.cleaned_data["update_progress"]:
                        snapshot={key:form.cleaned_data[key] for key in ("curriculum","chapter","content")}
                        changes["progress_snapshot"]=snapshot
                    elif not lesson.progress_snapshot:
                        changes["progress_snapshot"]=progress
                    if Lesson.objects.filter(pk=pk,version=form.cleaned_data["version"]).update(**changes)!=1:
                        raise StaleEdit
                    LessonFeedback.objects.update_or_create(lesson=lesson,defaults={"text":form.cleaned_data["text"]})
                    if form.cleaned_data["update_progress"]:
                        Student.objects.filter(pk=lesson.student_id).update(**snapshot)
                messages.success(request,"反馈已保存，当前教学进度已更新。" if form.cleaned_data["update_progress"] else "反馈已保存，当前教学进度保持原样。")
                return redirect("lesson_detail",pk=pk)
            except StaleEdit:
                form.add_error(None,"课程已在另一个页面更新。你的文本仍在下方，请复制后重新打开课程，核对最新内容再保存。")
                response_status=409
    return render(request,"feedback/detail.html",{"lesson":lesson,"form":form,"notes_form":NotesForm(),"saved":saved},status=response_status)


def run_generation(request,lesson,notes):
    lock=f"generation:{request.user.pk}:{lesson.pk}"
    if not cache.add(lock,True,timeout=40):
        return JsonResponse({"error":"正在生成，请等待本次完成。"},status=429)
    try:
        text=generate_feedback(lesson,notes,preferences())
        return JsonResponse({"text":text})
    except AIError as exc:
        return JsonResponse({"error":str(exc)},status=503)
    finally:
        cache.delete(lock)


@login_required
@require_POST
def generate(request,pk):
    lesson=get_object_or_404(Lesson.objects.select_related("student"),pk=pk)
    if lesson.status=="cancelled":
        return JsonResponse({"error":"请先恢复已取消的课程。"},status=409)
    form=NotesForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"error":"请填写本次内容、学生表现和课后作业，并检查输入长度。","fields":form.errors.get_json_data()},status=400)
    return run_generation(request,lesson,form.cleaned_data)


@login_required
def settings_page(request):
    config=preferences()
    form=PreferencesForm(request.POST or None,instance=config)
    if request.method=="POST" and form.is_valid():
        form.save();messages.success(request,"反馈设置已保存，仅用于之后生成，历史反馈保留原文。")
        return redirect("settings")
    return render(request,"settings.html",{"form":form,"configured":bool(settings.BAILIAN_API_KEY)})


@login_required
@require_POST
def test_generation(request):
    lesson=SimpleNamespace(pk="test",student=SimpleNamespace(name="示例学生"),date=timezone.localdate(),start_time=time(17,30),end_time=time(19,30))
    return run_generation(request,lesson,{"lesson_contents":"复习细胞结构","performance":"课堂练习5题做对4题，细胞膜的功能还需复习","homework":"完成配套练习第1至5题"})
