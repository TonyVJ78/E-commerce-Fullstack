"""
Exporta el esquema completo de base de datos de Kantu Market en SQL puro para PostgreSQL.
Genera sentencias CREATE TABLE, PK, FK, UNIQUE, CHECK e INDEX limpias y listas para copiar y ejecutar.
"""

import os
import sys
import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection
from django.apps import apps

app_labels = ['usuarios', 'tiendas', 'catalogo', 'pedidos', 'crm', 'marketing', 'ia']
models = [
    m for m in apps.get_models()
    if m._meta.app_label in app_labels
    and not m._meta.auto_created
    and m._meta.db_table not in ('usuario_groups', 'usuario_user_permissions')
]

with connection.schema_editor(collect_sql=True) as editor:
    for m in models:
        editor.create_model(m)
    raw_statements = editor.collected_sql

# Filtrar sentencias invalidas o repetidas
filtered_statements = []
seen_creates = set()

for stmt in raw_statements:
    s = stmt.strip()
    if not s:
        continue
    # Quitar creates vacios
    if s.startswith('CREATE TABLE') and s.endswith('();'):
        continue
    if s.startswith('CREATE TABLE'):
        table_name = s.split()[2].strip('"')
        if table_name in seen_creates:
            continue
        seen_creates.add(table_name)
    # Excluir referencias a tablas de django auth si existen
    if 'REFERENCES "auth_' in s:
        continue
    filtered_statements.append(s.rstrip(';') + ';')

output_path = os.path.join(os.path.dirname(BASE_DIR), 'kantu_market_database.sql')
with open(output_path, 'w', encoding='utf-8') as f:
    f.write('-- =============================================================================\n')
    f.write('-- KANTU MARKET - ESQUEMA DE BASE DE DATOS POSTGRESQL 16\n')
    f.write('-- Total Tablas: 33 entidades relacionales\n')
    f.write('-- =============================================================================\n\n')
    f.write('\n\n'.join(filtered_statements))
    f.write('\n')

print(f"Esquema SQL generado en: {output_path} ({len(filtered_statements)} sentencias)")
