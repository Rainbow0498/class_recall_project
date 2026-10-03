from datetime import date, timedelta, time
from uuid import uuid4
from urllib.parse import urlencode
from django.urls import reverse
from types import SimpleNamespace
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import transaction
from django.db.models import F
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .forms import ScheduleForm, LessonEditForm
from .models import Student, Lesson, CourseSeries


class StaleSchedule(Exception):
    pass


def find_conflicts(day, start, end, exclude_ids=()):
    return Lesson.objects.filter(date=day, start_time__lt=end, end_time__gt=start).exclude(status="cancelled").exclude(pk__in=exclude_ids).select_related("student")


def preview_occurrences(cleaned):
    day, end = cleaned["start_date"], cleaned["end_date"]
    weekdays = {int(x) for x in cleaned.get("weekdays", [])}
    result=[]
    while day <= end:
        if not weekdays or day.weekday() in weekdays:
            result.append({"date":day, "start_time":cleaned["start_time"], "end_time":cleaned["end_time"], "conflicts":list(find_conflicts(day, cleaned["start_time"], cleaned["end_time"]))})
        day += timedelta(days=1)
    return result


def minute(value):
    return value.hour*60 + value.minute


def layout_day(lessons, start_hour=8):
    # Partition connected overlap groups; interval coloring keeps each course clickable.
    groups=[]
    for lesson in sorted(lessons, key=lambda x:(x.start_time,x.end_time,x.pk)):
        if not groups or minute(lesson.start_time) >= groups[-1]["end"]:
            groups.append({"end":minute(lesson.end_time), "items":[]})
        group=groups[-1]
        group["end"]=max(group["end"],minute(lesson.end_time))
        group["items"].append(lesson)
    result=[]
    for group in groups:
        ends=[]; positioned=[]
        for lesson in group["items"]:
            col=next((i for i,end in enumerate(ends) if end<=minute(lesson.start_time)),len(ends))
            if col==len(ends): ends.append(0)
            ends[col]=minute(lesson.end_time)
            positioned.append((lesson,col))
        for lesson,col in positioned:
            result.append({"lesson":lesson,"left":round(col*100/len(ends),4),"width":round(100/len(ends),4),"top":round((minute(lesson.start_time)-start_hour*60)*88/60,2),"height":max(22,round((minute(lesson.end_time)-minute(lesson.start_time))*88/60,2))})
    return result


@login_required
def calendar(request):
    try: anchor=date.fromisoformat(request.GET.get("week", ""))
    except ValueError: anchor=timezone.localdate()
    start=anchor-timedelta(days=anchor.weekday())
    # Keep navigation arithmetic inside the supported date range.
    if start.year < 1900 or start.year > 2100: start=timezone.localdate()-timedelta(days=timezone.localdate().weekday())
    student_id=request.GET.get("student", "")
    lessons=Lesson.objects.filter(date__gte=start,date__lt=start+timedelta(days=7)).exclude(status="cancelled").select_related("student")
    if student_id.isdigit(): lessons=lessons.filter(student_id=student_id)
    rows=list(lessons)
    start_hour=min([8]+[x.start_time.hour for x in rows])
    end_hour=min(24,max([22]+[x.end_time.hour+(1 if x.end_time.minute else 0) for x in rows]))
    try: selected_day=date.fromisoformat(request.GET.get("day", ""))
    except ValueError: selected_day=timezone.localdate()
    if not start <= selected_day < start+timedelta(days=7): selected_day=start
    days=[]
    for i in range(7):
        day=start+timedelta(days=i)
        entries=[x for x in rows if x.date==day]
        slots=[]
        for value in range(start_hour*60,end_hour*60,30):
            start_time=f"{value//60:02d}:{value%60:02d}"
            end_value=min(value+120,1439)
            end_time=f"{end_value//60:02d}:{end_value%60:02d}"
            query={"date":day.isoformat(),"start":start_time,"end":end_time}
            if student_id.isdigit(): query["student"]=student_id
            slots.append({"start":start_time,"end":end_time,"url":reverse("lesson_new")+"?"+urlencode(query)})
        days.append({"date":day,"label":"周"+"一二三四五六日"[i],"today":day==timezone.localdate(),"active":day==selected_day,"lessons":entries,"layout":layout_day(entries,start_hour),"slots":slots})
    return render(request,"schedule/calendar.html",{"days":days,"week":start,"selected_day":selected_day,"prev":start-timedelta(days=7),"next":start+timedelta(days=7),"students":Student.objects.all(),"active_students":Student.objects.filter(archived=False),"selected_student":student_id,"lesson_count":len(rows),"hours":range(start_hour,end_hour+1),"grid_height":(end_hour-start_hour)*88,"cancelled":Lesson.objects.filter(date__gte=start,date__lt=start+timedelta(days=7),status="cancelled").filter(**({"student_id":student_id} if student_id.isdigit() else {})).select_related("student")})


