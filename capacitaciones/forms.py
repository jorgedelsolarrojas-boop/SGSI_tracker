from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

class RegistrarAdminForm(UserCreationForm):
    first_name = forms.CharField(max_length=100, label="Nombres completos")
    last_name = forms.CharField(max_length=100, label="Apellidos")
    email = forms.EmailField(label="Correo electrónico institucional")
    dni = forms.CharField(max_length=8, min_length=8, label="DNI (8 dígitos)")
    num_reg = forms.CharField(max_length=20, label="Número de Registro")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('first_name', 'last_name', 'email')
class UploadExcelForm(forms.Form):
    archivo = forms.FileField(label="Selecciona el Maestro Excel")

    def clean_archivo(self):
        file = self.cleaned_data.get('archivo')
        if file:
            # Validar extensión
            if not file.name.endswith(('.xlsx', '.xls')):
                raise ValidationError("Solo se permiten archivos Excel (.xlsx o .xls)")
            # Validar tamaño (7MB = 7 * 1024 * 1024 bytes)
            if file.size > 7 * 1024 * 1024:
                raise ValidationError("El archivo es demasiado grande (Máximo 7MB)")
        return file
