# core/urls.py
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views # IMPORTANTE: No olvides esta línea
from .views import LockedLoginView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Login personalizado con bloqueo por intentos
    path('login/', LockedLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    path('', include('capacitaciones.urls')),
]
