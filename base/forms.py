# core/forms.py
from django import forms

class UploadFileForm(forms.Form):
    file = forms.FileField()

class ProcessForm(forms.Form):
    session_id = forms.CharField()
    mapping = forms.CharField()  # JSON string