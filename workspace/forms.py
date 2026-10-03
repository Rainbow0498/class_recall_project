from django import forms
from .models import Student, ExamRecord

class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["name", "grade", "curriculum", "chapter", "content", "usual_raw", "usual_scaled", "target_score", "school"]
        widgets = {"content": forms.Textarea(attrs={"rows":3}), "curriculum": forms.TextInput(attrs={"placeholder":"例如：必修1"}), "chapter": forms.TextInput(attrs={"placeholder":"例如：第2章"})}

class ExamForm(forms.ModelForm):
    class Meta:
        model = ExamRecord
        fields = ["date", "raw_score", "scaled_score"]
        widgets = {"date": forms.DateInput(attrs={"type":"date"}, format="%Y-%m-%d")}
    def clean(self):
        cleaned = super().clean()
        if cleaned.get("raw_score") is None and cleaned.get("scaled_score") is None:
            raise forms.ValidationError("请至少填写裸分或赋分中的一项。")
        return cleaned

class ScheduleForm(forms.Form):
    student = forms.ModelChoiceField(label="学生", queryset=Student.objects.filter(archived=False))
    start_date = forms.DateField(label="首次课程日期", widget=forms.DateInput(attrs={"type":"date"}))
    end_date = forms.DateField(label="重复排课截止日期", required=False, widget=forms.DateInput(attrs={"type":"date"}), help_text="单次排课留空；批量排课最多一年。")
    weekdays = forms.MultipleChoiceField(label="每周上课日", required=False, choices=[(str(i),"周"+x) for i,x in enumerate("一二三四五六日")], widget=forms.CheckboxSelectMultiple)
    start_time = forms.TimeField(label="开始时间", widget=forms.TimeInput(attrs={"type":"time"}))
    end_time = forms.TimeField(label="结束时间", widget=forms.TimeInput(attrs={"type":"time"}))
    next_goal = forms.CharField(label="下次课目标（可选，仅内部备课）", required=False, max_length=2000, widget=forms.Textarea(attrs={"rows":2}))
    def clean(self):
        data = super().clean()
        start, end = data.get("start_date"), data.get("end_date") or data.get("start_date")
        data["end_date"] = end
        if start and end:
            if end < start or (end-start).days > 365:
                self.add_error("end_date", "截止日期必须在首次课程之后，日期范围最多一年。")
            elif start != end and not data.get("weekdays"):
                self.add_error("weekdays", "批量排课请选择每周上课日。")
        if data.get("start_time") and data.get("end_time") and data["end_time"] <= data["start_time"]:
            self.add_error("end_time", "结束时间必须晚于开始时间，课程不能跨日。")
        return data

class LessonEditForm(forms.Form):
    date = forms.DateField(label="课程日期", widget=forms.DateInput(attrs={"type":"date"}))
    start_time = forms.TimeField(label="开始时间", widget=forms.TimeInput(attrs={"type":"time"}))
    end_time = forms.TimeField(label="结束时间", widget=forms.TimeInput(attrs={"type":"time"}))
    next_goal = forms.CharField(label="内部备课目标", required=False, max_length=2000, widget=forms.Textarea(attrs={"rows":2}))
    scope = forms.ChoiceField(label="调整范围", choices=[("once","仅本次"),("future","本次及之后（已完成课程除外）")])
    def clean(self):
        data=super().clean()
        if data.get("start_time") and data.get("end_time") and data["end_time"] <= data["start_time"]:
            self.add_error("end_time", "结束时间必须晚于开始时间。")
        return data
