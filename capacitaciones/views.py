from django.db import transaction
import pandas as pd
from django.shortcuts import render, redirect
from .models import CharlaMaestra, Empleado, ProgresoCharla, RegistroCarga
from .forms import UploadExcelForm
from django.contrib import messages
from django.db.models import Count, Q
from django.contrib.auth.decorators import login_required
import io
import json
import matplotlib
matplotlib.use('Agg')  # Para generar imágenes sin interfaz gráfica
import matplotlib.pyplot as plt
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import HttpResponse, FileResponse
from django.utils import timezone
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

from .models import Empleado, ProgresoCharla
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from .forms import RegistrarAdminForm
from .models import PerfilAdmin

class DashboardGSIView(LoginRequiredMixin, View):
    template_name = 'capacitaciones/dashboard.html'

    def get_filtros(self, request):
        """Extrae y aplica los filtros base al QuerySet de Empleados"""
        query_intendencia = request.GET.get('intendencia')
        query_unidad = request.GET.get('unidad')
        
        empleados = Empleado.objects.all()
        
        if query_intendencia:
            empleados = empleados.filter(intendencia=query_intendencia)
        if query_unidad:
            empleados = empleados.filter(unidad_organica=query_unidad)
        
        return empleados, query_intendencia, query_unidad

    def get(self, request, *args, **kwargs):
        # 1. Si la URL pide exportar, llamar a la función de PDF
        if request.GET.get('export') == 'pdf':
            return self.generar_pdf(request)

        # 2. Obtener empleados filtrados y valores de búsqueda
        empleados, q_int, q_uni = self.get_filtros(request)
        total_poblacion = empleados.count()
        
        # --- LÓGICA DE FILTROS JERÁRQUICOS ---
        listado_intendencias = Empleado.objects.values_list('intendencia', flat=True).distinct().order_by('intendencia')
        
        # Si hay intendencia seleccionada, filtramos las unidades que le pertenecen
        if q_int:
            listado_unidades = Empleado.objects.filter(intendencia=q_int).values_list('unidad_organica', flat=True).distinct().order_by('unidad_organica')
        else:
            listado_unidades = []

        # --- ESTADÍSTICAS DINÁMICAS (Usando CharlaMaestra) ---
        stats_charlas = []
        charlas_configuradas = CharlaMaestra.objects.all().order_by('numero')

        for charla_m in charlas_configuradas:
            aprobados = ProgresoCharla.objects.filter(
                empleado__in=empleados, 
                charla_config=charla_m,
                resultado__iexact='Aprobado'
            ).count()
            
            stats_charlas.append({
                'n': charla_m.numero,
                'titulo': charla_m.titulo,
                'aprobados': aprobados,
                'pendientes': total_poblacion - aprobados
            })

        context = {
            'total_empleados': total_poblacion,
            'listado_intendencias': listado_intendencias,
            'listado_unidades': listado_unidades,
            'filtros': {'intendencia': q_int, 'unidad': q_uni},
            'stats_list': stats_charlas, # Para los cuadros del HTML
            'json_stats': json.dumps(stats_charlas) # Para Chart.js
        }
        return render(request, self.template_name, context)

    def generar_grafico_matplotlib(self, aprobados, pendientes, titulo):
        """Genera el gráfico circular en memoria"""
        plt.figure(figsize=(3, 3))
        total = aprobados + pendientes
        if total == 0:
            plt.pie([1], colors=['#6c757d'])
            plt.text(0, 0, 'Sin datos', ha='center', va='center')
        else:
            plt.pie([aprobados, pendientes], labels=['Aprob.', 'Pend.'], 
                    colors=['#198754', '#dc3545'], autopct='%1.1f%%', startangle=140)
        plt.title(titulo, fontsize=10)
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', bbox_inches='tight')
        img_buffer.seek(0)
        plt.close()
        return img_buffer

    def generar_pdf(self, request):
        """Lógica de ReportLab con tablas y gráficos"""
        empleados, q_int, q_uni = self.get_filtros(request)
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph("INFORME ESTATÍSTICO SGSI", styles['Title']))
        elements.append(Paragraph(f"Filtro: {q_int or 'GENERAL'} | {q_uni or 'TODAS'}", styles['Normal']))
        elements.append(Spacer(1, 20))

        # Cuadrícula de gráficos
        celdas = []
        charlas_m = CharlaMaestra.objects.all().order_by('numero')
        total_p = empleados.count()

        for c in charlas_m:
            aprob = ProgresoCharla.objects.filter(empleado__in=empleados, charla_config=c, resultado__iexact='Aprobado').count()
            pend = total_p - aprob
            
            buf = self.generar_grafico_matplotlib(aprob, pend, f"Charla {c.numero}")
            img = Image(buf, width=150, height=150)
            celdas.append([img, Paragraph(f"<b>{c.titulo}</b><br/>Aprobados: {aprob}<br/>Pendientes: {pend}", styles['Normal'])])

        # Organizar de 2 en 2
        tabla_final = Table(celdas, colWidths=[250, 250])
        elements.append(tabla_final)
        
        doc.build(elements)
        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename="Reporte_SGSI.pdf")


