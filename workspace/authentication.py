import hashlib
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django import forms

class GuardedAuthenticationForm(AuthenticationForm):
    def clean(self):
        identity=(self.request.META.get("REMOTE_ADDR", "")+":"+self.cleaned_data.get("username", "")).encode()
        key="login-failures:"+hashlib.sha256(identity).hexdigest()
        failures=cache.get(key,0)
        if failures>=5:
            raise forms.ValidationError("登录尝试次数过多，请 5 分钟后再试。")
        try:
            result=super().clean()
        except forms.ValidationError:
            cache.set(key,failures+1,timeout=300)
            raise
        cache.delete(key)
        return result

class TeacherLoginView(LoginView):
    authentication_form=GuardedAuthenticationForm
