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