from django.db import transaction
import pandas as pd
from .models import Empleado, ProgresoCharla, RegistroCarga, CharlaMaestra

from django.db import transaction
import pandas as pd
from .models import Empleado, ProgresoCharla, RegistroCarga, CharlaMaestra

@login_required
def importar_excel(request):
    if request.method == "POST":
        form = UploadExcelForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['archivo']
            try:
                with transaction.atomic():
                    # 1. Carga inicial
                    df_raw = pd.read_excel(file, header=None, dtype=str)

                    # 2. Localizar la fila de encabezados (COD REG.)
                    header_idx = None
                    for i, row in df_raw.iterrows():
                        val = str(row[0]).strip().upper() if row[0] is not None else ""
                        if val in ["COD REG.", "REG.", "COD REG", "REG"]:
                            header_idx = i
                            break
                    
                    if header_idx is None:
                        raise ValueError("No se encontró la cabecera 'REG.' o 'COD REG.'")

                    # 3. FILA DE TÍTULOS (Búsqueda inteligente hacia arriba)
                    titles_row = None
                    for k in range(1, 5): 
                        if header_idx - k < 0: break
                        candidate_row = df_raw.iloc[header_idx - k]
                        val_check = str(candidate_row[4]).strip().upper() if len(candidate_row) > 4 else ""
                        if "ASISTIO" in val_check or "RESULTADO" in val_check:
                            continue
                        titles_row = candidate_row
                        break
                    
                    if titles_row is None:
                        titles_row = df_raw.iloc[header_idx - 1]

                    # 4. DATOS
                    df_data = df_raw.iloc[header_idx + 1:].copy()
                    df_data = df_data.where(pd.notnull(df_data), None)

                    total_cols = len(df_raw.columns)
                    num_charlas = (total_cols - 4) // 3

                    # 5. LIMPIEZA Y CARGA DE EMPLEADOS
                    Empleado.objects.all().delete()
                    empleados_list = []
                    for row in df_data.values:
                        cod = str(row[0]).strip() if row[0] else None
                        if not cod: continue
                        empleados_list.append(Empleado(
                            cod_reg=cod,
                            nombre_completo=str(row[1])[:255] if row[1] else "SIN NOMBRE",
                            unidad_organica=str(row[2])[:255] if row[2] else "SIN UNIDAD",
                            intendencia=str(row[3])[:255] if row[3] else "SIN INTENDENCIA",
                        ))
                    creados = Empleado.objects.bulk_create(empleados_list, batch_size=1000)

                    # --- CORRECCIÓN AQUÍ ---
                    
                    # 6. SINCRONIZACIÓN DE TÍTULOS (CharlaMaestra)
                    
                    # A) PODA: Borrar charlas excedentes (Ej: Si antes habia 6 y ahora 4, borramos 5 y 6)
                    # Esto limpia el Dashboard y el Configurar Links inmediatamente.
                    CharlaMaestra.objects.filter(numero__gt=num_charlas).delete()

                    config_map = {}
                    col_ptr = 4
                    for i in range(1, num_charlas + 1):
                        raw_name = titles_row[col_ptr]
                        if not raw_name or pd.isna(raw_name):
                            for offset in [1, 2]:
                                if col_ptr + offset < total_cols:
                                    val = titles_row[col_ptr + offset]
                                    if val and not pd.isna(val):
                                        raw_name = val
                                        break
                        
                        titulo_final = str(raw_name).strip().replace('\n', ' ') if raw_name else f"Charla {i}"
                        if "ASISTIO" in titulo_final.upper(): titulo_final = f"Charla {i}"

                        # B) ACTUALIZAR: Mantenemos los links de las charlas que sí existen
                        obj, _ = CharlaMaestra.objects.get_or_create(
                            numero=i,
                            defaults={'titulo': titulo_final}
                        )
                        if obj.titulo != titulo_final:
                            obj.titulo = titulo_final
                            obj.save()
                        
                        config_map[i] = obj
                        col_ptr += 3

                    # 7. CARGA DE PROGRESO
                    progresos_list = []
                    for row_val, emp_obj in zip(df_data.values, creados):
                        ptr = 4
                        for i in range(1, num_charlas + 1):
                            asistio = str(row_val[ptr]).strip().upper() == "SI" if row_val[ptr] else False
                            resultado = str(row_val[ptr+1]).strip() if row_val[ptr+1] else ""
                            fecha = None
                            try:
                                if row_val[ptr+2]:
                                    fecha = pd.to_datetime(row_val[ptr+2], dayfirst=True).date()
                            except: pass

                            progresos_list.append(ProgresoCharla(
                                empleado=emp_obj,
                                charla_config=config_map[i],
                                asistio=asistio,
                                resultado=resultado,
                                fecha=fecha
                            ))
                            ptr += 3

                    ProgresoCharla.objects.bulk_create(progresos_list, batch_size=2000)
                    RegistroCarga.objects.create()
                    
                    messages.success(request, f"¡Sincronización completa! Se detectaron {num_charlas} charlas. Las charlas excedentes fueron eliminadas.")

                return redirect('importar_excel')
            except Exception as e:
                messages.error(request, f"Error: {str(e)}")
                return redirect('importar_excel')
    else:
        form = UploadExcelForm()
    return render(request, 'capacitaciones/upload.html', {'form': form})



