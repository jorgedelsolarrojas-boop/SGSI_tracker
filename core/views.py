from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.contrib import messages
from django.utils import timezone


class LockedLoginView(LoginView):
    """LoginView que limita intentos fallidos y aplica bloqueo temporal.

    - Cuenta 3 intentos fallidos (por usuario si se proporciona username, o por IP si no).
    - Al alcanzar el máximo establece un bloqueo temporal (por defecto 5 minutos).
    - Muestra códigos de error mediante el framework de messages:
        - AUTH_INVALID -> credenciales incorrectas
        - AUTH_LOCKED  -> cuenta bloqueada temporalmente
    """

    template_name = 'registration/login.html'
    max_attempts = 3
    lockout_seconds = 300  # 5 minutos

    def _username_from_request(self, request):
        return (request.POST.get('username') or '').strip().lower()

    def _ip_from_request(self, request):
        return request.META.get('REMOTE_ADDR', 'unknown')

    def _user_key(self, username):
        return f'login:uname:{username}'

    def _ip_key(self, ip):
        return f'login:ip:{ip}'

    def _locked_remaining_for_key(self, key):
        val = cache.get(key + ':lock')
        if not val:
            return 0
        # valor guardado: timestamp de expiración
        remaining = int(val - timezone.now().timestamp())
        return max(0, remaining)

    def dispatch(self, request, *args, **kwargs):
        username = self._username_from_request(request)
        ip = self._ip_from_request(request)

        # Revisar bloqueo por username (si existe) y por IP
        remaining = 0
        if username:
            remaining = self._locked_remaining_for_key(self._user_key(username))
        if remaining == 0:
            remaining = self._locked_remaining_for_key(self._ip_key(ip))

        if remaining > 0:
            minutes = (remaining + 59) // 60
            messages.error(request, f'Demasiados intentos. Intenta de nuevo en ~{minutes} minuto(s).')
            return self.render_to_response(self.get_context_data())

        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        request = self.request
        username = self._username_from_request(request)
        ip = self._ip_from_request(request)

        # Preferir llevar el conteo por username si está presente
        if username:
            key = self._user_key(username)
        else:
            key = self._ip_key(ip)

        attempts = cache.get(key, 0) + 1
        cache.set(key, attempts, self.lockout_seconds)

        if attempts >= self.max_attempts:
            expiry = timezone.now().timestamp() + self.lockout_seconds
            cache.set(key + ':lock', expiry, self.lockout_seconds)
            messages.error(request, f'Demasiados intentos. Cuenta bloqueada por {self.lockout_seconds // 60} minuto(s).')
        else:
            remaining = self.max_attempts - attempts
            messages.error(request, f'Usuario o contraseña incorrectos. Intentos restantes: {remaining}')

        return super().form_invalid(form)

    def form_valid(self, form):
        # Al iniciar sesión correctamente, limpiar contadores/bloqueos
        request = self.request
        username = self._username_from_request(request)
        ip = self._ip_from_request(request)

        if username:
            cache.delete(self._user_key(username))
            cache.delete(self._user_key(username) + ':lock')
        cache.delete(self._ip_key(ip))
        cache.delete(self._ip_key(ip) + ':lock')

        return super().form_valid(form)
