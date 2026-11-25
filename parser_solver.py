import re
import pandas as pd


def extraer_responsable_nota(texto):
    """Extrae el nombre del especialista desde el bloque '» Cerrado por ...' o Work notes."""
    if pd.isna(texto):
        return None
    texto_str = str(texto)
    m1 = re.search(r'Cerrado por\s+([^\n»]+)', texto_str)
    if m1:
        return m1.group(1).strip()
    m2 = re.search(r'Solver\s*\(Work notes\)\s*\n([^:\n]+):', texto_str)
    if m2:
        return m2.group(1).strip()
    return None


def normalizar_nombre(nombre):
    """Normaliza variantes de nombre completo de Solver a formato corto consistente."""
    if not nombre or pd.isna(nombre) or str(nombre).strip() == '':
        return 'Sin Asignar'
    n = str(nombre).strip()
    n_low = n.lower()
    if 'jeremy' in n_low:
        return 'Jeremy Vera'
    if 'sebastian' in n_low or 'sebastián' in n_low:
        return 'Sebastián Banda'
    if 'jose mauricio' in n_low or 'josé mauricio' in n_low:
        return 'Jose Vera'
    return n


def evaluar_sla_ticket(tipo, horas, reasignaciones=0, estado='Cerrado'):
    """
    Evalúa el cumplimiento SLA operativo según tipo de caso y prioridad base del reporte:
    - Incidentes (Priority 5 - Planning en Solver): objetivo operativo <= 24h hábiles (alerta > 8h).
    - Requerimientos (Priority 4 - Low en Solver): objetivo operativo <= 72h / 3 días (alerta > 48h).
    Retorna tupla (sla_estado, sla_meta_horas).
    """
    if estado != 'Cerrado':
        meta = 24.0 if tipo == 'Incidente' else 72.0
        return ('En Curso / Pendiente', meta)

    if tipo == 'Incidente':
        meta = 24.0
        if horas <= 24.0:
            return ('Cumplido', meta)
        return ('Vencido', meta)
    else:
        meta = 72.0
        if horas <= 72.0:
            return ('Cumplido', meta)
        return ('Vencido', meta)


def procesar_excel_solver(filepath):
    """
    Lee el reporte exportado desde Solver (hojas 'INC' y 'Requerimientos (Tasks)'),
    resuelve el responsable técnico, calcula horas hábiles y evalúa el SLA operativo.
    """
    xls = pd.ExcelFile(filepath)
    registros = []

    # 1. Procesar Incidentes (INC)
    if 'INC' in xls.sheet_names:
        df_inc = pd.read_excel(xls, sheet_name='INC')
        for _, row in df_inc.iterrows():
            ticket_num = str(row.get('Number', '')).strip()
            if not ticket_num or ticket_num == 'nan':
                continue

            resp = row.get('Solver assigned to')
            if pd.isna(resp) or str(resp).strip() == '':
                resp = extraer_responsable_nota(row.get('Resolution notes'))
            if (pd.isna(resp) or str(resp).strip() == '') and str(row.get('Closed by')) != 'System Administrator':
                resp = row.get('Closed by')

            estado_raw = str(row.get('Incident state', '')).strip()
            estado = 'Cerrado' if estado_raw in ['Closed', 'Resolved', 'Canceled'] else 'Pendiente'

            bus_dur = row.get('Business duration')
            horas = round(float(bus_dur) / 3600.0, 2) if pd.notna(bus_dur) else 0.0
            horas = max(horas, 0.0)

            reasig = int(row.get('Reassignment count', 0)) if pd.notna(row.get('Reassignment count')) else 0
            prioridad = str(row.get('Priority', '5 - Planning')).strip()
            sla_estado, sla_meta = evaluar_sla_ticket('Incidente', horas, reasig, estado)

            fecha_ini = pd.to_datetime(row.get('Opened'), errors='coerce')
            fecha_fin = pd.to_datetime(row.get('Resolved') or row.get('Closed'), errors='coerce')

            servicio = row.get('Specification') if pd.notna(row.get('Specification')) else row.get('Short description')

            registros.append({
                'ticket_num': ticket_num,
                'tipo': 'Incidente',
                'direccion': str(servicio).strip() if pd.notna(servicio) else 'Soporte Apple',
                'responsable': normalizar_nombre(resp),
                'estado': estado,
                'fecha_inicio': fecha_ini.strftime('%Y-%m-%d %H:%M') if pd.notna(fecha_ini) else '',
                'fecha_fin': fecha_fin.strftime('%Y-%m-%d %H:%M') if pd.notna(fecha_fin) else '',
                'tiempo_horas': horas,
                'prioridad': prioridad,
                'reasignaciones': reasig,
                'sla_estado': sla_estado,
                'sla_meta_horas': sla_meta
            })

    # 2. Procesar Requerimientos (Tasks)
    sheet_req = next((s for s in xls.sheet_names if 'Requerimientos' in s or 'Tasks' in s), None)
    if sheet_req:
        df_req = pd.read_excel(xls, sheet_name=sheet_req)
        for _, row in df_req.iterrows():
            ticket_num = str(row.get('Number', '')).strip()
            if not ticket_num or ticket_num == 'nan':
                continue

            resp = row.get('Solver assigned to')
            if pd.isna(resp) or str(resp).strip() == '':
                resp = extraer_responsable_nota(row.get('Close notes'))

            estado_raw = str(row.get('State', '')).strip()
            estado = 'Cerrado' if estado_raw.startswith('Closed') else 'Pendiente'

            fecha_ini = pd.to_datetime(row.get('Actual start') or row.get('Created'), errors='coerce')
            fecha_fin = pd.to_datetime(row.get('Actual end') or row.get('Closed'), errors='coerce')

            if pd.notna(fecha_ini) and pd.notna(fecha_fin):
                horas = round((fecha_fin - fecha_ini).total_seconds() / 3600.0, 2)
            else:
                horas = 0.0
            horas = max(horas, 0.0)

            prioridad = str(row.get('Priority', '4 - Low')).strip()
            sla_estado, sla_meta = evaluar_sla_ticket('Requerimiento', horas, 0, estado)

            servicio = row.get('Configuration item') if pd.notna(row.get('Configuration item')) else row.get('Short description')

            registros.append({
                'ticket_num': ticket_num,
                'tipo': 'Requerimiento',
                'direccion': str(servicio).strip() if pd.notna(servicio) else 'Requerimiento Apple',
                'responsable': normalizar_nombre(resp),
                'estado': estado,
                'fecha_inicio': fecha_ini.strftime('%Y-%m-%d %H:%M') if pd.notna(fecha_ini) else '',
                'fecha_fin': fecha_fin.strftime('%Y-%m-%d %H:%M') if pd.notna(fecha_fin) else '',
                'tiempo_horas': horas,
                'prioridad': prioridad,
                'reasignaciones': 0,
                'sla_estado': sla_estado,
                'sla_meta_horas': sla_meta
            })

    return registros
