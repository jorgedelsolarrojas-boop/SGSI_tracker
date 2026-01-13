from django.db import models
from django.contrib.auth.models import User

class Empleado(models.Model):
    cod_reg = models.CharField(max_length=4, unique=True,verbose_name="Código de Registro")
    nombre_completo = models.CharField(max_length=150)
    unidad_organica = models.CharField(max_length=150)
    intendencia = models.CharField(max_length=150)

    def __str__(self):
        return f"{self.cod_reg} {self.nombre_completo}"
    
class ProgresoCharla(models.Model):
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE,related_name='charlas')
    numero_charla = models.IntegerField()
    titulo_charla = models.CharField(max_length=150)
    asistio = models.BooleanField(default=False)
    resultado = models.CharField(max_length=50, blank=True, null=True)
    fecha = models.DateField(null=True, blank=True)

class Meta:
    unique_together = ('empleado', 'numero_charla')

class RegistroCarga (models.Model):
    fecha_carga = models.DateTimeField(auto_now_add=True)

class PerfilAdmin(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    num_reg = models.CharField(max_length=20, verbose_name="Núm. Registro")
    dni = models.CharField(max_length=8, verbose_name="DNI")

    def __str__(self):
        return f"Perfil de {self.user.username}"
