from django import forms
from .models import Student, ExamRecord, FeedbackSettings

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

class NotesForm(forms.Form):
    lesson_contents = forms.CharField(label="本次上课内容", max_length=6000, widget=forms.Textarea(attrs={"rows":4,"placeholder":"例如：拉马克学说、达尔文学说"}))
    performance = forms.CharField(label="学生表现", max_length=6000, widget=forms.Textarea(attrs={"rows":5,"placeholder":"例如：12题对11题；适应的相对性还需要巩固"}))
    homework = forms.CharField(label="课后作业", max_length=3000, widget=forms.Textarea(attrs={"rows":3,"placeholder":"例如：我发的练习。没有作业时可填写“本次无作业”。"}))

class FeedbackForm(forms.Form):
    text = forms.CharField(label="最终反馈", max_length=20000, widget=forms.Textarea(attrs={"class":"feedback-text","rows":16}))
    version = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    curriculum = forms.CharField(label="教材", required=False, max_length=30)
    chapter = forms.CharField(label="章节", required=False, max_length=100)
    content = forms.CharField(label="主要内容", required=False, max_length=2000, widget=forms.Textarea(attrs={"rows":2}))
    next_goal = forms.CharField(label="下次课目标（仅内部备课，可留空）", required=False, max_length=2000, widget=forms.Textarea(attrs={"rows":2}))
    update_progress = forms.BooleanField(required=False)

class PreferencesForm(forms.ModelForm):
    model = forms.RegexField(label="模型名称", regex=r"^[a-zA-Z0-9._:/-]{1,100}$")
    vision_model = forms.RegexField(label="图片课表识别模型", regex=r"^[a-zA-Z0-9._:/-]{1,100}$", required=False, help_text="图片导入使用支持视觉识别的模型，默认 qwen3-vl-flash。")
    def clean_vision_model(self):
        return self.cleaned_data.get("vision_model") or self.instance.vision_model
    class Meta:
        model=FeedbackSettings
        fields=["body_template","instructions","model","vision_model"]
        widgets={"body_template":forms.Textarea(attrs={"rows":8}),"instructions":forms.Textarea(attrs={"rows":5})}
