"""Preview and atomically import image-derived students and two-hour lessons."""
import hashlib
import json
from datetime import datetime, timedelta
from uuid import uuid4

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.cache import cache
from django.db import OperationalError, transaction
from django.forms import formset_factory
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .ai import AIError
from .feedback import preferences
from .models import CourseSeries, Lesson, Student
from .schedule_vision import MAX_ROWS, normalize_name, read_image, recognize_schedule
from .scheduling import find_conflicts


class UploadForm(forms.Form):
    image = forms.FileField(label="课表图片", widget=forms.ClearableFileInput(attrs={"accept": "image/png,image/jpeg,image/webp"}), help_text="JPG、PNG 或 WebP，最大 6 MB。图片需包含日期列和左侧时间。")


class StudentSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if hasattr(value, "instance"):
            option["attrs"]["data-name"] = value.instance.name
        return option


class StudentChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, student):
        return f"{student.name} · {student.grade} · #{student.pk}"


class ImportRowForm(forms.Form):
    include = forms.BooleanField(label="导入这节课", required=False, initial=True)
    name = forms.CharField(label="学生姓名", max_length=50, required=False)
    grade = forms.ChoiceField(label="年级", required=False, choices=[(x, x) for x in ("其他", "高一", "高二", "高三")])
    student = StudentChoiceField(label="对应档案", required=False, queryset=Student.objects.filter(archived=False), empty_label="按姓名匹配 / 新增", widget=StudentSelect)
    date = forms.DateField(label="日期", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    start_time = forms.TimeField(label="开始时间", required=False, widget=forms.TimeInput(attrs={"type": "time", "step": "60"}, format="%H:%M"))

    def __init__(self, *args, year=None, **kwargs):
        self.year = year
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        if not data.get("include"):
            self._errors.clear()
            return data
        for key in ("name", "date", "start_time"):
            if not data.get(key) and key not in self.errors:
                self.add_error(key, "请填写此项，或取消勾选这节课。")
        if data.get("name"):
            data["name"] = normalize_name(data["name"])
        data["grade"] = data.get("grade") or "其他"
        if data.get("date") and data["date"].year != self.year:
            self.add_error("date", f"请使用 {self.year} 年的课程日期。")
        if data.get("start_time"):
            start = datetime.combine(timezone.localdate(), data["start_time"])
            if data["start_time"].second or data["start_time"].microsecond or (start + timedelta(hours=2)).date() != start.date():
                self.add_error("start_time", "每节课为 2 小时，开始时间需精确到分钟，且不能跨日。")
        return data


RowsFormSet = formset_factory(ImportRowForm, extra=0, max_num=MAX_ROWS, absolute_max=MAX_ROWS, validate_max=True, min_num=1, validate_min=True)


class ImportProblem(Exception):
    def __init__(self, text, index=0, field="student"):
        self.text, self.index, self.field = text, index, field


class ChangedPlan(Exception):
    def __init__(self, plan):
        self.plan = plan


def signed(payload, stage):
    return signing.dumps(payload, salt="image-import:" + stage, compress=True)


def load_token(token, stage, user):
    payload = signing.loads(token, salt="image-import:" + stage, max_age=900)
    if payload["user"] != user.pk or not isinstance(payload["rows"], list) or not 1 <= len(payload["rows"]) <= MAX_ROWS:
        raise signing.BadSignature
    return payload


def matching_initial(rows):
    students = list(Student.objects.filter(archived=False))
    result = []
    for row in rows:
        candidates = [student for student in students if normalize_name(student.name) == row["name"]]
        result.append({**row, "student": candidates[0].pk if len(candidates) == 1 else ""})
    return result


def serialize_forms(formset):
    rows = []
    for form in formset:
        data = form.cleaned_data
        if not data.get("include"):
            continue
        rows.append({"name": data["name"], "grade": data["grade"], "student": data["student"].pk if data.get("student") else "", "date": data["date"].isoformat(), "start_time": data["start_time"].strftime("%H:%M"), "include": True})
    return rows


def bound_rows(payload):
    rows = payload["rows"]
    data = {"rows-TOTAL_FORMS": len(rows), "rows-INITIAL_FORMS": len(rows), "rows-MIN_NUM_FORMS": 1, "rows-MAX_NUM_FORMS": MAX_ROWS}
    for index, row in enumerate(rows):
        for key in ("name", "grade", "student", "date", "start_time"):
            data[f"rows-{index}-{key}"] = row.get(key, "")
        data[f"rows-{index}-include"] = "on"
    return RowsFormSet(data, prefix="rows", form_kwargs={"year": payload["year"]})


def build_plan(rows):
    students = list(Student.objects.all())
    by_id = {student.pk: student for student in students}
    plan_rows, seen, new_grades = [], set(), {}
    for index, row in enumerate(rows):
        name = normalize_name(row["name"])
        selected = row.get("student")
        student = by_id.get(int(selected)) if selected else None
        if selected and (not student or student.archived):
            raise ImportProblem("所选学生不存在或已归档，请重新选择。", index)
        if student and normalize_name(student.name) != name:
            raise ImportProblem("姓名与所选档案不同，请核对姓名或改为按姓名匹配。", index)
        if not selected:
            matches = [item for item in students if normalize_name(item.name) == name]
            active = [item for item in matches if not item.archived]
            if len(active) > 1:
                raise ImportProblem("存在同名学生，请在对应档案中明确选择。", index)
            if active:
                student = active[0]
            elif matches:
                raise ImportProblem("同名学生已归档，请先恢复该档案再导入。", index)
        grade = student.grade if student else row["grade"]
        if not student:
            previous = new_grades.get(name, "其他")
            if previous != "其他" and grade != "其他" and previous != grade:
                raise ImportProblem("同一位新学生的年级不一致，请核对后导入。", index, "grade")
            new_grades[name] = grade if grade != "其他" else previous
        day = datetime.strptime(row["date"], "%Y-%m-%d").date()
        start = datetime.strptime(row["start_time"], "%H:%M")
        end = (start + timedelta(hours=2)).time()
        key = (student.pk if student else name, row["date"], row["start_time"])
        duplicate = key in seen or bool(student and Lesson.objects.filter(student=student, date=day, start_time=start.time(), end_time=end).exclude(status="cancelled").exists())
        seen.add(key)
        conflicts = []
        if not duplicate:
            for lesson in find_conflicts(day, start.time(), end):
                conflicts.append({"id": lesson.pk, "version": lesson.version, "name": lesson.student.name, "date": lesson.date.isoformat(), "start": lesson.start_time.strftime("%H:%M"), "end": lesson.end_time.strftime("%H:%M")})
        plan_rows.append({"name": student.name if student else name, "grade": grade, "student_id": student.pk if student else None, "date": row["date"], "start": row["start_time"], "end": end.strftime("%H:%M"), "duplicate": duplicate, "conflicts": conflicts})
    additions = [row for row in plan_rows if not row["duplicate"]]
    for i, row in enumerate(plan_rows):
        if row["duplicate"]:
            continue
        if not row["student_id"]:
            row["grade"] = new_grades[row["name"]]
        for j, other in enumerate(plan_rows):
            if i != j and not other["duplicate"] and row["date"] == other["date"] and row["start"] < other["end"] and row["end"] > other["start"]:
                row["conflicts"].append({"id": f"import-{j}", "name": other["name"], "date": other["date"], "start": other["start"], "end": other["end"]})
    fingerprint = hashlib.sha256(json.dumps(plan_rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {"rows": plan_rows, "lesson_count": len(additions), "duplicate_count": len(plan_rows) - len(additions), "student_count": len({row["name"] for row in additions if not row["student_id"]}), "has_conflicts": any(row["conflicts"] for row in additions), "fingerprint": fingerprint}


def apply_import(payload, accept):
    with transaction.atomic():
        series, created = CourseSeries.objects.get_or_create(token=payload["nonce"], defaults={"rule": {"source": "image"}})
        if not created:
            return series.rule, True
        plan = build_plan(payload["rows"])
        if plan["fingerprint"] != payload["fingerprint"]:
            raise ChangedPlan(plan)
        if plan["has_conflicts"] and not accept:
            raise ChangedPlan(plan)
        new_students, lessons = {}, []
        for row in plan["rows"]:
            if row["duplicate"]:
                continue
            student_id = row["student_id"]
            if student_id is None:
                if row["name"] not in new_students:
                    new_students[row["name"]] = Student.objects.create(name=row["name"], grade=row["grade"])
                student_id = new_students[row["name"]].pk
            # The series is an import receipt only; pictured lessons are independent bookings.
            lessons.append(Lesson(student_id=student_id, date=row["date"], start_time=row["start"], end_time=row["end"]))
        Lesson.objects.bulk_create(lessons)
        summary = {"source": "image", "lesson_count": len(lessons), "student_count": len(new_students), "duplicate_count": plan["duplicate_count"], "first_date": min(row["date"] for row in plan["rows"])}
        series.rule = summary
        series.save(update_fields=["rule"])
        return summary, False


@login_required
@require_http_methods(["GET", "POST"])
def import_schedule(request):
    year = timezone.localdate().year
    upload = UploadForm(request.POST if request.method == "POST" else None, request.FILES or None)
    image_key = f"image-preview:{request.user.pk}"

    def cached_image(payload):
        cached = cache.get(image_key)
        return cached["image_url"] if cached and cached["nonce"] == payload["nonce"] else None

    def editable(payload, formset=None, image_url=None, status=200):
        image_url = image_url or cached_image(payload)
        if formset is None:
            formset = RowsFormSet(initial=payload["rows"], prefix="rows", form_kwargs={"year": payload["year"]})
        return render(request, "schedule/import_edit.html", {"formset": formset, "draft_token": signed(payload, "draft"), "year": payload["year"], "warnings": payload.get("warnings", []), "image_url": image_url}, status=status)

    def confirmation(payload, plan, changed=False):
        payload = {**payload, "fingerprint": plan["fingerprint"]}
        return render(request, "schedule/import_confirm.html", {"plan": plan, "confirm_token": signed(payload, "confirm"), "year": payload["year"], "changed": changed})

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "recognize":
            upload = UploadForm(request.POST, request.FILES)
            if upload.is_valid():
                lock = f"image-import:{request.user.pk}"
                if not cache.add(lock, True, timeout=40):
                    upload.add_error(None, "正在识别图片，请等待本次完成。")
                else:
                    try:
                        image_url = read_image(upload.cleaned_data["image"])
                        rows, notes = recognize_schedule(image_url, year, preferences().vision_model)
                        if not rows:
                            upload.add_error(None, "没有识别到可导入课程，请选择包含学生姓名、日期和时间的清晰课表。")
                        else:
                            payload = {"user": request.user.pk, "nonce": uuid4().hex, "year": year, "rows": matching_initial(rows), "warnings": notes}
                            # Keep only the latest image per teacher, for the lifetime of the draft.
                            cache.set(image_key, {"nonce": payload["nonce"], "image_url": image_url}, timeout=900)
                            return editable(payload, image_url=image_url)
                    except AIError as exc:
                        upload.add_error(None, str(exc))
                    finally:
                        cache.delete(lock)
        elif action in ("preview", "confirm", "edit"):
            try:
                stage = "draft" if action == "preview" else "confirm"
                payload = load_token(request.POST.get(stage + "_token", ""), stage, request.user)
                if action == "edit":
                    return editable(payload)
                if action == "preview":
                    formset = RowsFormSet(request.POST, prefix="rows", form_kwargs={"year": payload["year"]})
                    if not formset.is_valid():
                        return editable(payload, formset)
                    rows = serialize_forms(formset)
                    if not rows:
                        formset.forms[0].add_error("include", "请至少勾选一节课程。")
                        return editable(payload, formset)
                    try:
                        plan = build_plan(rows)
                    except ImportProblem as exc:
                        # The plan indexes selected rows; map back to the visible form.
                        selected = [form for form in formset if form.cleaned_data.get("include")]
                        selected[exc.index].add_error(exc.field, exc.text)
                        return editable(payload, formset)
                    return confirmation({**payload, "rows": rows}, plan)
                try:
                    summary, repeated = apply_import(payload, request.POST.get("accept_conflicts") == "on")
                except ChangedPlan as exc:
                    return confirmation(payload, exc.plan, changed=exc.plan["fingerprint"] != payload["fingerprint"])
                except ImportProblem as exc:
                    formset = bound_rows(payload)
                    formset.forms[exc.index].add_error(exc.field, exc.text)
                    return editable(payload, formset, status=409)
                except OperationalError:
                    return render(request, "schedule/import_error.html", {"confirm_token": request.POST["confirm_token"]}, status=409)
                if repeated:
                    messages.info(request, "本次图片导入已完成，没有重复新增。")
                else:
                    messages.success(request, f"已导入 {summary['lesson_count']} 节课程，新增 {summary['student_count']} 位学生，跳过 {summary['duplicate_count']} 节已有课程。")
                if cached_image(payload):
                    cache.delete(image_key)
                return redirect(reverse("home") + "?week=" + summary["first_date"])
            except (signing.BadSignature, KeyError, TypeError, ValueError):
                upload.add_error(None, "导入预览已过期或无效，请重新选择图片识别。")
                return render(request, "schedule/import_upload.html", {"form": upload, "year": year, "configured": bool(settings.BAILIAN_API_KEY)}, status=400)
        else:
            upload.add_error(None, "请选择图片识别，或使用有效的预览确认导入。")
    return render(request, "schedule/import_upload.html", {"form": upload, "year": year, "configured": bool(settings.BAILIAN_API_KEY)})
