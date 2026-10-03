from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

SCORES = [MinValueValidator(0), MaxValueValidator(100)]
class Student(models.Model):
    name = models.CharField("学生姓名", max_length=50)
    grade = models.CharField("当前年级", max_length=10, choices=[(x,x) for x in ["高一","高二","高三","其他"]])
    curriculum = models.CharField("教材", max_length=30, blank=True)
    chapter = models.CharField("章节", max_length=100, blank=True)
    content = models.TextField("主要内容", blank=True, max_length=2000)
    usual_raw = models.DecimalField("平时裸分", max_digits=5, decimal_places=2, null=True, blank=True, validators=SCORES)
    usual_scaled = models.DecimalField("平时赋分", max_digits=5, decimal_places=2, null=True, blank=True, validators=SCORES)
    target_score = models.DecimalField("目标分（赋分）", max_digits=5, decimal_places=2, null=True, blank=True, validators=SCORES)
    school = models.CharField("期望学校", max_length=100, blank=True)
    archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["archived", "name", "pk"]
    def __str__(self):
        return self.name
    @property
    def latest_exam(self):
        return self.exams.order_by("-date", "-created_at", "-pk").first()

class ExamRecord(models.Model):
    student = models.ForeignKey(Student, related_name="exams", on_delete=models.CASCADE)
    date = models.DateField("考试日期")
    raw_score = models.DecimalField("裸分", max_digits=5, decimal_places=2, null=True, blank=True, validators=SCORES)
    scaled_score = models.DecimalField("赋分", max_digits=5, decimal_places=2, null=True, blank=True, validators=SCORES)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-date", "-created_at", "-pk"]

class CourseSeries(models.Model):
    token = models.CharField(max_length=64, unique=True)
    rule = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

class Lesson(models.Model):
    student = models.ForeignKey(Student, related_name="lessons", on_delete=models.CASCADE)
    date = models.DateField("课程日期")
    start_time = models.TimeField("开始时间")
    end_time = models.TimeField("结束时间")
    series = models.ForeignKey(CourseSeries, related_name="lessons", null=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=12, default="scheduled", choices=[("scheduled","待上课"),("completed","已完成"),("cancelled","已取消")])
    next_goal = models.TextField("下次课目标（内部备课）", blank=True, max_length=2000)
    progress_snapshot = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=0)
    class Meta:
        ordering = ["date", "start_time", "pk"]
        indexes = [models.Index(fields=["date", "status"])]
        constraints = [models.CheckConstraint(condition=models.Q(end_time__gt=models.F("start_time")), name="lesson_positive_duration")]