def buscar_progreso(request):
    query = request.GET.get('q')
    empleado = None
    progreso_pct = 0
    
    if query:
        empleado = Empleado.objects.filter(cod_reg__iexact=query).first()
        if empleado:
            aprobadas = empleado.charlas.filter(resultado__iexact='Aprobado').count()
            progreso_pct = int((aprobadas / 6) * 100)
            
    return render(request, 'capacitaciones/buscar.html', {
        'empleado': empleado,
        'progreso_pct': progreso_pct,
        'query': query
    })

@login_required
def dashboard_admin(request):
    # 1. Obtener filtros de la URL
    q_intendencia = request.GET.get('intendencia')
    q_unidad = request.GET.get('unidad')

    # 2. Filtrar el QuerySet base
    empleados = Empleado.objects.all()
    if q_intendencia:
        empleados = empleados.filter(intendencia=q_intendencia)
    if q_unidad:
        empleados = empleados.filter(unidad_organica=q_unidad)

    total_empleados = empleados.count()

    # 3. Datos para los 6 gráficos de pasteles (Aprobados vs Pendientes por Charla)
    stats_charlas = []
    barras_labels = []
    barras_data = []

    for i in range(1, 7):
        aprobados = ProgresoCharla.objects.filter(
            empleado__in=empleados, 
            numero_charla=i, 
            resultado__iexact='Aprobado'
        ).count()
        
        pendientes = total_empleados - aprobados
        
        stats_charlas.append({
            'numero': i,
            'aprobados': aprobados,
            'pendientes': pendientes
        })
        # Datos para el gráfico de barras comparativo
        barras_labels.append(f"Charla {i}")
        barras_data.append(aprobados)

    # 4. Datos para filtros (Dropdowns)
    listado_intendencias = Empleado.objects.values_list('intendencia', flat=True).distinct()
    listado_unidades = Empleado.objects.values_list('unidad_organica', flat=True).distinct()

    context = {
        'stats_charlas': stats_charlas,
        'barras_labels': barras_labels,
        'barras_data': barras_data,
        'total_empleados': total_empleados,
        'listado_intendencias': listado_intendencias,
        'listado_unidades': listado_unidades,
        'filtros': {'intendencia': q_intendencia, 'unidad': q_unidad}
    }
    return render(request, 'capacitaciones/dashboard.html', context)

def registrar_admin(request):
    if request.method == "POST":
        form = RegistrarAdminForm(request.POST)
        if form.is_valid():
            # El form.save() de un UserCreationForm ya se encarga de:
            # 1. Encriptar la contraseña (Hashing)
            # 2. Aplicar los validadores de seguridad
            user = form.save() 
            
            PerfilAdmin.objects.create(
                user=user,
                num_reg=form.cleaned_data['num_reg'],
                dni=form.cleaned_data['dni']
            )
            messages.success(request, f"Admin {user.username} creado con éxito y contraseña encriptada.")
            return redirect('dashboard_admin')
        else:
            # Esto mostrará por qué la contraseña es "débil"
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    
    return render(request, 'capacitaciones/registrar_admin.html')

@login_required
def modulo_secreto(request):
    empleados_list = Empleado.objects.all().order_by('cod_reg')
    paginator = Paginator(empleados_list, 50) # 50 registros por página
    
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'capacitaciones/secreto.html', {'page_obj': page_obj})



@login_required
def gestionar_links(request):
    # Obtenemos todas las charlas configuradas actualmente
    charlas = CharlaMaestra.objects.all().order_by('numero')
    
    if request.method == "POST":
        for charla in charlas:
            # Capturamos los datos del formulario usando el ID de la charla
            nuevo_titulo = request.POST.get(f'titulo_{charla.id}')
            nuevo_video = request.POST.get(f'video_{charla.id}')
            nueva_eval = request.POST.get(f'eval_{charla.id}')
            
            # Actualizamos solo si se enviaron datos
            charla.titulo = nuevo_titulo
            charla.url_video = nuevo_video
            charla.url_evaluacion = nueva_eval
            charla.save()
            
        messages.success(request, "✅ Configuración de charlas actualizada correctamente.")
        return redirect('gestionar_links')
    
    return render(request, 'capacitaciones/gestionar_links.html', {'charlas': charlas})