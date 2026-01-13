from django.db import transaction
import pandas as pd
from django.shortcuts import render, redirect
from .models import Empleado, ProgresoCharla, RegistroCarga
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
        
        # Si seleccionamos unidad, filtramos también (esto es para el resultado final)
        if query_unidad:
            empleados = empleados.filter(unidad_organica=query_unidad)
        
        return empleados, query_intendencia, query_unidad

    def get(self, request, *args, **kwargs):
        # 1. Lógica de Exportación PDF
        if request.GET.get('export') == 'pdf':
            return self.generar_pdf(request)

        # 2. Obtener datos filtrados
        empleados, q_int, q_uni = self.get_filtros(request)
        
        # --- LÓGICA JERÁRQUICA PARA DROPDOWNS ---
        # A. Las intendencias siempre se muestran todas para poder cambiar
        listado_intendencias = Empleado.objects.values_list('intendencia', flat=True).distinct().order_by('intendencia')
        
        # B. Las unidades dependen de si hay una intendencia seleccionada
        if q_int:
            # Si hay Intendencia, solo mostramos sus unidades hijas
            listado_unidades = Empleado.objects.filter(intendencia=q_int).values_list('unidad_organica', flat=True).distinct().order_by('unidad_organica')
        else:
            # Si no hay filtro, mostramos todas (o ninguna, según prefieras. Aquí dejo todas)
            listado_unidades = Empleado.objects.values_list('unidad_organica', flat=True).distinct().order_by('unidad_organica')

        # 3. Estadísticas
        stats_charlas = []
        total_emps = empleados.count()
        
        for i in range(1, 7):
            aprobados = ProgresoCharla.objects.filter(
                empleado__in=empleados, 
                numero_charla=i, 
                resultado__iexact='Aprobado'
            ).count()
            stats_charlas.append({
                'n': i,
                'aprobados': aprobados,
                'pendientes': total_emps - aprobados
            })

        context = {
            'total_empleados': total_emps,
            'listado_intendencias': listado_intendencias,
            'listado_unidades': listado_unidades,
            'filtros': {'intendencia': q_int, 'unidad': q_uni},
            'stats_list': stats_charlas,
            'json_stats': json.dumps(stats_charlas)
        }
        return render(request, self.template_name, context)

    def generar_grafico_matplotlib(self, aprobados, pendientes, titulo):
        plt.figure(figsize=(3, 3))
        try: a = float(aprobados)
        except: a = 0.0
        try: p = float(pendientes)
        except: p = 0.0
        total = a + p
        if total == 0 or total != total:
            plt.pie([1], colors=['#6c757d'])
            plt.text(0, 0, 'Sin datos', ha='center', va='center', fontsize=9)
        else:
            plt.pie([a, p], labels=['Aprob.', 'Pend.'], colors=['#28a745', '#dc3545'], autopct='%1.1f%%', startangle=140)
        plt.title(titulo, fontsize=10)
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', bbox_inches='tight')
        img_buffer.seek(0)
        plt.close()
        return img_buffer

    def generar_pdf(self, request):
        empleados, q_int, q_uni = self.get_filtros(request)
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        # 1. Cabecera Mejorada
        elements.append(Paragraph("INFORME DE CUMPLIMIENTO SGSI", styles['Title']))
        elements.append(Paragraph(f"Fecha de corte: {timezone.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
        elements.append(Paragraph(f"Filtros: {q_int or 'NIVEL NACIONAL'} | {q_uni or 'TODAS LAS UNIDADES'}", styles['Normal']))
        elements.append(Spacer(1, 20))

        # 2. Generación de Celdas (Gráfico + Tabla)
        celdas_graficos = [] # Lista plana que luego convertiremos en matriz
        
        total_poblacion = empleados.count()

        for i in range(1, 7):
            # Cálculos
            aprobados = ProgresoCharla.objects.filter(
                empleado__in=empleados, 
                numero_charla=i, 
                resultado__iexact='Aprobado'
            ).count()
            pendientes = total_poblacion - aprobados
            
            # Evitar división por cero
            pct_aprob = (aprobados / total_poblacion * 100) if total_poblacion > 0 else 0
            pct_pend = (pendientes / total_poblacion * 100) if total_poblacion > 0 else 0

            # A. Generar Imagen (Chart)
            buf = self.generar_grafico_matplotlib(aprobados, pendientes, f"Charla {i}")
            img_flowable = Image(buf, width=140, height=140)

            # B. Generar Tabla de Datos (La "tablita" debajo)
            data_subtabla = [
                ['Estado', 'Cant.', '%'],
                ['Aprobados', f"{aprobados}", f"{pct_aprob:.1f}%"],
                ['Pendientes', f"{pendientes}", f"{pct_pend:.1f}%"],
                ['TOTAL', f"{total_poblacion}", "100%"]
            ]

            sub_tabla = Table(data_subtabla, colWidths=[60, 40, 40])
            sub_tabla.setStyle(TableStyle([
                ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                ('FONTSIZE', (0,0), (-1,-1), 8),
                # Cabecera gris
                ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                # Fila Aprobados (Texto Verde)
                ('TEXTCOLOR', (0,1), (-1,1), colors.HexColor("#198754")), 
                # Fila Pendientes (Texto Rojo)
                ('TEXTCOLOR', (0,2), (-1,2), colors.HexColor("#dc3545")),
                # Fila Total (Negrita)
                ('FONTNAME', (0,3), (-1,3), 'Helvetica-Bold'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ]))

            # C. Agrupar Imagen y Tabla en una lista (Flowable)
            # Esto mete el gráfico y su tabla en la misma "caja"
            item_celda = [img_flowable, Spacer(1, 5), sub_tabla]
            celdas_graficos.append(item_celda)

        # 3. Organizar en Cuadrícula de 2 columnas
        # Convertimos la lista plana [1,2,3,4,5,6] en matriz [[1,2], [3,4], [5,6]]
        tabla_estructura = []
        for i in range(0, len(celdas_graficos), 2):
            fila = [celdas_graficos[i]]
            if i + 1 < len(celdas_graficos):
                fila.append(celdas_graficos[i+1])
            else:
                fila.append("") # Celda vacía si es impar
            tabla_estructura.append(fila)

        # 4. Estilo de la Tabla Principal (Invisible, solo para alinear)
        t_principal = Table(tabla_estructura, colWidths=[250, 250])
        t_principal.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'), # Alinear todo arriba
            ('ALIGN', (0,0), (-1,-1), 'CENTER'), # Centrar contenido
            ('BOTTOMPADDING', (0,0), (-1,-1), 20), # Espacio entre filas de gráficos
        ]))

        elements.append(t_principal)
        
        doc.build(elements)
        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename=f"Reporte_SGSI_{q_int or 'General'}.pdf")

