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
