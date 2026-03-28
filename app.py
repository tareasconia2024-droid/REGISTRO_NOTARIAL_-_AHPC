#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aplicación Flask - Sistema de Consulta Índice Onomástico AHPC
Proyecto: Prueba de Concepto (POC)
Autor: Asistente Claude
Fecha: 2026-01-31
"""

from flask import Flask, render_template, request, jsonify, make_response
import sqlite3
import os
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ahpc-indice-onomastico-2026'

# Configuración de la base de datos
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ahpc_indice_archivistico.db')

def get_db_connection():
    """Establece conexión con la base de datos"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Para acceder a columnas por nombre
    return conn

def ejecutar_consulta(query, params=()):
    """Ejecuta una consulta y retorna los resultados"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    resultados = cursor.fetchall()
    conn.close()
    return resultados

@app.route('/')
def index():
    """Página principal"""
    # Obtener estadísticas para la página principal
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Total de registros
    cursor.execute("SELECT COUNT(*) as total FROM indice_onomastico")
    total_registros = cursor.fetchone()['total']
    
    # Rango de años (limitado al período oficial 1775-1925)
    cursor.execute("SELECT MIN(año) as min, MAX(año) as max FROM indice_onomastico WHERE año IS NOT NULL AND año <= 1925")
    rango_años = cursor.fetchone()
    
    # Si no hay años válidos, usar los valores por defecto
    if not rango_años['max']:
        año_inicio = 1775
        año_fin = 1925
    else:
        año_inicio = rango_años['min']
        año_fin = min(rango_años['max'], 1925)  # Asegurar que no exceda 1925
    
    # Total de escribanos
    cursor.execute("SELECT COUNT(*) as total FROM escribanos")
    total_escribanos = cursor.fetchone()['total']
    
    conn.close()
    
    stats = {
        'total_registros': total_registros,
        'año_inicio': año_inicio,
        'año_fin': año_fin,
        'total_escribanos': total_escribanos
    }
    
    return render_template('index.html', stats=stats)

@app.route('/buscar')
def buscar():
    """Página de búsqueda avanzada"""
    # Obtener lista de escribanos para el filtro
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT DISTINCT nombre_normalizado 
        FROM escribanos 
        ORDER BY nombre_normalizado
    """)
    escribanos = [row['nombre_normalizado'] for row in cursor.fetchall()]
    
    # Obtener tipos de acto para el filtro
    cursor.execute("""
        SELECT DISTINCT tipo_acto 
        FROM indice_onomastico 
        WHERE tipo_acto IS NOT NULL
        ORDER BY tipo_acto
    """)
    tipos_acto = [row['tipo_acto'] for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template('buscar.html', escribanos=escribanos, tipos_acto=tipos_acto)

@app.route('/api/buscar', methods=['GET'])
def api_buscar():
    """API de búsqueda"""
    # Obtener parámetros de búsqueda
    apellido = request.args.get('apellido', '').strip()
    nombre = request.args.get('nombre', '').strip()
    año_desde = request.args.get('año_desde', '').strip()
    año_hasta = request.args.get('año_hasta', '').strip()
    escribano = request.args.get('escribano', '').strip()
    tipo_acto = request.args.get('tipo_acto', '').strip()
    texto_libre = request.args.get('texto_libre', '').strip()
    
    # Construir la consulta SQL dinámicamente
    query = """
        SELECT 
            i.id,
            i.año,
            i.foja_numero,
            i.foja_tipo,
            i.apellido_principal,
            i.nombre_principal,
            i.nombre_completo_original,
            i.tipo_acto,
            i.acto_juridico_texto,
            e.nombre_normalizado as escribano,
            i.numero_inventario_final
        FROM indice_onomastico i
        LEFT JOIN escribanos e ON i.escribano_id = e.id
        WHERE 1=1
    """
    
    params = []
    
    # Filtros
    if apellido:
        query += " AND i.apellido_principal LIKE ?"
        params.append(f"%{apellido.upper()}%")
    
    if nombre:
        query += " AND i.nombre_principal LIKE ?"
        params.append(f"%{nombre}%")
    
    if año_desde:
        query += " AND i.año >= ?"
        params.append(int(año_desde))
    
    if año_hasta:
        query += " AND i.año <= ?"
        params.append(int(año_hasta))
    
    if escribano:
        query += " AND e.nombre_normalizado = ?"
        params.append(escribano)
    
    if tipo_acto:
        query += " AND i.tipo_acto = ?"
        params.append(tipo_acto)
    
    if texto_libre:
        # Búsqueda de texto completo en FTS5
        query = """
            SELECT 
                i.id,
                i.año,
                i.foja_numero,
                i.foja_tipo,
                i.apellido_principal,
                i.nombre_principal,
                i.nombre_completo_original,
                i.tipo_acto,
                i.acto_juridico_texto,
                e.nombre_normalizado as escribano,
                i.numero_inventario_final
            FROM indice_onomastico i
            LEFT JOIN escribanos e ON i.escribano_id = e.id
            WHERE i.id IN (
                SELECT rowid FROM indice_onomastico_fts 
                WHERE indice_onomastico_fts MATCH ?
            )
        """
        params = [texto_libre]
    
    # Ordenar por año
    query += " ORDER BY i.año DESC, i.apellido_principal ASC LIMIT 100"
    
    # Ejecutar consulta
    resultados = ejecutar_consulta(query, params)
    
    # Convertir a lista de diccionarios
    registros = []
    for row in resultados:
        registro = {
            'id': row['id'],
            'año': row['año'],
            'foja': f"{row['foja_numero']}{row['foja_tipo']}" if row['foja_numero'] else 'S/F',
            'apellido': row['apellido_principal'],
            'nombre': row['nombre_principal'],
            'nombre_completo': row['nombre_completo_original'],
            'tipo_acto': row['tipo_acto'],
            'acto_juridico': row['acto_juridico_texto'],
            'escribano': row['escribano'],
            'inventario': row['numero_inventario_final']
        }
        registros.append(registro)
    
    return jsonify({
        'total': len(registros),
        'registros': registros
    })

@app.route('/detalle/<int:registro_id>')
def detalle(registro_id):
    """Página de detalle de un registro"""
    query = """
        SELECT 
            i.*,
            e.nombre_normalizado as escribano_nombre,
            e.apellido as escribano_apellido,
            e.nombre as escribano_nombre_propio
        FROM indice_onomastico i
        LEFT JOIN escribanos e ON i.escribano_id = e.id
        WHERE i.id = ?
    """
    
    resultados = ejecutar_consulta(query, (registro_id,))
    
    if not resultados:
        return "Registro no encontrado", 404
    
    registro = dict(resultados[0])
    
    return render_template('detalle.html', registro=registro)

@app.route('/api/exportar-pdf', methods=['GET'])
def exportar_pdf():
    """Exporta resultados de búsqueda a PDF"""
    # Obtener parámetros de búsqueda (mismos que /api/buscar)
    apellido = request.args.get('apellido', '').strip()
    nombre = request.args.get('nombre', '').strip()
    año_desde = request.args.get('año_desde', '').strip()
    año_hasta = request.args.get('año_hasta', '').strip()
    escribano = request.args.get('escribano', '').strip()
    tipo_acto = request.args.get('tipo_acto', '').strip()
    texto_libre = request.args.get('texto_libre', '').strip()
    
    # Construir la consulta SQL (igual que en /api/buscar)
    query = """
        SELECT 
            i.id,
            i.año,
            i.foja_numero,
            i.foja_tipo,
            i.apellido_principal,
            i.nombre_principal,
            i.nombre_completo_original,
            i.tipo_acto,
            i.acto_juridico_texto,
            e.nombre_normalizado as escribano,
            i.numero_inventario_final
        FROM indice_onomastico i
        LEFT JOIN escribanos e ON i.escribano_id = e.id
        WHERE 1=1
    """
    
    params = []
    
    if apellido:
        query += " AND i.apellido_principal LIKE ?"
        params.append(f"%{apellido.upper()}%")
    
    if nombre:
        query += " AND i.nombre_principal LIKE ?"
        params.append(f"%{nombre}%")
    
    if año_desde:
        query += " AND i.año >= ?"
        params.append(int(año_desde))
    
    if año_hasta:
        query += " AND i.año <= ?"
        params.append(int(año_hasta))
    
    if escribano:
        query += " AND e.nombre_normalizado = ?"
        params.append(escribano)
    
    if tipo_acto:
        query += " AND i.tipo_acto = ?"
        params.append(tipo_acto)
    
    if texto_libre:
        query = """
            SELECT 
                i.id,
                i.año,
                i.foja_numero,
                i.foja_tipo,
                i.apellido_principal,
                i.nombre_principal,
                i.nombre_completo_original,
                i.tipo_acto,
                i.acto_juridico_texto,
                e.nombre_normalizado as escribano,
                i.numero_inventario_final
            FROM indice_onomastico i
            LEFT JOIN escribanos e ON i.escribano_id = e.id
            WHERE i.id IN (
                SELECT rowid FROM indice_onomastico_fts 
                WHERE indice_onomastico_fts MATCH ?
            )
        """
        params = [texto_libre]
    
    query += " ORDER BY i.año DESC, i.apellido_principal ASC LIMIT 500"
    
    # Ejecutar consulta
    resultados = ejecutar_consulta(query, params)
    
    # Crear PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=18)
    
    # Contenedor para elementos del PDF
    elements = []
    
    # Estilos
    styles = getSampleStyleSheet()
    
    # Título
    title_text = "ARCHIVO HISTÓRICO PROVINCIAL DE CÓRDOBA<br/>Índice Onomástico - Registro Notarial N°1<br/>Resultados de Búsqueda"
    title = Paragraph(title_text, styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))
    
    # Criterios de búsqueda
    criterios = []
    if apellido:
        criterios.append(f"Apellido: {apellido}")
    if nombre:
        criterios.append(f"Nombre: {nombre}")
    if año_desde and año_hasta:
        criterios.append(f"Período: {año_desde}-{año_hasta}")
    elif año_desde:
        criterios.append(f"Desde: {año_desde}")
    elif año_hasta:
        criterios.append(f"Hasta: {año_hasta}")
    if escribano:
        criterios.append(f"Escribano: {escribano}")
    if tipo_acto:
        criterios.append(f"Tipo: {tipo_acto}")
    if texto_libre:
        criterios.append(f"Texto: {texto_libre}")
    
    if criterios:
        criterios_text = "<b>Criterios de búsqueda:</b> " + " | ".join(criterios)
        criterios_para = Paragraph(criterios_text, styles['Normal'])
        elements.append(criterios_para)
        elements.append(Spacer(1, 12))
    
    # Total de resultados
    total_text = f"<b>Total de resultados:</b> {len(resultados)} registro(s)"
    if len(resultados) == 500:
        total_text += " (máximo 500)"
    total_para = Paragraph(total_text, styles['Normal'])
    elements.append(total_para)
    elements.append(Spacer(1, 12))
    
    # Tabla de resultados
    if resultados:
        # Datos de la tabla
        data = [['Año', 'Apellido', 'Nombre', 'Tipo Acto', 'Escribano', 'Foja']]
        
        for row in resultados:
            foja = f"{row['foja_numero']}{row['foja_tipo']}" if row['foja_numero'] else 'S/F'
            año = str(row['año']) if row['año'] else 'S/D'
            apellido = (row['apellido_principal'] or '')[:20]  # Limitar longitud
            nombre = (row['nombre_principal'] or '')[:15]
            tipo = (row['tipo_acto'] or '')[:12]
            escribano = (row['escribano'] or '')[:25]
            
            data.append([año, apellido, nombre, tipo, escribano, foja])
        
        # Crear tabla
        table = Table(data, colWidths=[0.8*inch, 1.5*inch, 1.2*inch, 1*inch, 1.8*inch, 0.7*inch])
        
        # Estilo de la tabla (blanco y negro)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)])
        ]))
        
        elements.append(table)
    else:
        no_results = Paragraph("No se encontraron resultados con los criterios especificados.", styles['Normal'])
        elements.append(no_results)
    
    # Construir PDF
    doc.build(elements)
    
    # Preparar respuesta
    pdf = buffer.getvalue()
    buffer.close()
    
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=indice_onomastico_resultados.pdf'
    
    return response