from django.db import transaction
import pandas as pd
from .models import Empleado, ProgresoCharla, RegistroCarga

@login_required
def importar_excel(request):
    if request.method == "POST":
        form = UploadExcelForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['archivo']
            try:
                with transaction.atomic():
                    # 1. CARGA INICIAL: Leemos todo como texto (sin saltar filas aún)
                    # header=None para que no asuma que la fila 0 son los títulos
                    df_raw = pd.read_excel(file, header=None, dtype=str)

                    # 2. ENCONTRAR LA FILA DE CABECERA DINÁMICAMENTE
                    header_idx = None
                    for i, row in df_raw.iterrows():
                        # Buscamos en la primera columna (columna 0)
                        val = str(row[0]).strip().upper() if row[0] is not None else ""
                        if val in ["COD REG.", "REG.", "COD REG", "REG"]:
                            header_idx = i
                            break
                    
                    if header_idx is None:
                        raise ValueError("No se encontró la cabecera 'REG.' o 'COD REG.' en el archivo.")

                    # 3. RE-PROCESAR EL DATAFRAME DESDE LA CABECERA
                    # Tomamos los datos debajo de la fila encontrada
                    df = df_raw.iloc[header_idx + 1:].copy()
                    
                    # Limpieza de NaN para evitar errores en la DB
                    df = df.where(pd.notnull(df), None)

                    # 4. LIMPIEZA TOTAL Y CARGA MASIVA
                    Empleado.objects.all().delete()

                    empleados_para_crear = []
                    # Usamos .values para iterar más rápido ya que es una carga masiva
                    for row in df.values:
                        cod_reg_limpio = str(row[0]).strip() if row[0] is not None else None
                        if not cod_reg_limpio: continue # Saltar filas vacías al final del Excel

                        empleados_para_crear.append(Empleado(
                            cod_reg=cod_reg_limpio,
                            nombre_completo=str(row[1])[:255] if row[1] else "SIN NOMBRE",
                            unidad_organica=str(row[2])[:255] if row[2] else "SIN UNIDAD",
                            intendencia=str(row[3])[:255] if row[3] else "SIN INTENDENCIA",
                        ))
                    
                    empleados_creados = Empleado.objects.bulk_create(empleados_para_crear, batch_size=1000)

                    # 5. CARGA DE CHARLAS
                    charlas_para_crear = []
                    nombres_charlas = [
                        "Introduccion al SGSI", "Amenazas y Casos", 
                        "Casos Prácticos Seguridad", "Medidas Seguras", 
                        "Riesgos y amenazas", "Amenazas y delitos informáticos"
                    ]

                    for row, emp_obj in zip(df.values, empleados_creados):
                        col_idx = 4
                        for i in range(6):
                            # Lógica de detección: "SI" -> Asistió. Vacío u otro -> Pendiente.
                            raw_asistio = row[col_idx]
                            asistio_bool = str(raw_asistio).strip().upper() == "SI" if raw_asistio else False
                            
                            res_val = str(row[col_idx + 1]).strip() if row[col_idx + 1] else ""
                            
                            # Procesar fecha de forma segura
                            fec_val = None
                            raw_fec = row[col_idx + 2]
                            if raw_fec:
                                try:
                                    fec_val = pd.to_datetime(raw_fec).date()
                                except:
                                    fec_val = None

                            charlas_para_crear.append(ProgresoCharla(
                                empleado=emp_obj,
                                numero_charla=i + 1,
                                titulo_charla=nombres_charlas[i],
                                asistio=asistio_bool,
                                resultado=res_val,
                                fecha=fec_val
                            ))
                            col_idx += 3

                    ProgresoCharla.objects.bulk_create(charlas_para_crear, batch_size=2000)
                    RegistroCarga.objects.create()
                    
                    messages.success(request, f"¡Actualización veloz exitosa! Se encontraron los datos en la fila {header_idx + 1} del Excel. Y con {len(empleados_creados)} empleados cargados.")

                return redirect('importar_excel')

            except Exception as e:
                messages.error(request, f"Error al procesar: {str(e)}")
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
