from django.urls import path
from . import views

urlpatterns = [
    path('', views.buscar_progreso, name='buscar_progreso'),
    path('importar/', views.importar_excel, name='importar_excel'),
    path('dashboard/', views.DashboardGSIView.as_view(), name='dashboard_admin'),
    path('registrar_admin/', views.registrar_admin, name='registrar_admin'),
    path('maestro-full/', views.modulo_secreto, name='modulo_secreto'),
]