@app.route('/api/apellidos', methods=['GET'])
def api_apellidos():
    """API para obtener lista de apellidos únicos (para autocompletado)"""
    query = request.args.get('q', '').strip().upper()
    
    if len(query) < 2:
        return jsonify([])
    
    # Búsqueda de apellidos que empiecen con las letras escritas
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT DISTINCT apellido_principal
        FROM indice_onomastico
        WHERE apellido_principal LIKE ?
        ORDER BY apellido_principal
        LIMIT 20
    """, (f"{query}%",))
    
    apellidos = [row['apellido_principal'] for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(apellidos)

@app.route('/estadisticas')
def estadisticas():
    """Página de estadísticas"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Top apellidos
    cursor.execute("""
        SELECT apellido_principal, COUNT(*) as total
        FROM indice_onomastico
        GROUP BY apellido_principal
        ORDER BY total DESC
        LIMIT 20
    """)
    top_apellidos = [dict(row) for row in cursor.fetchall()]
    
    # Distribución por década
    cursor.execute("""
        SELECT decada, COUNT(*) as total
        FROM indice_onomastico
        WHERE decada IS NOT NULL
        GROUP BY decada
        ORDER BY decada
    """)
    por_decada = [dict(row) for row in cursor.fetchall()]
    
    # Distribución por tipo de acto
    cursor.execute("""
        SELECT tipo_acto, COUNT(*) as total
        FROM indice_onomastico
        WHERE tipo_acto IS NOT NULL
        GROUP BY tipo_acto
        ORDER BY total DESC
    """)
    por_tipo_acto = [dict(row) for row in cursor.fetchall()]
    
    # Top escribanos
    cursor.execute("""
        SELECT e.nombre_normalizado, COUNT(i.id) as total
        FROM escribanos e
        LEFT JOIN indice_onomastico i ON e.id = i.escribano_id
        GROUP BY e.id
        ORDER BY total DESC
        LIMIT 10
    """)
    top_escribanos = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template('estadisticas.html',
                         top_apellidos=top_apellidos,
                         por_decada=por_decada,
                         por_tipo_acto=por_tipo_acto,
                         top_escribanos=top_escribanos)

if __name__ == "__main__":
    import os
    # Esto le dice a tu app: "Usa el puerto que Render te asigne"
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
