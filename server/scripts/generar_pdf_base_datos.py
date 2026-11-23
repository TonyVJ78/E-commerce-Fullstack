"""
Generador de Documentacion PDF de la Base de Datos de Kantu Market.
Extrae metadatos oficiales directamente de los modelos Django 5.1 y genera
un PDF profesional con ReportLab.
"""

import os
import sys
import django

# Configurar entorno Django
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.apps import apps
from django.db import models

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """Canvas con numeracion de paginas de dos pasadas (Pagina X de Y)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))

        # No dibujar pie ni encabezado en portada
        if self._pageNumber > 1:
            # Encabezado
            self.drawString(36, 810, "KANTU MARKET - DICCIONARIO DE DATOS Y MODELO RELACIONAL")
            self.drawRightString(559, 810, "PostgreSQL 16 & Django 5.1")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(36, 804, 559, 804)

            # Pie de pagina
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(36, 40, 559, 40)
            self.drawString(36, 28, "Confidencial - Documentacion Tecnica de Ingenieria")
            self.drawRightString(559, 28, f"Pagina {self._pageNumber} de {page_count}")

        self.restoreState()


def get_field_type_display(field):
    """Devuelve representacion amigable del tipo de dato."""
    internal_type = field.get_internal_type()
    if internal_type == 'CharField':
        return f'VARCHAR({field.max_length})'
    elif internal_type == 'TextField':
        return 'TEXT'
    elif internal_type == 'IntegerField':
        return 'INTEGER'
    elif internal_type == 'PositiveIntegerField':
        return 'INTEGER (UNSIGNED)'
    elif internal_type == 'SmallIntegerField':
        return 'SMALLINT'
    elif internal_type == 'BooleanField':
        return 'BOOLEAN'
    elif internal_type == 'DateTimeField':
        return 'TIMESTAMP WITH TIME ZONE'
    elif internal_type == 'DateField':
        return 'DATE'
    elif internal_type == 'DecimalField':
        return f'DECIMAL({field.max_digits}, {field.decimal_places})'
    elif internal_type == 'ForeignKey':
        return 'FOREIGN KEY (BIGINT)'
    elif internal_type == 'OneToOneField':
        return 'ONE-TO-ONE (BIGINT)'
    elif internal_type == 'JSONField':
        return 'JSONB'
    elif internal_type == 'ArrayField':
        return 'ARRAY'
    elif internal_type == 'SlugField':
        return f'SLUG({field.max_length})'
    elif internal_type == 'EmailField':
        return f'VARCHAR({field.max_length or 254})'
    elif internal_type == 'URLField':
        return f'VARCHAR({field.max_length or 200})'
    elif internal_type == 'GenericIPAddressField':
        return 'INET'
    elif internal_type == 'BigAutoField':
        return 'BIGSERIAL (PK)'
    elif internal_type == 'AutoField':
        return 'SERIAL (PK)'
    return internal_type.upper()


def get_field_constraint(field):
    """Determina las restricciones del campo (PK, FK, UK, NULL)."""
    tags = []
    if getattr(field, 'primary_key', False):
        tags.append('PK')
    if field.is_relation and field.related_model:
        target_table = field.related_model._meta.db_table
        target_pk = field.target_field.name if hasattr(field, 'target_field') else 'id'
        tags.append(f'FK -> {target_table}.{target_pk}')
    if getattr(field, 'unique', False) and not getattr(field, 'primary_key', False):
        tags.append('UNIQUE')
    if getattr(field, 'null', False):
        tags.append('NULL')
    else:
        tags.append('NOT NULL')
    return ', '.join(tags)


def generar_pdf_base_datos(output_path):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=50,
        bottomMargin=50
    )

    styles = getSampleStyleSheet()

    # Estilos tipograficos
    style_cover_title = ParagraphStyle(
        'CoverTitle',
        fontName='Helvetica-Bold',
        fontSize=26,
        leading=32,
        textColor=colors.HexColor('#0F172A'),
        alignment=0,
        spaceAfter=12
    )

    style_cover_sub = ParagraphStyle(
        'CoverSub',
        fontName='Helvetica',
        fontSize=13,
        leading=18,
        textColor=colors.HexColor('#475569'),
        spaceAfter=24
    )

    style_mod_header = ParagraphStyle(
        'ModHeader',
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=19,
        textColor=colors.HexColor('#0F172A'),
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    )

    style_table_title = ParagraphStyle(
        'TableTitle',
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#C8102E'), # Rojo Kantu
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    )

    style_desc = ParagraphStyle(
        'DescText',
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#334155'),
        spaceAfter=5,
        keepWithNext=True
    )

    style_cell_header = ParagraphStyle(
        'CellHeader',
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white
    )

    style_cell = ParagraphStyle(
        'CellText',
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#1E293B')
    )

    style_cell_bold = ParagraphStyle(
        'CellTextBold',
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#0F172A')
    )

    style_cell_pk = ParagraphStyle(
        'CellTextPK',
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=9,
        textColor=colors.HexColor('#C8102E')
    )

    style_cell_fk = ParagraphStyle(
        'CellTextFK',
        fontName='Helvetica',
        fontSize=7,
        leading=9,
        textColor=colors.HexColor('#0284C7')
    )

    elements = []

    # =========================================================================
    # PORTADA
    # =========================================================================
    elements.append(Spacer(1, 40))
    elements.append(Paragraph("KANTU MARKET", ParagraphStyle(
        'Brand',
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=14,
        textColor=colors.HexColor('#C8102E'),
        spaceAfter=8
    )))
    elements.append(Paragraph("DICCIONARIO DE DATOS Y MODELO RELACIONAL", style_cover_title))
    elements.append(Paragraph(
        "Especificacion tecnica completa del esquema de base de datos multitenant, relaciones de integridad referencial, entidades, campos, tipos y restricciones.",
        style_cover_sub
    ))

    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#0F172A'), spaceAfter=20))

    # Ficha tecnica de la portada
    ficha_data = [
        [Paragraph("<b>Sistema:</b>", style_cell_bold), Paragraph("Kantu Market (Marketplace Multitenant Boliviano)", style_cell)],
        [Paragraph("<b>Motor de BD:</b>", style_cell_bold), Paragraph("PostgreSQL 16 (Neon Cloud Database)", style_cell)],
        [Paragraph("<b>Framework ORM:</b>", style_cell_bold), Paragraph("Django 5.1 & Django REST Framework", style_cell)],
        [Paragraph("<b>Estrategia Multitenancy:</b>", style_cell_bold), Paragraph("Row-Level Partitioning logicamente aislada por tienda_id", style_cell)],
        [Paragraph("<b>Total Entidades:</b>", style_cell_bold), Paragraph("33 Tablas Relacionales estructuradas en 7 modulos", style_cell)],
        [Paragraph("<b>Casos de Uso Recientes:</b>", style_cell_bold), Paragraph("CU-26 (Soporte/Reclamos) y CU-27 (Campanas Carrito Abandonado)", style_cell)],
        [Paragraph("<b>Fecha de Generacion:</b>", style_cell_bold), Paragraph("Octubre 2026", style_cell)],
        [Paragraph("<b>Estado de BD:</b>", style_cell_bold), Paragraph("Produccion / Migraciones 100% Sincronizadas", style_cell)],
    ]
    t_ficha = Table(ficha_data, colWidths=[130, 393])
    t_ficha.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#E2E8F0')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    elements.append(t_ficha)
    elements.append(Spacer(1, 30))

    # Resumen de Modulos
    elements.append(Paragraph("<b>DISTRIBUCION ARQUITECTURAL DE MODULOS</b>", style_table_title))
    mod_summary = [
        [Paragraph("Modulo", style_cell_header), Paragraph("App Django", style_cell_header), Paragraph("Tablas", style_cell_header), Paragraph("Responsabilidad Principal", style_cell_header)],
        [Paragraph("1. Seguridad y Accesos", style_cell_bold), Paragraph("apps.usuarios", style_cell), Paragraph("6", style_cell), Paragraph("Autenticacion con email, RBAC, auditoria y bitacora", style_cell)],
        [Paragraph("2. Tiendas Multitenant", style_cell_bold), Paragraph("apps.tiendas", style_cell), Paragraph("3", style_cell), Paragraph("Tenants, personal de tiendas y direcciones de despacho", style_cell)],
        [Paragraph("3. Catalogo e Inventario", style_cell_bold), Paragraph("apps.catalogo", style_cell), Paragraph("4", style_cell), Paragraph("Arbol de categorias, productos, SKUs y kardex de stock", style_cell)],
        [Paragraph("4. Comercio y Ventas", style_cell_bold), Paragraph("apps.pedidos", style_cell), Paragraph("10", style_cell), Paragraph("Carritos, pedidos, transacciones de pago, envios y resenas", style_cell)],
        [Paragraph("5. CRM y Fidelizacion", style_cell_bold), Paragraph("apps.crm", style_cell), Paragraph("9", style_cell), Paragraph("Ficha 360, Wishlist, Reclamos (CU-26) y Carritos (CU-27)", style_cell)],
        [Paragraph("6. Marketing y Cupones", style_cell_bold), Paragraph("apps.marketing", style_cell), Paragraph("4", style_cell), Paragraph("Campanas de descuento, cupones y bitacora de notificaciones", style_cell)],
        [Paragraph("7. Inteligencia Artificial", style_cell_bold), Paragraph("apps.ia", style_cell), Paragraph("3", style_cell), Paragraph("Eventos de navegacion, recomendaciones y reportes ejecutivos", style_cell)],
    ]
    t_mod = Table(mod_summary, colWidths=[110, 80, 40, 293])
    t_mod.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0F172A')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    elements.append(t_mod)

    elements.append(PageBreak())

    # =========================================================================
    # DETALLE DE MODELOS POR MODULO
    # =========================================================================
    modulos_orden = [
        ('apps.usuarios', 'MODULO 1: SEGURIDAD, ACCESOS Y AUDITORIA', 'Gestion de usuarios con email como identificador unico, roles, permisos granulares, bitacora inmutable de logins y trazabilidad forense de operaciones administrativas.'),
        ('apps.tiendas', 'MODULO 2: GESTION DE TIENDAS MULTITENANT', 'Eje de particionamiento logico del marketplace. Administra las tiendas (tenants), personal asociado con roles internos y sucursales fisicas.'),
        ('apps.catalogo', 'MODULO 3: CATALOGO DE PRODUCTOS E INVENTARIO', 'Jerarquia de categorias, productos base con metadatos JSON y tags PostgreSQL, variantes comerciales (SKU) con stock y kardex inmutable de movimientos.'),
        ('apps.pedidos', 'MODULO 4: COMERCIO ELECTRONICO, VENTAS Y DESPACHO', 'Flujo transaccional completo: canastas de compra, congelamiento de precios historicos en pedidos, trazabilidad de pagos bancarios/QR, despacho de envios y valoraciones.'),
        ('apps.crm', 'MODULO 5: CRM, FIDELIZACION, SOPORTE (CU-26) Y RECUPERACION (CU-27)', 'Segmentacion analitica de clientes, Ficha 360, listas de deseos, tickets de soporte postventa con chat bidireccional y campanas automaticas de recuperacion de carritos abandonados.'),
        ('apps.marketing', 'MODULO 6: MARKETING, CUPONES Y COMUNICACIONES', 'Campanas promocionales asociadas a segmentos, emision y redencion de cupones de descuento y registro multicanal de notificaciones.'),
        ('apps.ia', 'MODULO 7: INTELIGENCIA ARTIFICIAL Y TELEMETRIA', 'Captura de telemetria de usuario (vistas, busquedas, clics), generacion automatizada de scores de recomendacion de productos y reportes analiticos.')
    ]

    for app_label, mod_titulo, mod_desc in modulos_orden:
        elements.append(Paragraph(mod_titulo, style_mod_header))
        elements.append(Paragraph(mod_desc, style_desc))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#94A3B8'), spaceAfter=10))

        app_config = apps.get_app_config(app_label.split('.')[-1])
        modelos = list(app_config.get_models())

        for model in modelos:
            meta = model._meta
            nombre_tabla = meta.db_table
            nombre_modelo = model.__name__
            docstring = (model.__doc__ or 'Sin descripcion').strip().split('\n')[0]

            # Encabezado de la tabla
            elements.append(Paragraph(
                f"Tabla: <b>{nombre_tabla}</b> &nbsp;&nbsp;|&nbsp;&nbsp; Modelo: <b>{nombre_modelo}</b>",
                style_table_title
            ))
            elements.append(Paragraph(f"<i>Descripcion:</i> {docstring}", style_desc))

            # Columnas
            columnas_data = [
                [
                    Paragraph("Campo", style_cell_header),
                    Paragraph("Tipo de Dato", style_cell_header),
                    Paragraph("Restricciones / Llaves", style_cell_header),
                    Paragraph("Descripcion / Destino", style_cell_header)
                ]
            ]

            fields = meta.fields
            for f in fields:
                f_name = f.name
                f_type = get_field_type_display(f)
                f_constraint = get_field_constraint(f)

                # Estilo de celda segun tipo de llave
                if 'PK' in f_constraint:
                    c_style = style_cell_pk
                elif 'FK' in f_constraint:
                    c_style = style_cell_fk
                else:
                    c_style = style_cell

                # Descripcion / help text
                desc_text = f.help_text or f.verbose_name or ''
                if f.is_relation and f.related_model:
                    desc_text = f"Relacion con {f.related_model._meta.db_table} ({f.related_model.__name__})"

                columnas_data.append([
                    Paragraph(f_name, style_cell_bold),
                    Paragraph(f_type, style_cell),
                    Paragraph(f_constraint, c_style),
                    Paragraph(desc_text, style_cell)
                ])

            # Construir tabla PDF
            t_col = Table(columnas_data, colWidths=[105, 125, 145, 148])
            t_col.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E293B')),
                ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
                ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8FAFC')]),
                ('TOPPADDING', (0,0), (-1,-1), 3),
                ('BOTTOMPADDING', (0,0), (-1,-1), 3),
                ('LEFTPADDING', (0,0), (-1,-1), 4),
                ('RIGHTPADDING', (0,0), (-1,-1), 4),
            ]))

            elements.append(t_col)

            # Relaciones entrantes (quien apunta a esta tabla)
            rel_entrantes = [
                rel for rel in meta.related_objects
                if hasattr(rel, 'related_model') and rel.related_model
            ]
            if rel_entrantes:
                rel_strs = [
                    f"<b>{rel.related_model._meta.db_table}</b> (via {rel.field.name})"
                    for rel in rel_entrantes[:6] # Limitar a 6 para no saturar
                ]
                rel_p = Paragraph(
                    f"<b>Entidades Dependientes (1:N):</b> {', '.join(rel_strs)}",
                    style_desc
                )
                elements.append(Spacer(1, 2))
                elements.append(rel_p)

            elements.append(Spacer(1, 10))

        elements.append(PageBreak())

    # Construir documento
    doc.build(elements, canvasmaker=NumberedCanvas)
    print(f"Documento generado exitosamente en: {output_path}")

if __name__ == '__main__':
    target = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'Kantu_Market_Base_de_Datos.pdf'
    )
    generar_pdf_base_datos(target)