def slot_initial(request):
    try: day=date.fromisoformat(request.GET.get("date", ""))
    except ValueError: day=timezone.localdate()
    initial={"start_date":day,"student":request.GET.get("student"),"start_time":"17:30","end_time":"19:30"}
    try:
        start=time.fromisoformat(request.GET.get("start", ""))
        end=time.fromisoformat(request.GET.get("end", ""))
        if start.tzinfo is None and end.tzinfo is None and not start.second and not end.second and not start.microsecond and not end.microsecond and end>start:
            initial.update(start_time=start.strftime("%H:%M"),end_time=end.strftime("%H:%M"))
    except ValueError:
        pass
    return initial



@login_required
def lesson_create(request):
    initial=slot_initial(request)
    raw=request.POST or None
    token=request.POST.get("preview_token", "")
    nonce=uuid4().hex
    if token:
        try:
            payload=signing.loads(token,salt="schedule",max_age=900)
            raw=payload["data"];nonce=payload["nonce"]
        except (signing.BadSignature,KeyError):
            return HttpResponseBadRequest("排课预览已过期，请重新预览。")
    form=ScheduleForm(raw,initial=initial)
    if request.method=="POST" and form.is_valid():
        occurrences=preview_occurrences(form.cleaned_data)
        if not occurrences:
            form.add_error("weekdays","所选日期范围内没有对应的上课日。")
        else:
            has_conflicts=any(x["conflicts"] for x in occurrences)
            if token and request.POST.get("confirm")=="on" and (not has_conflicts or request.POST.get("accept_conflicts")=="on"):
                with transaction.atomic():
                    series,created=CourseSeries.objects.get_or_create(token=nonce,defaults={"rule":raw})
                    if created:
                        Lesson.objects.bulk_create([Lesson(student=form.cleaned_data["student"],date=x["date"],start_time=x["start_time"],end_time=x["end_time"],series=series,next_goal=form.cleaned_data["next_goal"]) for x in occurrences])
                messages.success(request,f"已添加 {len(occurrences)} 节课程。")
                return redirect("home")
            serial={key:(raw.getlist(key) if key=="weekdays" and hasattr(raw,"getlist") else raw.get(key, [] if key=="weekdays" else "")) for key in form.fields}
            preview_token=signing.dumps({"data":serial,"nonce":nonce},salt="schedule")
            return render(request,"schedule/preview.html",{"form":form,"occurrences":occurrences,"preview_token":preview_token,"has_conflicts":has_conflicts,"student":form.cleaned_data["student"]})
    return render(request,"schedule/form.html",{"form":form})


def scoped_lessons(lesson,scope):
    if scope=="future" and lesson.series_id:
        return list(Lesson.objects.filter(series=lesson.series,date__gte=lesson.date).exclude(status="completed"))
    return [lesson] if lesson.status!="completed" else []


@login_required
def lesson_detail(request,pk):
    lesson=get_object_or_404(Lesson.objects.select_related("student"),pk=pk)
    return render(request,"schedule/detail.html",{"lesson":lesson})


