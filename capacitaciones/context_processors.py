from .models import RegistroCarga

def fecha_actualizacion(request):
    ultima = RegistroCarga.objects.all().order_by('-fecha_carga').first()
    return {'ultima_actualizacion': ultima.fecha_carga if ultima else "Sin registros"}