@login_required
def lesson_edit(request,pk):
    lesson=get_object_or_404(Lesson.objects.select_related("student"),pk=pk)
    if lesson.status=="completed":
        messages.error(request,"已完成课程保留原排课记录，请在课程详情编辑反馈。")
        return redirect("lesson_detail",pk=pk)
    form=LessonEditForm(request.POST or None,initial={"date":lesson.date,"start_time":lesson.start_time,"end_time":lesson.end_time,"next_goal":lesson.next_goal,"scope":"once"})
    if request.method=="POST" and form.is_valid():
        targets=scoped_lessons(lesson,form.cleaned_data["scope"])
        delta=form.cleaned_data["date"]-lesson.date
        occurrences=[];ids=[x.pk for x in targets]
        for item in targets:
            new_date=item.date+delta
            occurrences.append({"date":new_date,"start_time":form.cleaned_data["start_time"],"end_time":form.cleaned_data["end_time"],"conflicts":list(find_conflicts(new_date,form.cleaned_data["start_time"],form.cleaned_data["end_time"],ids)) if item.status!="cancelled" else []})
        for i,row in enumerate(occurrences):
            if targets[i].status == "cancelled": continue
            for j,other in enumerate(occurrences):
                if i==j or targets[j].status=="cancelled": continue
                if row["date"]==other["date"] and row["start_time"]<other["end_time"] and row["end_time"]>other["start_time"]:
                    row["conflicts"].append(SimpleNamespace(student=targets[j].student,start_time=other["start_time"],end_time=other["end_time"]))
        has_conflicts=any(x["conflicts"] for x in occurrences)
        if request.POST.get("confirm")=="on" and (not has_conflicts or request.POST.get("accept_conflicts")=="on"):
            try:
                with transaction.atomic():
                    for item,occurrence in zip(targets,occurrences):
                        changed=Lesson.objects.filter(pk=item.pk,version=item.version,status=item.status).exclude(status="completed").update(date=occurrence["date"],start_time=occurrence["start_time"],end_time=occurrence["end_time"],next_goal=form.cleaned_data["next_goal"],version=F("version")+1)
                        if changed!=1: raise StaleSchedule
            except StaleSchedule:
                form.add_error(None,"课程已在其他页面更新，本次批量调整未保存。请重新打开课程并预览。")
                return render(request,"schedule/edit.html",{"lesson":lesson,"form":form,"occurrences":occurrences,"has_conflicts":has_conflicts},status=409)
            messages.success(request,f"已调整 {len(targets)} 节尚未完成的课程。")
            return redirect("lesson_detail",pk=pk)
        return render(request,"schedule/edit.html",{"lesson":lesson,"form":form,"occurrences":occurrences,"has_conflicts":has_conflicts})
    return render(request,"schedule/edit.html",{"lesson":lesson,"form":form})


@login_required
def lesson_cancel(request,pk):
    lesson=get_object_or_404(Lesson.objects.select_related("student"),pk=pk)
    scope=request.POST.get("scope","once")
    token=request.POST.get("preview_token", "")
    payload=None
    if token:
        try:
            payload=signing.loads(token,salt="cancel",max_age=900)
            if payload["lesson_id"]!=pk: raise signing.BadSignature
            scope=payload["scope"]
        except (signing.BadSignature,KeyError):
            return HttpResponseBadRequest("取消预览已过期，请重新预览。")
    targets=[item for item in scoped_lessons(lesson,scope) if item.status=="scheduled"]
    signature=[{"id":item.pk,"version":item.version,"status":item.status} for item in targets]
    error="";status=200
    if request.method=="POST" and token and request.POST.get("confirm")=="on":
        try:
            if signature != payload["targets"]: raise StaleSchedule
            with transaction.atomic():
                for item in targets:
                    changed=Lesson.objects.filter(pk=item.pk,version=item.version,status="scheduled").update(status="cancelled",version=F("version")+1)
                    if changed!=1: raise StaleSchedule
            messages.success(request,f"已取消 {len(targets)} 节尚未完成的课程。")
            return redirect("home")
        except StaleSchedule:
            error="课程状态或范围已变化，本次取消未保存。请核对下方最新范围，必要时重新打开课程。"
            status=409
    context={"lesson":lesson,"scope":scope,"error":error}
    if request.method=="POST":
        context.update(targets=targets,preview_token=signing.dumps({"lesson_id":pk,"scope":scope,"targets":signature},salt="cancel"))
    return render(request,"schedule/cancel.html",context,status=status)


@login_required
def lesson_restore(request,pk):
    lesson=get_object_or_404(Lesson.objects.select_related("student"),pk=pk,status="cancelled")
    conflicts=list(find_conflicts(lesson.date,lesson.start_time,lesson.end_time,[pk]))
    if request.method=="POST" and request.POST.get("confirm")=="on" and (not conflicts or request.POST.get("accept_conflicts")=="on"):
        changed=Lesson.objects.filter(pk=pk,status="cancelled",version=lesson.version).update(status="scheduled",version=F("version")+1)
        if changed!=1:
            return HttpResponseBadRequest("课程状态已变化，请重新打开课程。")
        messages.success(request,"课程已恢复。")
        return redirect("home")
    return render(request,"schedule/restore.html",{"lesson":lesson,"conflicts":conflicts})
