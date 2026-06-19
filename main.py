# ============================================================
# APP-COBROS-V12-FINAL - MAIN.PY PRODUCCIÓN
# Python + Kivy + SQLite
#
# Características:
# - Base SQLite persistente real.
# - En PC guarda la DB junto al proyecto.
# - En Android guarda la DB en user_data_dir.
# - No carga datos demo automáticamente.
# - Interfaz mobile-first.
# - Nuevo cliente por pasos.
# - Cálculo automático de total, cuota y saldo del crédito.
# - CRUD cliente/préstamo.
# - Cobros: Cuota, Aporte, No Pago, Siguiente Día.
# - Estados visuales: verde, amarillo, rojo.
# - Movimientos de caja.
# - Resumen del día.
# ============================================================

from datetime import datetime, timedelta
from pathlib import Path
import os
import sqlite3
import json
import urllib.request
import urllib.error
import ssl
import certifi
import urllib.parse
import threading
import calendar
import time
import uuid
import shutil

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import ObjectProperty, NumericProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget
from kivy.utils import platform


# ============================================================
# CONFIGURACIÓN VISUAL
# ============================================================

if platform not in ("android", "ios"):
    Window.size = (430, 820)

Window.clearcolor = (0.06, 0.07, 0.10, 1)

BLUE = (0.117, 0.227, 0.541, 1)
BLUE_DARK = (0.08, 0.16, 0.36, 1)
GOLD = (0.93, 0.69, 0.13, 1)
WHITE = (1, 1, 1, 1)
TEXT = (0.10, 0.12, 0.16, 1)
MUTED = (0.43, 0.47, 0.54, 1)
DARK = (0.12, 0.14, 0.18, 1)
SUCCESS = (0.12, 0.62, 0.32, 1)
DANGER = (0.83, 0.18, 0.18, 1)
LIGHT_BG = (0.95, 0.96, 0.98, 1)

STATUS_GREEN = (0.86, 0.98, 0.89, 1)
STATUS_YELLOW = (1.00, 0.96, 0.78, 1)
STATUS_RED = (1.00, 0.88, 0.88, 1)
STATUS_PAID_OFF = (0.86, 0.94, 1.00, 1)
STATUS_BORDER_GREEN = (0.12, 0.62, 0.32, 1)
STATUS_BORDER_YELLOW = (0.93, 0.69, 0.13, 1)
STATUS_BORDER_RED = (0.83, 0.18, 0.18, 1)
STATUS_BORDER_PAID_OFF = (0.12, 0.45, 0.78, 1)


# ============================================================
# CONFIGURACIÓN SUPABASE
# ============================================================
# Pega aquí los datos de tu proyecto Supabase.
# No uses SERVICE_ROLE_KEY dentro de la app móvil.
SUPABASE_URL = "https://frvzniydfdmhltxwyknh.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZydnpuaXlkZmRtaGx0eHd5a25oIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1Nzc3NjUsImV4cCI6MjA5NjE1Mzc2NX0.2NFIkalEfGf0P7d9bT_kmNW_DvMU8I9bYTqQxabV_hI"
COBRADOR_ID = "e058ca8f-210f-4c2e-8c7d-33ed239b3f20"
COBRADOR_NOMBRE = "PACHO"

# Versión para cliente único: el dueño es administrador y cobrador a la vez.
MODO_DUENO_UNICO = True
DUENO_COBRADOR_ID = COBRADOR_ID
DUENO_NOMBRE = "PACHO"
CENTRAL_CASH_ID = "CAJA_CENTRAL"
CENTRAL_CASH_NAME = "CAJA CENTRAL ADMIN"


SYNC_ENABLED = True
SYNC_INTERVAL_SECONDS = 60
SYNC_TIMEOUT_SECONDS = 10


def build_ssl_context():
    """
    Crea un contexto SSL usando el paquete certifi.
    Esto corrige CERTIFICATE_VERIFY_FAILED en Android/Buildozer
    sin desactivar la verificación de seguridad.
    """
    try:
        return ssl.create_default_context(cafile=certifi.where())
    except Exception as error:
        print("ADVERTENCIA SSL CONTEXT:", error)
        return ssl.create_default_context()


SSL_CONTEXT = build_ssl_context()


# ============================================================
# MEMORIA DE LA APP
# ============================================================

CLIENTES = []
TRANSACCIONES = []
MOVIMIENTOS_CAJA = []


# ============================================================
# UTILIDADES
# ============================================================

def today_text():
    return datetime.now().strftime("%d/%m/%Y")


def now_text():
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def iso_today():
    return datetime.now().strftime("%Y-%m-%d")


def display_date_from_iso(value):
    try:
        if not value:
            return "No definido"
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return "No definido"


def record_date_iso(value):
    """Convierte fechas de la app a YYYY-MM-DD."""
    value = str(value or "").strip()

    for date_format in (
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(
                value,
                date_format,
            ).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return ""


def records_for_date(records, date_iso=None):
    date_iso = date_iso or iso_today()

    return [
        record
        for record in records
        if record_date_iso(
            record.get("fecha", "")
        ) == date_iso
    ]


def cash_balance_before_date(date_iso=None):
    """
    Calcula el saldo acumulado antes de comenzar el día.
    Ese valor se usa como caja inicial.
    """
    date_iso = date_iso or iso_today()

    ingresos = sum(
        int(movement.get("valor", 0))
        for movement in MOVIMIENTOS_CAJA
        if movement.get("tipo") == "Ingreso"
        and record_date_iso(
            movement.get("fecha", "")
        ) < date_iso
    )

    egresos = sum(
        int(movement.get("valor", 0))
        for movement in MOVIMIENTOS_CAJA
        if movement.get("tipo") == "Egreso"
        and record_date_iso(
            movement.get("fecha", "")
        ) < date_iso
    )

    recaudos = sum(
        int(transaction.get("valor", 0))
        for transaction in TRANSACCIONES
        if transaction.get("tipo") in (
            "Cuota",
            "Aporte",
        )
        and record_date_iso(
            transaction.get("fecha", "")
        ) < date_iso
    )

    return ingresos + recaudos - egresos


def daily_metrics(date_iso=None):
    """
    Calcula únicamente la actividad de una fecha.
    Evita mezclar el recaudo de ayer con el de hoy.
    """
    date_iso = date_iso or iso_today()

    transactions = records_for_date(
        TRANSACCIONES,
        date_iso,
    )
    movements = records_for_date(
        MOVIMIENTOS_CAJA,
        date_iso,
    )

    payments = [
        transaction
        for transaction in transactions
        if transaction.get("tipo") in (
            "Cuota",
            "Aporte",
        )
    ]

    no_payments = [
        transaction
        for transaction in transactions
        if transaction.get("tipo") == "No Pago"
    ]

    postponed = [
        transaction
        for transaction in transactions
        if transaction.get("tipo") == "Siguiente Día"
    ]

    income = sum(
        int(movement.get("valor", 0))
        for movement in movements
        if movement.get("tipo") == "Ingreso"
    )

    expenses = sum(
        int(movement.get("valor", 0))
        for movement in movements
        if movement.get("tipo") == "Egreso"
    )

    collected = sum(
        int(transaction.get("valor", 0))
        for transaction in payments
    )

    opening_cash = cash_balance_before_date(date_iso)
    closing_cash = (
        opening_cash
        + income
        + collected
        - expenses
    )

    new_clients = [
        client
        for client in CLIENTES
        if record_date_iso(
            client.get("created_at", "")
        ) == date_iso
    ]

    expected = sum(
        int(client.get("cuota", 0))
        for client in CLIENTES
        if (
            client.get("estado") != "paz_y_salvo"
            and int(client.get("pendientes", 0)) > 0
            and (
                not client.get("proximo_cobro")
                or client.get("proximo_cobro") <= date_iso
            )
        )
    )

    return {
        "date_iso": date_iso,
        "transactions": transactions,
        "movements": movements,
        "payments": payments,
        "no_payments": no_payments,
        "postponed": postponed,
        "new_clients": new_clients,
        "income": income,
        "expenses": expenses,
        "collected": collected,
        "opening_cash": opening_cash,
        "closing_cash": closing_cash,
        "expected": expected,
    }




def _client_id_from_record(record):
    """Identificador estable para contar clientes únicos en reportes."""
    cid = safe_int(record.get("cliente_id", 0))
    if cid:
        return f"id:{cid}"
    nombre = str(record.get("cliente", "") or "").strip().lower()
    return f"nombre:{nombre}" if nombre else ""


def productivity_metrics(date_iso=None):
    """
    Reporte profesional de productividad del cobrador.

    Visitados: clientes con gestión registrada hoy:
    cuota, aporte, no pago o reprogramación.
    """
    date_iso = date_iso or iso_today()
    metrics = daily_metrics(date_iso)
    transactions = metrics["transactions"]

    paid_records = [
        tx for tx in transactions
        if str(tx.get("tipo", "") or "") in ("Cuota", "Aporte")
        and safe_int(tx.get("valor", 0)) > 0
    ]
    no_payment_records = [
        tx for tx in transactions
        if str(tx.get("tipo", "") or "") == "No Pago"
    ]
    rescheduled_records = [
        tx for tx in transactions
        if str(tx.get("tipo", "") or "") == "Siguiente Día"
        or "reprogram" in str(tx.get("observacion", "") or "").lower()
        or "aplaz" in str(tx.get("observacion", "") or "").lower()
    ]

    visited_ids = {
        _client_id_from_record(tx)
        for tx in paid_records + no_payment_records + rescheduled_records
        if _client_id_from_record(tx)
    }
    paid_ids = {
        _client_id_from_record(tx)
        for tx in paid_records
        if _client_id_from_record(tx)
    }
    no_payment_ids = {
        _client_id_from_record(tx)
        for tx in no_payment_records
        if _client_id_from_record(tx)
    }
    rescheduled_ids = {
        _client_id_from_record(tx)
        for tx in rescheduled_records
        if _client_id_from_record(tx)
    }

    visited = len(visited_ids)
    paid = len(paid_ids)
    no_paid = len(no_payment_ids)
    rescheduled = len(rescheduled_ids)
    effectiveness = round((paid / visited) * 100) if visited else 0

    collected = metrics["collected"]
    expected = metrics["expected"]
    gap = collected - expected

    if visited == 0:
        verdict = "Sin gestiones registradas hoy"
    elif effectiveness >= 80:
        verdict = "Día muy productivo"
    elif effectiveness >= 60:
        verdict = "Día aceptable"
    else:
        verdict = "Día con baja efectividad"

    return {
        "visited": visited,
        "paid": paid,
        "no_paid": no_paid,
        "rescheduled": rescheduled,
        "effectiveness": effectiveness,
        "collected": collected,
        "expected": expected,
        "gap": gap,
        "verdict": verdict,
    }


def risk_distribution(clients=None):
    """Conteo automático de clientes por nivel de riesgo."""
    clients = clients if clients is not None else CLIENTES
    result = {
        "alto": 0,
        "medio": 0,
        "bajo": 0,
    }

    for cliente in clients:
        if safe_int(cliente.get("saldo", 0)) <= 0 or safe_int(cliente.get("pendientes", 0)) <= 0:
            continue
        riesgo = str(client_risk_profile(cliente).get("nivel", "Bajo") or "Bajo").lower()
        if riesgo in result:
            result[riesgo] += 1
        else:
            result["bajo"] += 1

    return result




def weekly_managerial_metrics(date_iso=None):
    """
    Indicadores gerenciales de la semana actual.

    Permite saber si el negocio está creciendo, cumpliendo recaudo
    o acumulando cartera pendiente.
    """
    date_iso = date_iso or iso_today()
    start_iso, end_iso = week_bounds(date_iso)
    week = weekly_metrics(date_iso)

    active_clients = [
        client for client in CLIENTES
        if safe_int(client.get("saldo", 0)) > 0
        and safe_int(client.get("pendientes", 0)) > 0
        and str(client.get("estado", "") or "") != "paz_y_salvo"
    ]

    expected_week = sum(
        safe_int(client.get("cuota", 0))
        for client in active_clients
        if (
            not str(client.get("proximo_cobro", "") or "").strip()
            or str(client.get("proximo_cobro", "") or "")[:10] <= end_iso
        )
    )

    collected_week = safe_int(week.get("collected", 0))
    difference = collected_week - expected_week
    outstanding_portfolio = sum(
        safe_int(client.get("saldo", 0))
        for client in active_clients
    )

    no_payments_count = len(week.get("no_payments", []))

    delivered_movements = [
        movement for movement in week.get("movements", [])
        if movement.get("tipo") == "Egreso"
        and (
            "desembolso" in str(movement.get("concepto", "") or "").lower()
            or "renovación" in str(movement.get("concepto", "") or "").lower()
            or "renovacion" in str(movement.get("concepto", "") or "").lower()
            or "préstamo" in str(movement.get("concepto", "") or "").lower()
            or "prestamo" in str(movement.get("concepto", "") or "").lower()
        )
    ]

    new_loans_delivered = sum(
        safe_int(movement.get("valor", 0))
        for movement in delivered_movements
    )

    # Utilidad estimada: intereses potenciales de préstamos nuevos/renovados
    # que están activos en la semana. No es utilidad contable final, sino
    # una referencia gerencial para ver crecimiento del negocio.
    delivered_client_ids = set()
    for tx in week.get("transactions", []):
        tipo = str(tx.get("tipo", "") or "").lower()
        if "renov" in tipo:
            cid = safe_int(tx.get("cliente_id", 0))
            if cid:
                delivered_client_ids.add(cid)

    for client in week.get("new_clients", []):
        cid = safe_int(client.get("id", 0))
        if cid:
            delivered_client_ids.add(cid)

    estimated_profit = 0
    for client in CLIENTES:
        cid = safe_int(client.get("id", 0))
        if cid in delivered_client_ids:
            estimated_profit += max(
                safe_int(client.get("total_credito", 0))
                - safe_int(client.get("valor_credito", 0)),
                0,
            )

    if difference >= 0 and no_payments_count <= 2:
        diagnosis = "Semana controlada"
    elif difference < 0 and no_payments_count <= 5:
        diagnosis = "Semana para seguimiento"
    else:
        diagnosis = "Semana con riesgo operativo"

    return {
        "start_iso": start_iso,
        "end_iso": end_iso,
        "expected_week": expected_week,
        "collected_week": collected_week,
        "difference": difference,
        "outstanding_portfolio": outstanding_portfolio,
        "no_payments_count": no_payments_count,
        "new_loans_delivered": new_loans_delivered,
        "estimated_profit": estimated_profit,
        "diagnosis": diagnosis,
    }


def renewal_intelligence(cliente):
    """
    Recomendación operativa de renovación:
    - Apto para renovar
    - Renovar con mismo monto
    - Renovar con menor monto
    - No renovar
    """
    status = cobranza_estado_profesional(cliente)
    behavior = client_behavior_summary(cliente, status)

    saldo = safe_int(cliente.get("saldo", 0))
    pendientes = safe_int(cliente.get("pendientes", 0))
    base_credit = safe_int(cliente.get("valor_credito", 0))
    total_credit = safe_int(cliente.get("total_credito", 0))
    no_pagos = safe_int(behavior.get("no_pagos", 0))
    aplazamientos = safe_int(behavior.get("aplazamientos", 0))
    pagos = safe_int(behavior.get("pagos", 0))
    riesgo = str(behavior.get("riesgo", "Bajo") or "Bajo").lower()
    dias = safe_int(status.get("dias_atraso", 0))

    finished = saldo <= 0 or pendientes <= 0 or str(cliente.get("estado", "") or "") == "paz_y_salvo"

    if not finished:
        return {
            "estado": "NO EVALUABLE",
            "decision": "Crédito activo",
            "apto": False,
            "monto_sugerido": 0,
            "motivo": "El crédito aún tiene saldo o cuotas pendientes.",
            "color": MUTED,
        }

    if riesgo == "alto" or no_pagos >= 4 or dias >= 7:
        return {
            "estado": "NO RENOVAR",
            "decision": "No renovar",
            "apto": False,
            "monto_sugerido": 0,
            "motivo": "Cliente con riesgo alto, varios no pagos o vencimiento fuerte.",
            "color": DARK,
        }

    if no_pagos >= 2 or aplazamientos >= 3 or riesgo == "medio":
        suggested = max(round((base_credit * 0.75) / 1000) * 1000, 0)
        if suggested <= 0:
            suggested = base_credit
        return {
            "estado": "RENOVAR CON MENOR MONTO",
            "decision": "Renovar con menor monto",
            "apto": True,
            "monto_sugerido": suggested,
            "motivo": "El cliente terminó, pero tuvo señales de riesgo. Conviene reducir cupo.",
            "color": DANGER,
        }

    if pagos >= 3 and no_pagos == 0:
        suggested = round((base_credit * 1.2) / 1000) * 1000
        if suggested <= 0:
            suggested = base_credit or total_credit
        return {
            "estado": "APTO PARA RENOVAR",
            "decision": "Apto para renovar",
            "apto": True,
            "monto_sugerido": suggested,
            "motivo": "Buen comportamiento de pago. Puede considerar aumento moderado.",
            "color": SUCCESS,
        }

    return {
        "estado": "RENOVAR CON MISMO MONTO",
        "decision": "Renovar con mismo monto",
        "apto": True,
        "monto_sugerido": max(base_credit, 0),
        "motivo": "Cliente finalizó el crédito. Mantener el cupo actual.",
        "color": GOLD,
    }

def week_bounds(date_iso=None):
    """Retorna lunes y domingo de la semana en formato ISO."""
    date_iso = date_iso or iso_today()
    base_date = datetime.strptime(date_iso, "%Y-%m-%d").date()
    monday = base_date - timedelta(days=base_date.weekday())
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


def display_week_range(date_iso=None):
    start_iso, end_iso = week_bounds(date_iso)
    start_date = datetime.strptime(start_iso, "%Y-%m-%d")
    end_date = datetime.strptime(end_iso, "%Y-%m-%d")
    return f"{start_date.strftime('%d/%m/%Y')} al {end_date.strftime('%d/%m/%Y')}"


def records_for_period(records, start_iso, end_iso):
    return [
        record
        for record in records
        if start_iso <= record_date_iso(record.get("fecha", "")) <= end_iso
    ]


def weekly_metrics(date_iso=None):
    """Calcula cobros y movimientos de lunes a domingo."""
    start_iso, end_iso = week_bounds(date_iso)
    transactions = records_for_period(TRANSACCIONES, start_iso, end_iso)
    movements = records_for_period(MOVIMIENTOS_CAJA, start_iso, end_iso)

    payments = [
        transaction for transaction in transactions
        if transaction.get("tipo") in ("Cuota", "Aporte")
    ]
    no_payments = [
        transaction for transaction in transactions
        if transaction.get("tipo") == "No Pago"
    ]
    postponed = [
        transaction for transaction in transactions
        if transaction.get("tipo") == "Siguiente Día"
    ]

    income = sum(
        int(movement.get("valor", 0))
        for movement in movements
        if movement.get("tipo") == "Ingreso"
    )
    expenses = sum(
        int(movement.get("valor", 0))
        for movement in movements
        if movement.get("tipo") == "Egreso"
    )
    collected = sum(int(transaction.get("valor", 0)) for transaction in payments)
    closure = get_cash_closure(date_iso)
    if closure and closure.get("estado") in ("abierta", "cerrada"):
        opening_cash = int(closure.get("caja_inicial", 0) or 0)
    else:
        opening_cash = cash_balance_before_date(start_iso)
    closing_cash = opening_cash + income + collected - expenses

    new_clients = [
        client for client in CLIENTES
        if start_iso <= record_date_iso(client.get("created_at", "")) <= end_iso
    ]
    active_clients = [
        client for client in CLIENTES
        if int(client.get("saldo", 0)) > 0 and int(client.get("pendientes", 0)) > 0
    ]
    outstanding_portfolio = sum(int(client.get("saldo", 0)) for client in active_clients)
    disbursements = sum(
        int(movement.get("valor", 0))
        for movement in movements
        if movement.get("tipo") == "Egreso"
        and str(movement.get("concepto", "")).strip().lower() == "desembolso préstamo"
    )

    return {
        "start_iso": start_iso,
        "end_iso": end_iso,
        "transactions": transactions,
        "movements": movements,
        "payments": payments,
        "no_payments": no_payments,
        "postponed": postponed,
        "new_clients": new_clients,
        "income": income,
        "expenses": expenses,
        "collected": collected,
        "opening_cash": opening_cash,
        "closing_cash": closing_cash,
        "active_clients": len(active_clients),
        "outstanding_portfolio": outstanding_portfolio,
        "disbursements": disbursements,
    }


def next_due_date(cobro):
    """
    Calcula la próxima fecha de cobro.
    Diario: mañana.
    Semanal: dentro de 7 días.
    Quincenal: dentro de 15 días.
    Mensual: dentro de 30 días.
    """
    today = datetime.now().date()
    cobro = (cobro or "Diario").strip().lower()

    if cobro == "semanal":
        delta = 7
    elif cobro == "quincenal":
        delta = 15
    elif cobro == "mensual":
        delta = 30
    else:
        delta = 1

    return (today + timedelta(days=delta)).strftime("%Y-%m-%d")



def frequency_days(cobro):
    cobro = (cobro or "Diario").strip().lower()
    if cobro == "semanal":
        return 7
    if cobro == "quincenal":
        return 15
    if cobro == "mensual":
        return 30
    return 1


def next_due_date_for_installments(cobro, installments=1):
    installments = max(int(installments or 1), 1)
    delta = frequency_days(cobro) * installments
    return (datetime.now().date() + timedelta(days=delta)).strftime("%Y-%m-%d")


def add_calendar_months(base_date, months=1):
    """
    Suma meses calendario conservando el día cuando sea posible.
    Ejemplo: 09/06/2026 + 1 mes = 09/07/2026.
    Si el día no existe en el mes destino, usa el último día del mes.
    """
    months = max(int(months or 1), 1)
    month_index = (base_date.month - 1) + months
    year = base_date.year + (month_index // 12)
    month = (month_index % 12) + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(base_date.day, last_day)

    return base_date.replace(year=year, month=month, day=day)


def next_due_from_anchor(anchor_value, cobro, installments=1):
    """
    Calcula la próxima fecha tomando como base el cronograma guardado.

    Si la próxima fecha fue editada manualmente, esa fecha se convierte en
    la nueva base. Ejemplo semanal:
    09/06 -> 16/06 -> 23/06 -> 30/06.

    Para varias cuotas, avanza varios periodos.
    """
    installments = max(int(installments or 1), 1)

    anchor_text = str(anchor_value or "").strip()
    anchor_date = None

    for date_format in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            anchor_date = datetime.strptime(anchor_text, date_format).date()
            break
        except ValueError:
            continue

    if anchor_date is None:
        anchor_date = datetime.now().date()

    frequency = (cobro or "Diario").strip().lower()

    if frequency == "mensual":
        result = add_calendar_months(anchor_date, installments)
    elif frequency == "semanal":
        result = anchor_date + timedelta(days=7 * installments)
    elif frequency == "quincenal":
        result = anchor_date + timedelta(days=15 * installments)
    else:
        result = anchor_date + timedelta(days=installments)

    return result.strftime("%Y-%m-%d")


def next_visit_after_payment(anchor_value, cobro, installments=1):
    """
    Avanza el cronograma después de un pago y garantiza que la nueva visita
    quede en una fecha futura. Evita que un cliente vencido siga apareciendo
    en la lista inmediatamente después de pagar.
    """
    result_text = next_due_from_anchor(
        anchor_value,
        cobro,
        installments,
    )

    try:
        result_date = datetime.strptime(
            result_text,
            "%Y-%m-%d",
        ).date()
    except Exception:
        result_date = datetime.now().date()

    today = datetime.now().date()
    frequency = (cobro or "Diario").strip().lower()

    while result_date <= today:
        if frequency == "mensual":
            result_date = add_calendar_months(result_date, 1)
        elif frequency == "semanal":
            result_date += timedelta(days=7)
        elif frequency == "quincenal":
            result_date += timedelta(days=15)
        else:
            result_date += timedelta(days=1)

    return result_date.strftime("%Y-%m-%d")


def default_rescheduled_visit():
    """Fecha sugerida para volver a visitar a quien no pagó: mañana."""
    return (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")


def normalize_date_input(value):
    """
    Acepta DD/MM/YYYY o YYYY-MM-DD y devuelve YYYY-MM-DD.
    """
    value = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_app_datetime(value):
    value = str(value or "").strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def projected_end_date(cliente):
    created = parse_app_datetime(cliente.get("created_at"))
    if not created:
        return "No disponible"

    periods = max(int(cliente.get("numero_cuotas") or 0), 0)
    if periods <= 0:
        return "No disponible"

    end_date = created.date() + timedelta(
        days=frequency_days(cliente.get("cobro", "Diario")) * periods
    )
    return end_date.strftime("%d/%m/%Y")


def actual_or_projected_end_date(cliente, transactions):
    if int(cliente.get("saldo") or 0) <= 0 and transactions:
        last_date = parse_app_datetime(transactions[-1].get("fecha"))
        if last_date:
            return f"{last_date.strftime('%d/%m/%Y')} (final real)"
    return f"{projected_end_date(cliente)} (estimada)"

def normalize_client_name(value):
    """
    Normaliza un nombre para comparar duplicados:
    - ignora mayúsculas/minúsculas;
    - elimina espacios repetidos;
    - elimina espacios al inicio y final.
    """
    return " ".join(str(value or "").strip().upper().split())


def client_name_exists(name, exclude_client_id=None):
    """
    Retorna True si ya existe otro cliente con el mismo nombre normalizado.
    """
    normalized = normalize_client_name(name)

    if not normalized:
        return False

    conn = get_connection()
    cursor = conn.cursor()

    if exclude_client_id is None:
        cursor.execute(
            "SELECT id, nombre FROM clientes"
        )
    else:
        cursor.execute(
            "SELECT id, nombre FROM clientes WHERE id <> ?",
            (int(exclude_client_id),),
        )

    exists = any(
        normalize_client_name(row[1]) == normalized
        for row in cursor.fetchall()
    )

    conn.close()
    return exists


def detach_widget(widget):
    """
    Evita el cierre de la app cuando se vuelve a la pantalla Nuevo.
    Kivy no permite agregar el mismo TextInput a dos padres distintos.
    Si el campo ya tenía padre, se separa antes de volver a usarlo.
    """
    try:
        if widget is not None and widget.parent is not None:
            widget.parent.remove_widget(widget)
    except Exception:
        pass


def money(value):
    try:
        value = int(float(value or 0))
    except Exception:
        value = 0
    return "$ {:,.0f}".format(value).replace(",", ".")


def business_name():
    try:
        return get_config_value("nombre_negocio", globals().get("BUSINESS_NAME", "COBROS V12 MOBILE"))
    except Exception:
        return globals().get("BUSINESS_NAME", "COBROS V12 MOBILE")


def configured_collector_name():
    try:
        return get_config_value("nombre_cobrador", cobrador_nombre())
    except Exception:
        return cobrador_nombre()


def client_matches_quick_filter(cliente, quick_filter, query=""):
    """Filtro operativo rápido para lista principal."""
    quick_filter = quick_filter or "Pendientes"
    query = (query or "").strip().lower()
    today = iso_today()

    saldo = safe_int(cliente.get("saldo", 0))
    pendientes = safe_int(cliente.get("pendientes", 0))
    estado = str(cliente.get("estado", "") or "")
    status = cobranza_estado_profesional(cliente)
    codigo = str(status.get("codigo", "") or "")
    no_pagos = client_no_payment_count(cliente)
    riesgo = str(client_risk_profile(cliente, status).get("nivel", "Bajo") or "Bajo").lower()

    if query:
        base_match = (
            query in str(cliente.get("nombre", "") or "").lower()
            or query in str(cliente.get("telefono", "") or "").lower()
            or query in str(cliente.get("documento", "") or "").lower()
            or query in str(cliente.get("barrio", "") or "").lower()
            or query in str(cliente.get("ruta", "") or "").lower()
            or query in str(cliente.get("zona", "") or "").lower()
        )
        if not base_match and quick_filter not in ("Por barrio", "Por ruta"):
            return False

    if quick_filter == "Todos":
        return True

    if quick_filter == "Pendientes":
        return (
            estado not in ("pagado", "paz_y_salvo")
            and pendientes > 0
            and saldo > 0
            and (
                not cliente.get("proximo_cobro")
                or str(cliente.get("proximo_cobro", ""))[:10] <= today
            )
        )

    if quick_filter == "Vencidos":
        return "vencido" in codigo

    if quick_filter == "Para hoy":
        return str(cliente.get("proximo_cobro", "") or "")[:10] == today and saldo > 0 and pendientes > 0

    if quick_filter == "No pagaron":
        return no_pagos > 0 or "no_pago" in codigo

    if quick_filter == "Alto riesgo":
        return riesgo == "alto"

    if quick_filter == "Pagaron hoy":
        return latest_payment_today_for_client(cliente) is not None

    if quick_filter == "Por barrio":
        return bool(query) and query in str(cliente.get("barrio", "") or "").lower()

    if quick_filter == "Por ruta":
        return bool(query) and query in str(cliente.get("ruta", "") or "").lower()

    return True


def client_code(cliente):
    """
    Código visual único del cliente.
    Se basa en el ID local para evitar duplicados y facilitar verificación.
    """
    try:
        cid = int(cliente.get("id") or 0)
    except Exception:
        cid = 0

    if cid > 0:
        return f"CLI-{cid:04d}"

    documento = "".join(ch for ch in str(cliente.get("documento", "") or "") if ch.isdigit())
    if documento:
        return f"CLI-{documento[-4:].zfill(4)}"

    return "CLI-0000"



def cobrador_nombre():
    return globals().get("COBRADOR_NOMBRE", "PACHO")


def latest_payment_today_for_client(cliente):
    """
    Retorna el último pago/aporte registrado hoy para el cliente.
    Sirve para bloquear doble pago accidental.
    """
    try:
        cid = int(cliente.get("id") or 0)
    except Exception:
        cid = 0

    nombre = str(cliente.get("nombre", "") or "").strip().lower()
    today = iso_today()
    matches = []

    for tx in TRANSACCIONES:
        tipo = str(tx.get("tipo", "") or "")
        if tipo not in ("Cuota", "Aporte"):
            continue

        if record_date_iso(tx.get("fecha", "")) != today:
            continue

        tx_cid = safe_int(tx.get("cliente_id", 0))
        tx_nombre = str(tx.get("cliente", "") or "").strip().lower()
        same_client = (cid and tx_cid == cid) or (nombre and tx_nombre == nombre)

        if same_client:
            matches.append(tx)

    matches.sort(key=lambda item: int(item.get("id") or 0))
    return matches[-1] if matches else None


def receipt_text(receipt):
    """Texto profesional del comprobante para copiar o compartir."""
    receipt_number = str(receipt.get("tx_id") or "").zfill(6)
    return (
        f"COMPROBANTE DE PAGO - {business_name()}\n"
        f"No. comprobante: CP-{receipt_number}\n"
        f"Cliente: {receipt.get('cliente', '')}\n"
        f"Código cliente: {receipt.get('codigo', '')}\n"
        f"Fecha y hora: {receipt.get('fecha', '')}\n"
        f"Tipo: {receipt.get('tipo', '')}\n"
        f"Valor pagado: {money(receipt.get('valor', 0))}\n"
        f"Saldo anterior: {money(receipt.get('saldo_anterior', 0))}\n"
        f"Saldo nuevo: {money(receipt.get('saldo_nuevo', 0))}\n"
        f"Cuotas pagadas: {receipt.get('cuotas_pagadas', 0)}\n"
        f"Cuotas pendientes: {receipt.get('cuotas_pendientes', 0)}\n"
        f"Cobrador: {receipt.get('cobrador', cobrador_nombre())}"
    )


def generate_payment_receipt_pdf(receipt):
    """Genera un PDF de comprobante con presentación más comercial."""
    filename = (
        f"comprobante_{receipt.get('codigo', 'cliente')}_"
        f"{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.pdf"
    )
    output_path = get_exports_dir() / filename
    pdf = ProfessionalPDF(output_path)

    receipt_number = str(receipt.get("tx_id") or datetime.now().strftime("%H%M%S")).zfill(6)

    pdf.section("Comprobante de pago")
    pdf.key_grid([
        ("Negocio", business_name(), False),
        ("No. comprobante", f"CP-{receipt_number}", True),
        ("Cliente", str(receipt.get("cliente", "")), False),
        ("Código cliente", str(receipt.get("codigo", "")), False),
        ("Fecha y hora", str(receipt.get("fecha", "")), False),
        ("Cobrador", str(receipt.get("cobrador", cobrador_nombre())), False),
    ])

    pdf.section("Datos del pago")
    pdf.key_grid([
        ("Tipo de movimiento", str(receipt.get("tipo", "")), False),
        ("Valor pagado", money(receipt.get("valor", 0)), True),
        ("Saldo anterior", money(receipt.get("saldo_anterior", 0)), False),
        ("Saldo nuevo", money(receipt.get("saldo_nuevo", 0)), True),
        ("Cuotas pagadas", str(receipt.get("cuotas_pagadas", 0)), False),
        ("Cuotas pendientes", str(receipt.get("cuotas_pendientes", 0)), False),
    ])

    pdf.section("Mensaje")
    pdf.paragraph(
        "Gracias por su pago. Conserve este comprobante como soporte del movimiento registrado."
    )
    pdf.paragraph(
        "El saldo y las cuotas pendientes corresponden al estado del credito despues de guardar el pago."
    )
    return pdf.save()


def share_text_android(message):
    """Comparte texto en Android, preferiblemente con WhatsApp si está instalado."""
    if platform != "android":
        return False, "Compartir directamente solo está disponible en Android."

    try:
        from importlib import import_module

        autoclass = import_module("jnius").autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")

        activity = PythonActivity.mActivity

        intent = Intent()
        intent.setAction(Intent.ACTION_SEND)
        intent.setType("text/plain")
        intent.putExtra(Intent.EXTRA_TEXT, message)

        try:
            intent.setPackage("com.whatsapp")
            activity.startActivity(intent)
        except Exception:
            intent.setPackage(None)
            chooser = Intent.createChooser(intent, "Compartir comprobante")
            activity.startActivity(chooser)

        return True, "Compartir abierto."
    except Exception as error:
        return False, str(error)


def format_thousands(value):
    """
    Devuelve números con separador de miles colombiano:
    500000 -> 500.000
    """
    try:
        value = int(float(value or 0))
    except Exception:
        value = 0
    return "{:,.0f}".format(value).replace(",", ".")


def to_int(value, default=0):
    try:
        clean = str(value or "").replace("$", "").replace(".", "").replace(",", "").strip()
        if clean == "":
            return default
        return int(float(clean))
    except Exception:
        return default


def to_float(value, default=0.0):
    try:
        clean = str(value or "").replace("%", "").replace(",", ".").strip()
        if clean == "":
            return default
        return float(clean)
    except Exception:
        return default


def asset_path(filename):
    base_dir = Path(__file__).resolve().parent
    candidates = [
        base_dir / "assets" / filename,
        Path(os.getcwd()) / "assets" / filename,
        base_dir / filename,
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return ""


def safe_pdf_text(value):
    text = str(value or "")
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U",
        "ñ": "n", "Ñ": "N",
        "–": "-", "—": "-", "“": '"', "”": '"',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def get_exports_dir():
    if platform in ("android", "ios"):
        try:
            app = App.get_running_app()
            if app and getattr(app, "user_data_dir", None):
                path = Path(app.user_data_dir) / "reportes"
                path.mkdir(parents=True, exist_ok=True)
                return path
        except Exception:
            pass

    path = Path(__file__).resolve().parent / "reportes"
    path.mkdir(parents=True, exist_ok=True)
    return path



def open_pdf_file(pdf_reference):
    """
    Abre el PDF con el visor predeterminado.

    Android:
    usa directamente ACTION_VIEW sobre un content:// URI de MediaStore.
    No utiliza Intent.createChooser para evitar incompatibilidades
    de firmas entre PyJNIus y Android.
    """
    try:
        if platform == "android":
            from importlib import import_module

            autoclass = import_module("jnius").autoclass

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            ActivityNotFoundException = autoclass(
                "android.content.ActivityNotFoundException"
            )

            activity = PythonActivity.mActivity

            uri = (
                pdf_reference
                if hasattr(pdf_reference, "getScheme")
                else Uri.parse(str(pdf_reference))
            )

            intent = Intent()
            intent.setAction(Intent.ACTION_VIEW)
            intent.setDataAndType(uri, "application/pdf")
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

            try:
                activity.startActivity(intent)
                return True, "PDF abierto correctamente."
            except ActivityNotFoundException:
                return (
                    False,
                    "No hay una aplicación instalada para abrir archivos PDF."
                )

        if os.name == "nt":
            os.startfile(str(pdf_reference))
            return True, "PDF abierto correctamente."

        import subprocess

        command = (
            ["open", str(pdf_reference)]
            if platform == "macosx"
            else ["xdg-open", str(pdf_reference)]
        )
        subprocess.Popen(command)
        return True, "PDF abierto correctamente."

    except Exception as error:
        return False, str(error)



def publish_pdf_to_downloads(pdf_path, open_after=True):
    """
    Publica el PDF en Descargas/CobrosV12 mediante MediaStore.

    La copia se ejecuta completamente en Java usando FileChannel.transferTo,
    evitando conversiones Python -> byte[] que fallan en algunos Android.
    """
    source = Path(pdf_path)

    if platform != "android":
        open_ok = False
        open_message = "PDF guardado."

        if open_after:
            open_ok, open_message = open_pdf_file(str(source))

        return str(source), open_ok, open_message

    uri = None
    input_stream = None
    input_channel = None
    output_stream = None
    output_channel = None

    try:
        from importlib import import_module

        autoclass = import_module("jnius").autoclass

        PythonActivity = autoclass(
            "org.kivy.android.PythonActivity"
        )
        MediaStore = autoclass("android.provider.MediaStore")
        ContentValues = autoclass("android.content.ContentValues")
        BuildVersion = autoclass("android.os.Build$VERSION")
        Environment = autoclass("android.os.Environment")
        FileInputStream = autoclass("java.io.FileInputStream")
        Channels = autoclass("java.nio.channels.Channels")

        activity = PythonActivity.mActivity
        resolver = activity.getContentResolver()
        sdk_int = int(BuildVersion.SDK_INT)

        values = ContentValues()
        values.put(
            MediaStore.MediaColumns.DISPLAY_NAME,
            source.name,
        )
        values.put(
            MediaStore.MediaColumns.MIME_TYPE,
            "application/pdf",
        )

        if sdk_int >= 29:
            values.put(
                MediaStore.MediaColumns.RELATIVE_PATH,
                Environment.DIRECTORY_DOWNLOADS + "/CobrosV12",
            )
            values.put(
                MediaStore.MediaColumns.IS_PENDING,
                1,
            )
            collection_uri = (
                MediaStore.Downloads.EXTERNAL_CONTENT_URI
            )
        else:
            # Compatibilidad para Android 8 y 9.
            collection_uri = MediaStore.Files.getContentUri(
                "external"
            )

        uri = resolver.insert(collection_uri, values)

        if uri is None:
            raise RuntimeError(
                "Android no permitió crear el PDF en Descargas."
            )

        output_stream = resolver.openOutputStream(uri, "w")
        if output_stream is None:
            raise RuntimeError(
                "Android no permitió escribir el PDF en Descargas."
            )

        # Copia directa Java -> Java. No convierte el PDF a bytearray.
        input_stream = FileInputStream(str(source))
        input_channel = input_stream.getChannel()
        output_channel = Channels.newChannel(output_stream)

        total_size = input_channel.size()
        position = 0

        while position < total_size:
            copied = input_channel.transferTo(
                position,
                total_size - position,
                output_channel,
            )

            if copied <= 0:
                raise RuntimeError(
                    "La copia del PDF se interrumpió antes de terminar."
                )

            position += copied

        output_stream.flush()

        # Cerrar antes de marcar el archivo como terminado.
        if input_channel is not None:
            input_channel.close()
            input_channel = None
        if input_stream is not None:
            input_stream.close()
            input_stream = None
        if output_channel is not None:
            output_channel.close()
            output_channel = None
        if output_stream is not None:
            output_stream.close()
            output_stream = None

        if sdk_int >= 29:
            completed_values = ContentValues()
            completed_values.put(
                MediaStore.MediaColumns.IS_PENDING,
                0,
            )
            resolver.update(
                uri,
                completed_values,
                None,
                None,
            )

        display_path = "Descargas/CobrosV12/" + source.name

        if open_after:
            open_ok, open_message = open_pdf_file(uri)
        else:
            open_ok = False
            open_message = "PDF guardado sin abrir."

        return display_path, open_ok, open_message

    except Exception as error:
        # Cerrar recursos sin ocultar el error original.
        for resource in (
            input_channel,
            input_stream,
            output_channel,
            output_stream,
        ):
            try:
                if resource is not None:
                    resource.close()
            except Exception:
                pass

        # Eliminar el registro incompleto creado en MediaStore.
        try:
            if uri is not None:
                resolver.delete(uri, None, None)
        except Exception:
            pass

        error_detail = f"{type(error).__name__}: {error}"
        print(
            "ERROR EXPORTANDO PDF A DESCARGAS:",
            error_detail,
        )

        return (
            str(source),
            False,
            "El PDF se generó en el almacenamiento privado, "
            "pero Android no permitió copiarlo a Descargas. "
            f"Detalle técnico: {error_detail}",
        )



def shorten(value, max_len=34):
    text = str(value or "")
    return text if len(text) <= max_len else text[:max_len - 3] + "..."


class ProfessionalPDF:
    def __init__(self, output_path):
        self.output_path = Path(output_path)
        self.page_width = 595
        self.page_height = 842
        self.margin = 34
        self.pages = []
        self.commands = []
        self.page_no = 0
        self.new_page()

    def color(self, r, g, b):
        self.commands.append(f"{r:.3f} {g:.3f} {b:.3f} rg")
        self.commands.append(f"{r:.3f} {g:.3f} {b:.3f} RG")

    def rect(self, x, y, w, h, fill=True):
        self.commands.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re {'f' if fill else 'S'}")

    def line(self, x1, y1, x2, y2):
        self.commands.append(f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def text(self, x, y, text, size=10, bold=False, color=(0.10, 0.12, 0.16)):
        font = "F2" if bold else "F1"
        r, g, b = color
        txt = safe_pdf_text(text)
        self.commands.extend([
            "BT",
            f"{r:.3f} {g:.3f} {b:.3f} rg",
            f"/{font} {size} Tf",
            f"1 0 0 1 {x:.2f} {y:.2f} Tm",
            f"({txt}) Tj",
            "ET",
        ])

    def new_page(self):
        if self.commands:
            self.footer()
            self.pages.append("\n".join(self.commands))
        self.page_no += 1
        self.commands = []
        self.y = 800
        self.header()

    def header(self):
        self.color(0.117, 0.227, 0.541)
        self.rect(0, 774, self.page_width, 68, True)
        self.text(self.margin, 814, "COBROS V12", 20, True, (1, 1, 1))
        self.text(self.margin, 792, "Reporte profesional de cierre de caja", 10, False, (0.90, 0.94, 1))
        self.color(0.93, 0.69, 0.13)
        self.rect(self.page_width - 170, 796, 135, 26, True)
        self.text(self.page_width - 158, 805, today_text(), 10, True, (0.12, 0.14, 0.18))
        self.y = 752

    def footer(self):
        self.color(0.78, 0.81, 0.86)
        self.line(self.margin, 42, self.page_width - self.margin, 42)
        self.text(self.margin, 26, "Cobros V12 Mobile - Reporte de cierre", 8, False, (0.42, 0.46, 0.52))
        self.text(self.page_width - 95, 26, f"Pagina {self.page_no}", 8, False, (0.42, 0.46, 0.52))

    def ensure_space(self, height):
        if self.y - height < 62:
            self.new_page()

    def section(self, title):
        self.ensure_space(38)
        self.color(0.117, 0.227, 0.541)
        self.rect(self.margin, self.y - 22, self.page_width - 2 * self.margin, 24, True)
        self.text(self.margin + 10, self.y - 15, title.upper(), 11, True, (1, 1, 1))
        self.y -= 36

    def key_grid(self, items, columns=2):
        width = self.page_width - 2 * self.margin
        col_w = width / columns
        row_h = 36

        for i in range(0, len(items), columns):
            self.ensure_space(row_h + 4)
            row = items[i:i + columns]
            for j, item in enumerate(row):
                label, value, highlight = item
                x = self.margin + j * col_w
                y = self.y - row_h
                self.color(1.00, 0.95, 0.78) if highlight else self.color(0.96, 0.97, 0.99)
                self.rect(x, y, col_w - 6, row_h - 4, True)
                self.color(0.84, 0.87, 0.91)
                self.rect(x, y, col_w - 6, row_h - 4, False)
                self.text(x + 8, y + 20, label, 8, True, (0.42, 0.46, 0.52))
                self.text(x + 8, y + 7, value, 11, highlight, (0.10, 0.12, 0.16))
            self.y -= row_h
        self.y -= 8

    def table(self, headers, rows, col_widths):
        table_width = sum(col_widths)
        header_h = 22
        row_h = 20
        self.ensure_space(header_h + row_h + 10)

        y = self.y - header_h
        self.color(0.90, 0.93, 0.97)
        self.rect(self.margin, y, table_width, header_h, True)
        self.color(0.78, 0.81, 0.86)
        self.rect(self.margin, y, table_width, header_h, False)

        x = self.margin
        for h, w in zip(headers, col_widths):
            self.text(x + 4, y + 8, h, 8, True, (0.20, 0.24, 0.30))
            x += w
        self.y -= header_h

        if not rows:
            self.ensure_space(row_h)
            self.text(self.margin + 4, self.y - 14, "Sin registros para mostrar.", 9, False, (0.42, 0.46, 0.52))
            self.y -= row_h + 8
            return

        for idx, row in enumerate(rows):
            self.ensure_space(row_h + 4)
            y = self.y - row_h
            self.color(1, 1, 1) if idx % 2 == 0 else self.color(0.98, 0.99, 1)
            self.rect(self.margin, y, table_width, row_h, True)
            self.color(0.88, 0.90, 0.94)
            self.line(self.margin, y, self.margin + table_width, y)
            x = self.margin
            for value, w in zip(row, col_widths):
                self.text(x + 4, y + 7, value, 8, False, (0.10, 0.12, 0.16))
                x += w
            self.y -= row_h
        self.y -= 10

    def paragraph(self, text):
        self.ensure_space(20)
        self.text(self.margin, self.y - 10, text, 9, False, (0.42, 0.46, 0.52))
        self.y -= 20

    def save(self):
        if self.commands:
            self.footer()
            self.pages.append("\n".join(self.commands))
            self.commands = []

        objects = [
            "1 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
            "2 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj\n",
        ]

        page_refs = []
        next_obj = 3

        for content in self.pages:
            content_id = next_obj
            page_id = next_obj + 1
            next_obj += 2
            page_refs.append(f"{page_id} 0 R")
            content_bytes = content.encode("latin-1", errors="ignore")
            objects.append(f"{content_id} 0 obj\n<< /Length {len(content_bytes)} >>\nstream\n{content}\nendstream\nendobj\n")
            objects.append(
                f"{page_id} 0 obj\n"
                f"<< /Type /Page /Parent 999 0 R /MediaBox [0 0 {self.page_width} {self.page_height}] "
                f"/Resources << /Font << /F1 1 0 R /F2 2 0 R >> >> /Contents {content_id} 0 R >>\n"
                f"endobj\n"
            )

        pages_id = next_obj
        catalog_id = next_obj + 1
        objects = [obj.replace("999 0 R", f"{pages_id} 0 R") for obj in objects]
        objects.append(f"{pages_id} 0 obj\n<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>\nendobj\n")
        objects.append(f"{catalog_id} 0 obj\n<< /Type /Catalog /Pages {pages_id} 0 R >>\nendobj\n")

        pdf = "%PDF-1.4\n"
        offsets = [0]
        for obj in objects:
            offsets.append(len(pdf.encode("latin-1", errors="ignore")))
            pdf += obj

        xref_pos = len(pdf.encode("latin-1", errors="ignore"))
        total_objects = len(objects) + 1
        pdf += f"xref\n0 {total_objects}\n"
        pdf += "0000000000 65535 f \n"
        for offset in offsets[1:]:
            pdf += f"{offset:010d} 00000 n \n"
        pdf += f"trailer\n<< /Size {total_objects} /Root {catalog_id} 0 R >>\nstartxref\n{xref_pos}\n%%EOF"

        self.output_path.write_bytes(pdf.encode("latin-1", errors="ignore"))
        return str(self.output_path)


def generate_daily_pdf_report():
    refresh_memory_from_db()

    metrics = daily_metrics()

    total_clientes = len(CLIENTES)
    pagos = metrics["payments"]
    no_pagos = metrics["no_payments"]
    aplazados = metrics["postponed"]

    recaudo_dia = metrics["collected"]
    ingresos = metrics["income"]
    egresos = metrics["expenses"]
    recaudo_esperado = metrics["expected"]
    caja_inicial = metrics["opening_cash"]
    saldo_caja = metrics["closing_cash"]
    pendientes_sync = count_pending_sync()

    filename = f"cierre_caja_{datetime.now().strftime('%Y_%m_%d_%H_%M')}.pdf"
    output_path = get_exports_dir() / filename
    pdf = ProfessionalPDF(output_path)

    pdf.section("Resumen ejecutivo")
    pdf.key_grid([
        ("Fecha", today_text(), False),
        ("Cobrador", "PACHO", False),
        ("Clientes registrados", str(total_clientes), False),
        ("Pagos registrados", str(len(pagos)), False),
        ("Clientes no pago", str(len(no_pagos)), False),
        ("Aplazados", str(len(aplazados)), False),
        ("Caja inicial", money(caja_inicial), False),
        ("Recaudo esperado", money(recaudo_esperado), False),
        ("Recaudo del dia", money(recaudo_dia), True),
        ("Ingresos de caja", money(ingresos), False),
        ("Egresos de caja", money(egresos), False),
        ("Saldo final en caja", money(saldo_caja), True),
        ("Pendientes nube", str(pendientes_sync), False),
    ])

    pdf.section("Pagos y aportes registrados")
    pagos_rows = [[
        shorten(t.get("cliente", ""), 28),
        shorten(t.get("tipo", ""), 9),
        money(t.get("valor", 0)),
        t.get("metodo", ""),
        t.get("fecha", ""),
    ] for t in pagos[-80:]]
    pdf.table(["Cliente", "Tipo", "Valor", "Metodo", "Fecha"], pagos_rows, [180, 60, 80, 75, 95])

    pdf.section("Clientes no pago y aplazados")
    especiales = [c for c in CLIENTES if c.get("estado") in ("no_pago", "siguiente")]
    especiales_rows = []
    for c in especiales:
        prox = display_date_from_iso(c.get("proximo_cobro", "")) if "display_date_from_iso" in globals() else c.get("proximo_cobro", "")
        especiales_rows.append([
            shorten(c.get("nombre", ""), 28),
            estado_texto(c.get("estado", "pendiente")),
            money(c.get("saldo", 0)),
            prox,
        ])
    pdf.table(["Cliente", "Estado", "Saldo", "Prox. cobro"], especiales_rows, [210, 90, 90, 100])

    pdf.section("Movimientos de caja")
    mov_rows = [[
        shorten(m.get("tipo", ""), 8),
        shorten(m.get("concepto", ""), 26),
        money(m.get("valor", 0)),
        shorten(m.get("observaciones", ""), 24),
    ] for m in metrics["movements"][-80:]]
    pdf.table(["Tipo", "Concepto", "Valor", "Observacion"], mov_rows, [65, 180, 90, 155])

    pdf.section("Clientes activos")
    cliente_rows = [[
        shorten(c.get("nombre", ""), 26),
        money(c.get("cuota", 0)),
        money(c.get("saldo", 0)),
        estado_texto(c.get("estado", "pendiente")),
        c.get("cobro", "Diario"),
    ] for c in CLIENTES[-120:]]
    pdf.table(["Cliente", "Cuota", "Saldo", "Estado", "Cobro"], cliente_rows, [170, 75, 90, 80, 75])

    pdf.section("Observacion")
    pdf.paragraph("Este reporte resume la gestion diaria del cobrador, los recaudos, movimientos de caja y clientes con novedades.")
    pdf.paragraph("El archivo sirve como soporte administrativo del cierre de ruta.")

    return pdf.save()


def show_popup(title, message, height=240):
    content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(12))

    label = Label(
        text=message,
        color=WHITE,
        font_size="14sp",
        halign="center",
        valign="middle",
    )
    label.bind(size=lambda instance, value: setattr(instance, "text_size", value))

    btn = Button(
        text="Aceptar",
        background_normal="",
        background_color=BLUE,
        color=WHITE,
        bold=True,
        size_hint_y=None,
        height=dp(46),
    )

    content.add_widget(label)
    content.add_widget(btn)

    popup = Popup(
        title=title,
        content=content,
        size_hint=(0.88, None),
        height=dp(height),
        auto_dismiss=False,
    )

    btn.bind(on_release=popup.dismiss)
    popup.open()


def confirm_popup(title, message, on_confirm):
    content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(12))

    label = Label(
        text=message,
        color=WHITE,
        font_size="14sp",
        halign="center",
        valign="middle",
    )
    label.bind(size=lambda instance, value: setattr(instance, "text_size", value))

    buttons = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(46), spacing=dp(8))

    cancel = Button(
        text="Cancelar",
        background_normal="",
        background_color=(0.55, 0.58, 0.63, 1),
        color=WHITE,
        bold=True,
    )

    accept = Button(
        text="Confirmar",
        background_normal="",
        background_color=DANGER,
        color=WHITE,
        bold=True,
    )

    buttons.add_widget(cancel)
    buttons.add_widget(accept)

    content.add_widget(label)
    content.add_widget(buttons)

    popup = Popup(
        title=title,
        content=content,
        size_hint=(0.88, None),
        height=dp(245),
        auto_dismiss=False,
    )

    cancel.bind(on_release=popup.dismiss)

    def do_confirm(*_):
        popup.dismiss()
        on_confirm()

    accept.bind(on_release=do_confirm)
    popup.open()


def estado_texto(estado):
    if estado == "paz_y_salvo":
        return "PAZ Y SALVO"
    if estado == "pagado":
        return "PAGADO"
    if estado == "aporte":
        return "APORTE"
    if estado == "no_pago":
        return "NO PAGO"
    if estado == "siguiente":
        return "SIG. DIA"
    return "PENDIENTE"


def estado_colores(estado):
    if estado == "paz_y_salvo":
        return (
            STATUS_PAID_OFF,
            STATUS_BORDER_PAID_OFF,
            "PAZ Y SALVO",
        )
    if estado in ("pagado", "aporte"):
        return STATUS_GREEN, STATUS_BORDER_GREEN, estado_texto(estado)
    if estado == "no_pago":
        return STATUS_RED, STATUS_BORDER_RED, "NO PAGO"
    return STATUS_YELLOW, STATUS_BORDER_YELLOW, estado_texto(estado)


# ============================================================
# BASE DE DATOS SQLITE
# ============================================================

def get_db_path():
    """
    Ruta corregida:
    - En Android/iOS: directorio privado de la app.
    - En PC: junto a main.py dentro del proyecto app-cobros-v12-final.
    """
    if platform in ("android", "ios"):
        try:
            app = App.get_running_app()
            if app and getattr(app, "user_data_dir", None):
                db_dir = Path(app.user_data_dir)
                db_dir.mkdir(parents=True, exist_ok=True)
                return str(db_dir / "cobros_v12_pacho_admin_existente.db")
        except Exception:
            pass

    return str(Path(__file__).resolve().parent / "cobros_v12_pacho_admin_existente.db")


def get_connection():
    conn = sqlite3.connect(get_db_path())
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


DB_SCHEMA_VERSION = 9


def backup_database_before_migration():
    """
    Crea una copia local antes de aplicar migraciones.
    Evita pérdida de información si una actualización falla.
    """
    try:
        db_path = Path(get_db_path())
        if not db_path.exists():
            return

        backup_dir = db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now().strftime("%Y_%m_%d")
        backup_path = backup_dir / f"backup_pre_migracion_v{DB_SCHEMA_VERSION}_{today}.db"

        if not backup_path.exists():
            shutil.copy2(db_path, backup_path)
            print("BACKUP DB:", backup_path)
    except Exception as error:
        print("BACKUP DB ERROR:", error)


def ensure_uuid_values(cursor, table_name):
    """
    Garantiza UUID en tablas principales para futura sincronización multi-equipo.
    """
    try:
        if not column_exists(cursor, table_name, "uuid"):
            return

        cursor.execute(f"SELECT id FROM {table_name} WHERE uuid IS NULL OR uuid = ''")
        rows = cursor.fetchall()
        for row in rows:
            cursor.execute(
                f"UPDATE {table_name} SET uuid = ? WHERE id = ?",
                (str(uuid.uuid4()), row[0]),
            )
    except Exception as error:
        print("UUID MIGRATION ERROR:", table_name, error)


def set_db_meta(cursor, key, value):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        )
    """)
    cursor.execute("""
        INSERT INTO app_meta (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (str(key), str(value)))


def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return column_name in [row[1] for row in cursor.fetchall()]


def ensure_column(cursor, table_name, column_name, column_definition):
    if not column_exists(cursor, table_name, column_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def init_database():
    backup_database_before_migration()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento TEXT,
            nombre TEXT NOT NULL,
            telefono TEXT,
            direccion TEXT,
            barrio TEXT NOT NULL DEFAULT '',
            zona TEXT NOT NULL DEFAULT '',
            ruta TEXT NOT NULL DEFAULT '',
            orden_visita INTEGER NOT NULL DEFAULT 0,
            producto TEXT NOT NULL DEFAULT '5 - CREDITO EN EFECTIVO',
            valor_credito INTEGER NOT NULL DEFAULT 0,
            interes REAL NOT NULL DEFAULT 0,
            total_credito INTEGER NOT NULL DEFAULT 0,
            cuota INTEGER NOT NULL DEFAULT 0,
            numero_cuotas INTEGER NOT NULL DEFAULT 1,
            saldo INTEGER NOT NULL DEFAULT 0,
            pagadas INTEGER NOT NULL DEFAULT 0,
            pendientes INTEGER NOT NULL DEFAULT 0,
            cobro TEXT NOT NULL DEFAULT 'Diario',
            estado TEXT NOT NULL DEFAULT 'pendiente',
            ultimo_tipo TEXT NOT NULL DEFAULT 'Pendiente por cobrar',
            codeudor_documento TEXT,
            codeudor_nombre TEXT,
            codeudor_movil TEXT,
            valor_seguro INTEGER NOT NULL DEFAULT 0,
            beneficiario TEXT,
            obs_seguro TEXT,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            proximo_cobro TEXT,
            ultima_fecha_pago TEXT,
            aporte_acumulado INTEGER NOT NULL DEFAULT 0,
            synced INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Migración automática para bases viejas
    columns = [
        ("documento", "TEXT"),
        ("telefono", "TEXT"),
        ("direccion", "TEXT"),
        ("barrio", "TEXT NOT NULL DEFAULT ''"),
        ("zona", "TEXT NOT NULL DEFAULT ''"),
        ("ruta", "TEXT NOT NULL DEFAULT ''"),
        ("orden_visita", "INTEGER NOT NULL DEFAULT 0"),
        ("producto", "TEXT NOT NULL DEFAULT '5 - CREDITO EN EFECTIVO'"),
        ("valor_credito", "INTEGER NOT NULL DEFAULT 0"),
        ("interes", "REAL NOT NULL DEFAULT 0"),
        ("total_credito", "INTEGER NOT NULL DEFAULT 0"),
        ("cuota", "INTEGER NOT NULL DEFAULT 0"),
        ("numero_cuotas", "INTEGER NOT NULL DEFAULT 1"),
        ("saldo", "INTEGER NOT NULL DEFAULT 0"),
        ("pagadas", "INTEGER NOT NULL DEFAULT 0"),
        ("pendientes", "INTEGER NOT NULL DEFAULT 0"),
        ("cobro", "TEXT NOT NULL DEFAULT 'Diario'"),
        ("estado", "TEXT NOT NULL DEFAULT 'pendiente'"),
        ("ultimo_tipo", "TEXT NOT NULL DEFAULT 'Pendiente por cobrar'"),
        ("codeudor_documento", "TEXT"),
        ("codeudor_nombre", "TEXT"),
        ("codeudor_movil", "TEXT"),
        ("valor_seguro", "INTEGER NOT NULL DEFAULT 0"),
        ("beneficiario", "TEXT"),
        ("obs_seguro", "TEXT"),
        ("created_at", "TEXT NOT NULL DEFAULT ''"),
        ("updated_at", "TEXT NOT NULL DEFAULT ''"),
        ("proximo_cobro", "TEXT"),
        ("ultima_fecha_pago", "TEXT"),
        ("aporte_acumulado", "INTEGER NOT NULL DEFAULT 0"),
        ("synced", "INTEGER NOT NULL DEFAULT 0"),
        ("uuid", "TEXT NOT NULL DEFAULT ''"),
        ("sync_status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("last_sync_at", "TEXT"),
        ("sync_error", "TEXT"),
        ("is_deleted", "INTEGER NOT NULL DEFAULT 0"),
        ("deleted_at", "TEXT"),
        ("deleted_reason", "TEXT"),
        ("cobrador_id", "TEXT NOT NULL DEFAULT ''"),
    ]

    for name, definition in columns:
        ensure_column(cursor, "clientes", name, definition)

    # Compatibilidad con versiones viejas que tenían saldo/cuota pero no valor_credito/total_credito
    cursor.execute("""
        UPDATE clientes
        SET valor_credito = saldo
        WHERE (valor_credito IS NULL OR valor_credito = 0) AND saldo > 0
    """)

    cursor.execute("""
        UPDATE clientes
        SET total_credito = saldo
        WHERE (total_credito IS NULL OR total_credito = 0) AND saldo > 0
    """)

    cursor.execute("""
        UPDATE clientes
        SET numero_cuotas = pendientes
        WHERE (numero_cuotas IS NULL OR numero_cuotas = 0) AND pendientes > 0
    """)

    cursor.execute("UPDATE clientes SET created_at = ? WHERE created_at IS NULL OR created_at = ''", (now_text(),))
    cursor.execute("UPDATE clientes SET updated_at = ? WHERE updated_at IS NULL OR updated_at = ''", (now_text(),))

    # Clientes completamente cancelados pasan al estado PAZ Y SALVO.
    cursor.execute("""
        UPDATE clientes
        SET estado = 'paz_y_salvo',
            ultimo_tipo = 'Crédito cancelado - Paz y salvo',
            proximo_cobro = ''
        WHERE saldo <= 0
          AND pendientes <= 0
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            cliente TEXT NOT NULL,
            tipo TEXT NOT NULL,
            valor INTEGER NOT NULL DEFAULT 0,
            metodo TEXT,
            fecha TEXT NOT NULL,
            numero_cuotas INTEGER NOT NULL DEFAULT 0,
            saldo_anterior INTEGER NOT NULL DEFAULT 0,
            saldo_nuevo INTEGER NOT NULL DEFAULT 0,
            cuotas_pagadas_total INTEGER NOT NULL DEFAULT 0,
            cuotas_pendientes_total INTEGER NOT NULL DEFAULT 0,
            observacion TEXT,
            synced INTEGER NOT NULL DEFAULT 0
        )
    """)

    for name, definition in [
        ("cliente_id", "INTEGER"),
        ("cliente", "TEXT NOT NULL DEFAULT ''"),
        ("tipo", "TEXT NOT NULL DEFAULT ''"),
        ("valor", "INTEGER NOT NULL DEFAULT 0"),
        ("metodo", "TEXT"),
        ("fecha", "TEXT NOT NULL DEFAULT ''"),
        ("numero_cuotas", "INTEGER NOT NULL DEFAULT 0"),
        ("saldo_anterior", "INTEGER NOT NULL DEFAULT 0"),
        ("saldo_nuevo", "INTEGER NOT NULL DEFAULT 0"),
        ("cuotas_pagadas_total", "INTEGER NOT NULL DEFAULT 0"),
        ("cuotas_pendientes_total", "INTEGER NOT NULL DEFAULT 0"),
        ("observacion", "TEXT"),
        ("synced", "INTEGER NOT NULL DEFAULT 0"),
        ("uuid", "TEXT NOT NULL DEFAULT ''"),
        ("sync_status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("last_sync_at", "TEXT"),
        ("sync_error", "TEXT"),
        ("is_deleted", "INTEGER NOT NULL DEFAULT 0"),
        ("deleted_at", "TEXT"),
        ("cobrador_id", "TEXT NOT NULL DEFAULT ''"),
    ]:
        ensure_column(cursor, "transacciones", name, definition)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movimientos_caja (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            concepto TEXT,
            valor INTEGER NOT NULL DEFAULT 0,
            observaciones TEXT,
            fecha TEXT NOT NULL,
            synced INTEGER NOT NULL DEFAULT 0
        )
    """)

    for name, definition in [
        ("tipo", "TEXT NOT NULL DEFAULT ''"),
        ("concepto", "TEXT"),
        ("valor", "INTEGER NOT NULL DEFAULT 0"),
        ("observaciones", "TEXT"),
        ("fecha", "TEXT NOT NULL DEFAULT ''"),
        ("synced", "INTEGER NOT NULL DEFAULT 0"),
        ("uuid", "TEXT NOT NULL DEFAULT ''"),
        ("sync_status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("last_sync_at", "TEXT"),
        ("sync_error", "TEXT"),
        ("is_deleted", "INTEGER NOT NULL DEFAULT 0"),
        ("deleted_at", "TEXT"),
        ("cobrador_id", "TEXT NOT NULL DEFAULT ''"),
    ]:
        ensure_column(cursor, "movimientos_caja", name, definition)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cierres_caja (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_iso TEXT NOT NULL UNIQUE,
            caja_inicial INTEGER NOT NULL DEFAULT 0,
            recaudo INTEGER NOT NULL DEFAULT 0,
            ingresos INTEGER NOT NULL DEFAULT 0,
            egresos INTEGER NOT NULL DEFAULT 0,
            saldo_final INTEGER NOT NULL DEFAULT 0,
            pagos INTEGER NOT NULL DEFAULT 0,
            no_pagos INTEGER NOT NULL DEFAULT 0,
            aplazados INTEGER NOT NULL DEFAULT 0,
            estado TEXT NOT NULL DEFAULT 'sin_abrir',
            observacion_apertura TEXT,
            observacion_cierre TEXT,
            efectivo_contado INTEGER NOT NULL DEFAULT 0,
            diferencia_caja INTEGER NOT NULL DEFAULT 0,
            estado_cuadre TEXT NOT NULL DEFAULT 'sin_arqueo',
            periodo_tipo TEXT NOT NULL DEFAULT 'diario',
            periodo_inicio TEXT,
            periodo_fin TEXT,
            clientes_activos INTEGER NOT NULL DEFAULT 0,
            cartera_pendiente INTEGER NOT NULL DEFAULT 0,
            prestamos_nuevos INTEGER NOT NULL DEFAULT 0,
            desembolsos INTEGER NOT NULL DEFAULT 0,
            opened_at TEXT,
            closed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            synced INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Migración segura: la tabla ya existe antes de agregar columnas.
    for name, definition in [
        ("fecha_iso", "TEXT"),
        ("caja_inicial", "INTEGER NOT NULL DEFAULT 0"),
        ("recaudo", "INTEGER NOT NULL DEFAULT 0"),
        ("ingresos", "INTEGER NOT NULL DEFAULT 0"),
        ("egresos", "INTEGER NOT NULL DEFAULT 0"),
        ("saldo_final", "INTEGER NOT NULL DEFAULT 0"),
        ("pagos", "INTEGER NOT NULL DEFAULT 0"),
        ("no_pagos", "INTEGER NOT NULL DEFAULT 0"),
        ("aplazados", "INTEGER NOT NULL DEFAULT 0"),
        ("estado", "TEXT NOT NULL DEFAULT 'sin_abrir'"),
        ("observacion_apertura", "TEXT"),
        ("observacion_cierre", "TEXT"),
        ("efectivo_contado", "INTEGER NOT NULL DEFAULT 0"),
        ("diferencia_caja", "INTEGER NOT NULL DEFAULT 0"),
        ("estado_cuadre", "TEXT NOT NULL DEFAULT 'sin_arqueo'"),
        ("periodo_tipo", "TEXT NOT NULL DEFAULT 'diario'"),
        ("periodo_inicio", "TEXT"),
        ("periodo_fin", "TEXT"),
        ("clientes_activos", "INTEGER NOT NULL DEFAULT 0"),
        ("cartera_pendiente", "INTEGER NOT NULL DEFAULT 0"),
        ("prestamos_nuevos", "INTEGER NOT NULL DEFAULT 0"),
        ("desembolsos", "INTEGER NOT NULL DEFAULT 0"),
        ("opened_at", "TEXT"),
        ("closed_at", "TEXT"),
        ("created_at", "TEXT NOT NULL DEFAULT ''"),
        ("updated_at", "TEXT NOT NULL DEFAULT ''"),
        ("synced", "INTEGER NOT NULL DEFAULT 0"),
        ("uuid", "TEXT NOT NULL DEFAULT ''"),
        ("sync_status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("last_sync_at", "TEXT"),
        ("sync_error", "TEXT"),
        ("is_deleted", "INTEGER NOT NULL DEFAULT 0"),
        ("deleted_at", "TEXT"),
        ("cobrador_id", "TEXT NOT NULL DEFAULT ''"),
    ]:
        ensure_column(cursor, "cierres_caja", name, definition)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eliminados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entidad TEXT NOT NULL,
            entidad_id INTEGER NOT NULL,
            cobrador_id TEXT,
            synced INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auditoria_acciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            accion TEXT NOT NULL,
            cliente_id INTEGER,
            cliente TEXT,
            motivo TEXT NOT NULL DEFAULT '',
            detalle TEXT NOT NULL DEFAULT '',
            cobrador TEXT NOT NULL DEFAULT '',
            synced INTEGER NOT NULL DEFAULT 0
        )
    """)

    for name, definition in [
        ("uuid", "TEXT NOT NULL DEFAULT ''"),
        ("sync_status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("last_sync_at", "TEXT"),
        ("sync_error", "TEXT"),
        ("cobrador_id", "TEXT NOT NULL DEFAULT ''"),
    ]:
        ensure_column(cursor, "auditoria_acciones", name, definition)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracion_app (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )
    """)

    for name, definition in [
        ("cobrador_id", "TEXT NOT NULL DEFAULT ''"),
        ("synced", "INTEGER NOT NULL DEFAULT 0"),
        ("sync_status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("last_sync_at", "TEXT"),
        ("sync_error", "TEXT"),
    ]:
        ensure_column(cursor, "configuracion_app", name, definition)

    for key, value in [
        ("nombre_negocio", "COBROS V12 MOBILE"),
        ("nombre_cobrador", cobrador_nombre() if "cobrador_nombre" in globals() else "PACHO"),
        ("moneda", "COP"),
        ("ciudad", ""),
        ("frecuencia_default", "Diario"),
        ("interes_default", "20"),
        ("telefono_negocio", ""),
        ("pin_admin", "1234"),
        ("pin_cobrador", "0000"),
    ]:
        cursor.execute("""
            INSERT INTO configuracion_app (key, value, updated_at, cobrador_id, synced, sync_status)
            VALUES (?, ?, ?, ?, 0, 'pending')
            ON CONFLICT(key) DO NOTHING
        """, (key, value, now_text(), COBRADOR_ID if "COBRADOR_ID" in globals() else ""))



    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios_app (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT NOT NULL DEFAULT '',
            nombre TEXT NOT NULL,
            usuario TEXT NOT NULL UNIQUE,
            pin TEXT NOT NULL,
            rol TEXT NOT NULL DEFAULT 'cobrador',
            cobrador_id TEXT NOT NULL DEFAULT '',
            activo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            synced INTEGER NOT NULL DEFAULT 0,
            sync_status TEXT NOT NULL DEFAULT 'pending',
            last_sync_at TEXT,
            sync_error TEXT
        )
    """)

    for name, definition in [
        ("uuid", "TEXT NOT NULL DEFAULT ''"),
        ("nombre", "TEXT NOT NULL DEFAULT ''"),
        ("usuario", "TEXT NOT NULL DEFAULT ''"),
        ("pin", "TEXT NOT NULL DEFAULT ''"),
        ("rol", "TEXT NOT NULL DEFAULT 'cobrador'"),
        ("cobrador_id", "TEXT NOT NULL DEFAULT ''"),
        ("activo", "INTEGER NOT NULL DEFAULT 1"),
        ("created_at", "TEXT NOT NULL DEFAULT ''"),
        ("updated_at", "TEXT NOT NULL DEFAULT ''"),
        ("synced", "INTEGER NOT NULL DEFAULT 0"),
        ("sync_status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("last_sync_at", "TEXT"),
        ("sync_error", "TEXT"),
    ]:
        ensure_column(cursor, "usuarios_app", name, definition)

    now_seed = now_text()
    cursor.execute("""
        INSERT INTO usuarios_app (uuid, nombre, usuario, pin, rol, cobrador_id, activo, created_at, updated_at, synced, sync_status)
        VALUES (?, 'Administrador', 'admin', '1234', 'administrador', ?, 1, ?, ?, 0, 'pending')
        ON CONFLICT(usuario) DO NOTHING
    """, (str(uuid.uuid4()), str(uuid.uuid4()), now_seed, now_seed))
    cursor.execute("""
        INSERT INTO usuarios_app (uuid, nombre, usuario, pin, rol, cobrador_id, activo, created_at, updated_at, synced, sync_status)
        VALUES (?, ?, 'pacho', '0000', 'cobrador', ?, 1, ?, ?, 0, 'pending')
        ON CONFLICT(usuario) DO NOTHING
    """, (str(uuid.uuid4()), COBRADOR_NOMBRE if 'COBRADOR_NOMBRE' in globals() else 'PACHO', COBRADOR_ID if 'COBRADOR_ID' in globals() else 'pacho', now_seed, now_seed))

    cursor.execute("UPDATE clientes SET cobrador_id = ? WHERE cobrador_id IS NULL OR cobrador_id = ''", (COBRADOR_ID if 'COBRADOR_ID' in globals() else 'pacho',))
    cursor.execute("UPDATE transacciones SET cobrador_id = ? WHERE cobrador_id IS NULL OR cobrador_id = ''", (COBRADOR_ID if 'COBRADOR_ID' in globals() else 'pacho',))
    cursor.execute("UPDATE movimientos_caja SET cobrador_id = ? WHERE cobrador_id IS NULL OR cobrador_id = ''", (COBRADOR_ID if 'COBRADOR_ID' in globals() else 'pacho',))
    cursor.execute("UPDATE cierres_caja SET cobrador_id = ? WHERE cobrador_id IS NULL OR cobrador_id = ''", (COBRADOR_ID if 'COBRADOR_ID' in globals() else 'pacho',))
    cursor.execute("UPDATE auditoria_acciones SET cobrador_id = ? WHERE cobrador_id IS NULL OR cobrador_id = ''", (COBRADOR_ID if 'COBRADOR_ID' in globals() else 'pacho',))

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS db_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT ''
        )
    """)

    # Índices para acelerar búsquedas, filtros, historial y sincronización.
    for index_sql in [
        "CREATE INDEX IF NOT EXISTS idx_clientes_nombre ON clientes(nombre)",
        "CREATE INDEX IF NOT EXISTS idx_clientes_documento ON clientes(documento)",
        "CREATE INDEX IF NOT EXISTS idx_clientes_telefono ON clientes(telefono)",
        "CREATE INDEX IF NOT EXISTS idx_clientes_barrio ON clientes(barrio)",
        "CREATE INDEX IF NOT EXISTS idx_clientes_ruta ON clientes(ruta)",
        "CREATE INDEX IF NOT EXISTS idx_clientes_uuid ON clientes(uuid)",
        "CREATE INDEX IF NOT EXISTS idx_clientes_deleted ON clientes(is_deleted)",
        "CREATE INDEX IF NOT EXISTS idx_clientes_estado ON clientes(estado)",
        "CREATE INDEX IF NOT EXISTS idx_clientes_proximo_cobro ON clientes(proximo_cobro)",
        "CREATE INDEX IF NOT EXISTS idx_clientes_synced ON clientes(synced)",
        "CREATE INDEX IF NOT EXISTS idx_clientes_sync_status ON clientes(sync_status)",
        "CREATE INDEX IF NOT EXISTS idx_transacciones_cliente ON transacciones(cliente_id)",
        "CREATE INDEX IF NOT EXISTS idx_transacciones_fecha ON transacciones(fecha)",
        "CREATE INDEX IF NOT EXISTS idx_transacciones_synced ON transacciones(synced)",
        "CREATE INDEX IF NOT EXISTS idx_transacciones_uuid ON transacciones(uuid)",
        "CREATE INDEX IF NOT EXISTS idx_transacciones_tipo ON transacciones(tipo)",
        "CREATE INDEX IF NOT EXISTS idx_movimientos_fecha ON movimientos_caja(fecha)",
        "CREATE INDEX IF NOT EXISTS idx_movimientos_uuid ON movimientos_caja(uuid)",
        "CREATE INDEX IF NOT EXISTS idx_movimientos_synced ON movimientos_caja(synced)",
        "CREATE INDEX IF NOT EXISTS idx_cierres_synced ON cierres_caja(synced)",
        "CREATE INDEX IF NOT EXISTS idx_cierres_periodo ON cierres_caja(periodo_inicio, periodo_fin)",
        "CREATE INDEX IF NOT EXISTS idx_eliminados_estado ON eliminados(entidad, synced)",
        "CREATE INDEX IF NOT EXISTS idx_auditoria_fecha ON auditoria_acciones(fecha)",
        "CREATE INDEX IF NOT EXISTS idx_configuracion_synced ON configuracion_app(synced)",
        "CREATE INDEX IF NOT EXISTS idx_configuracion_cobrador ON configuracion_app(cobrador_id)",
    ]:
        cursor.execute(index_sql)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        )
    """)

    for table_name in [
        "clientes",
        "transacciones",
        "movimientos_caja",
        "cierres_caja",
        "auditoria_acciones",
    ]:
        ensure_uuid_values(cursor, table_name)

    set_db_meta(cursor, "db_schema_version", DB_SCHEMA_VERSION)
    set_db_meta(cursor, "db_last_migration_at", now_text())

    cursor.execute("""
        INSERT OR IGNORE INTO db_migrations (version, applied_at, description)
        VALUES (?, ?, ?)
    """, (
        DB_SCHEMA_VERSION,
        now_text(),
        "Migración segura: UUIDs, configuración, sync_status, índices y backups.",
    ))

    conn.commit()
    conn.close()


def load_clients_from_db():
    global CLIENTES
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, documento, nombre, telefono, direccion, barrio, zona, ruta, orden_visita, producto,
               valor_credito, interes, total_credito, cuota, numero_cuotas,
               saldo, pagadas, pendientes, cobro, estado, ultimo_tipo,
               codeudor_documento, codeudor_nombre, codeudor_movil,
               valor_seguro, beneficiario, obs_seguro, created_at, updated_at,
               proximo_cobro, ultima_fecha_pago, aporte_acumulado, synced, cobrador_id
        FROM clientes
        WHERE COALESCE(is_deleted, 0) = 0
          AND (? = '' OR COALESCE(cobrador_id, '') = ?)
        ORDER BY nombre ASC
    """, (active_cobrador_id(), active_cobrador_id()))

    CLIENTES = [dict(row) for row in cursor.fetchall()]
    conn.close()


def load_transacciones_from_db():
    global TRANSACCIONES
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, cliente_id, cliente, tipo, valor, metodo, fecha,
               numero_cuotas, saldo_anterior, saldo_nuevo,
               cuotas_pagadas_total, cuotas_pendientes_total,
               observacion, synced, cobrador_id
        FROM transacciones
        WHERE (? = '' OR COALESCE(cobrador_id, '') = ?)
        ORDER BY id ASC
    """, (active_cobrador_id(), active_cobrador_id()))

    TRANSACCIONES = [dict(row) for row in cursor.fetchall()]
    conn.close()


def load_movimientos_from_db():
    global MOVIMIENTOS_CAJA
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, tipo, concepto, valor, observaciones, fecha, synced, cobrador_id
        FROM movimientos_caja
        WHERE (? = '' OR COALESCE(cobrador_id, '') = ?)
        ORDER BY id ASC
    """, (active_cobrador_id(), active_cobrador_id()))

    MOVIMIENTOS_CAJA = [dict(row) for row in cursor.fetchall()]
    conn.close()


def normalize_clients_with_latest_transactions():
    """
    Asegura que la ficha del cliente quede alineada con su último movimiento.
    Esto evita que un aporte quede bien en historial, pero no reflejado en la
    lista principal, en gestión o en el saldo general.
    """
    try:
        if not CLIENTES or not TRANSACCIONES:
            return

        latest_by_client = {}
        for tx in TRANSACCIONES:
            client_id = int(tx.get("cliente_id") or 0)
            if client_id <= 0:
                continue
            latest_by_client[client_id] = tx

        conn = get_connection()
        cursor = conn.cursor()
        changed = False

        for cliente in CLIENTES:
            client_id = int(cliente.get("id") or 0)
            latest_tx = latest_by_client.get(client_id)
            if not latest_tx:
                continue

            nuevo_saldo = int(latest_tx.get("saldo_nuevo", cliente.get("saldo", 0)) or 0)
            nuevas_pagadas = int(latest_tx.get("cuotas_pagadas_total", cliente.get("pagadas", 0)) or 0)
            nuevas_pendientes = int(latest_tx.get("cuotas_pendientes_total", cliente.get("pendientes", 0)) or 0)

            saldo_actual = int(cliente.get("saldo", 0) or 0)
            pagadas_actual = int(cliente.get("pagadas", 0) or 0)
            pendientes_actual = int(cliente.get("pendientes", 0) or 0)

            if (
                saldo_actual != nuevo_saldo
                or pagadas_actual != nuevas_pagadas
                or pendientes_actual != nuevas_pendientes
            ):
                cursor.execute(
                    """
                    UPDATE clientes
                    SET saldo = ?,
                        pagadas = ?,
                        pendientes = ?,
                        synced = 0,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        nuevo_saldo,
                        nuevas_pagadas,
                        nuevas_pendientes,
                        now_text(),
                        client_id,
                    ),
                )
                changed = True

        if changed:
            conn.commit()
        conn.close()
    except Exception as error:
        print("NORMALIZE CLIENTS ERROR:", error)


def refresh_memory_from_db(
    *,
    clients=True,
    transactions=True,
    movements=True,
    normalize=False,
):
    """
    Refresco selectivo de la memoria local.

    La normalización global es costosa, por eso solo se ejecuta al iniciar
    la app o después de una sincronización completa con Supabase.
    """
    update_due_statuses()

    if clients:
        load_clients_from_db()

    if transactions:
        load_transacciones_from_db()

    if normalize:
        # La normalización necesita clientes y transacciones cargados.
        if not clients:
            load_clients_from_db()
        if not transactions:
            load_transacciones_from_db()
        normalize_clients_with_latest_transactions()
        load_clients_from_db()

    if movements:
        load_movimientos_from_db()


def refresh_clients_cache():
    refresh_memory_from_db(
        clients=True,
        transactions=False,
        movements=False,
        normalize=False,
    )


def refresh_client_history_cache():
    refresh_memory_from_db(
        clients=True,
        transactions=True,
        movements=False,
        normalize=False,
    )


def refresh_daily_cache():
    refresh_memory_from_db(
        clients=True,
        transactions=True,
        movements=True,
        normalize=False,
    )


def insert_client_db(cliente):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO clientes (
            documento, nombre, telefono, direccion, barrio, zona, ruta, orden_visita, producto,
            valor_credito, interes, total_credito, cuota, numero_cuotas,
            saldo, pagadas, pendientes, cobro, estado, ultimo_tipo,
            codeudor_documento, codeudor_nombre, codeudor_movil,
            valor_seguro, beneficiario, obs_seguro, created_at, updated_at,
            proximo_cobro, ultima_fecha_pago, aporte_acumulado, synced, cobrador_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        cliente.get("documento", ""),
        cliente.get("nombre", "SIN NOMBRE"),
        cliente.get("telefono", ""),
        cliente.get("direccion", ""),
        cliente.get("barrio", ""),
        cliente.get("zona", ""),
        cliente.get("ruta", ""),
        int(cliente.get("orden_visita", 0)),
        cliente.get("producto", "5 - CREDITO EN EFECTIVO"),
        int(cliente.get("valor_credito", 0)),
        float(cliente.get("interes", 0)),
        int(cliente.get("total_credito", 0)),
        int(cliente.get("cuota", 0)),
        int(cliente.get("numero_cuotas", 1)),
        int(cliente.get("saldo", 0)),
        int(cliente.get("pagadas", 0)),
        int(cliente.get("pendientes", 0)),
        cliente.get("cobro", "Diario"),
        cliente.get("estado", "pendiente"),
        cliente.get("ultimo_tipo", "Pendiente por cobrar"),
        cliente.get("codeudor_documento", ""),
        cliente.get("codeudor_nombre", ""),
        cliente.get("codeudor_movil", ""),
        int(cliente.get("valor_seguro", 0)),
        cliente.get("beneficiario", ""),
        cliente.get("obs_seguro", ""),
        cliente.get("created_at", now_text()),
        now_text(),
        cliente.get("proximo_cobro", iso_today()),
        cliente.get("ultima_fecha_pago", ""),
        int(cliente.get("aporte_acumulado", 0)),
        int(cliente.get("synced", 0)),
        cliente.get("cobrador_id") or active_cobrador_id() or COBRADOR_ID,
    ))

    new_id = cursor.lastrowid
    cursor.execute("""
        UPDATE clientes
        SET uuid = CASE WHEN uuid IS NULL OR uuid = '' THEN ? ELSE uuid END,
            sync_status = 'pending',
            cobrador_id = CASE WHEN cobrador_id IS NULL OR cobrador_id = '' THEN ? ELSE cobrador_id END
        WHERE id = ?
    """, (str(uuid.uuid4()), active_cobrador_id() or COBRADOR_ID, new_id))
    conn.commit()
    conn.close()
    return new_id


def update_client_db(cliente):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE clientes
        SET documento = ?, nombre = ?, telefono = ?, direccion = ?, barrio = ?, zona = ?, ruta = ?, orden_visita = ?, producto = ?,
            valor_credito = ?, interes = ?, total_credito = ?, cuota = ?, numero_cuotas = ?,
            saldo = ?, pagadas = ?, pendientes = ?, cobro = ?, estado = ?, ultimo_tipo = ?,
            codeudor_documento = ?, codeudor_nombre = ?, codeudor_movil = ?,
            valor_seguro = ?, beneficiario = ?, obs_seguro = ?, updated_at = ?,
            proximo_cobro = ?, ultima_fecha_pago = ?,
            aporte_acumulado = ?, synced = ?, sync_status = 'pending',
            cobrador_id = CASE WHEN cobrador_id IS NULL OR cobrador_id = '' THEN ? ELSE cobrador_id END
        WHERE id = ?
    """, (
        cliente.get("documento", ""),
        cliente.get("nombre", "SIN NOMBRE"),
        cliente.get("telefono", ""),
        cliente.get("direccion", ""),
        cliente.get("barrio", ""),
        cliente.get("zona", ""),
        cliente.get("ruta", ""),
        int(cliente.get("orden_visita", 0)),
        cliente.get("producto", "5 - CREDITO EN EFECTIVO"),
        int(cliente.get("valor_credito", 0)),
        float(cliente.get("interes", 0)),
        int(cliente.get("total_credito", 0)),
        int(cliente.get("cuota", 0)),
        int(cliente.get("numero_cuotas", 1)),
        int(cliente.get("saldo", 0)),
        int(cliente.get("pagadas", 0)),
        int(cliente.get("pendientes", 0)),
        cliente.get("cobro", "Diario"),
        cliente.get("estado", "pendiente"),
        cliente.get("ultimo_tipo", "Pendiente por cobrar"),
        cliente.get("codeudor_documento", ""),
        cliente.get("codeudor_nombre", ""),
        cliente.get("codeudor_movil", ""),
        int(cliente.get("valor_seguro", 0)),
        cliente.get("beneficiario", ""),
        cliente.get("obs_seguro", ""),
        now_text(),
        cliente.get("proximo_cobro", ""),
        cliente.get("ultima_fecha_pago", ""),
        int(cliente.get("aporte_acumulado", 0)),
        int(cliente.get("synced", 0)),
        cliente.get("cobrador_id", active_cobrador_id() or COBRADOR_ID),
        int(cliente.get("id")),
    ))

    conn.commit()
    conn.close()


def mark_deleted_local(entidad, entidad_id):
    """
    Guarda una marca local de eliminación para que Supabase no restaure
    registros que el usuario ya borró.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO eliminados (entidad, entidad_id, cobrador_id, synced, deleted_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            entidad,
            int(entidad_id),
            COBRADOR_ID if "COBRADOR_ID" in globals() else "",
            0,
            now_text(),
        ))

        conn.commit()
        conn.close()
    except Exception as error:
        print("ERROR mark_deleted_local:", error)


def get_deleted_ids(entidad, only_pending=False):
    """
    Obtiene IDs marcados como eliminados.

    only_pending=True:
        solo devuelve eliminaciones que todavía no han sido confirmadas
        en Supabase. Las marcas antiguas synced=1 no deben impedir que un
        registro existente en la nube vuelva a descargarse.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        if only_pending:
            cursor.execute(
                """
                SELECT entidad_id
                FROM eliminados
                WHERE entidad = ?
                  AND synced = 0
                """,
                (entidad,),
            )
        else:
            cursor.execute(
                """
                SELECT entidad_id
                FROM eliminados
                WHERE entidad = ?
                """,
                (entidad,),
            )

        ids = {
            int(row[0])
            for row in cursor.fetchall()
        }
        conn.close()
        return ids

    except Exception:
        return set()


def clear_obsolete_deleted_marks(entidad, remote_ids):
    """
    Elimina marcas antiguas synced=1 cuando el registro vuelve a existir
    en Supabase. Esto permite restaurar datos legítimos en otros equipos.
    """
    if not remote_ids:
        return 0

    try:
        conn = get_connection()
        cursor = conn.cursor()

        placeholders = ",".join("?" for _ in remote_ids)

        cursor.execute(
            f"""
            DELETE FROM eliminados
            WHERE entidad = ?
              AND synced = 1
              AND entidad_id IN ({placeholders})
            """,
            [entidad, *sorted(remote_ids)],
        )

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted_count

    except Exception as error:
        print("ERROR clear_obsolete_deleted_marks:", error)
        return 0


def mark_deleted_synced(entidad, entidad_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE eliminados SET synced = 1
            WHERE entidad = ? AND entidad_id = ?
        """, (entidad, int(entidad_id)))
        conn.commit()
        conn.close()
    except Exception as error:
        print("ERROR mark_deleted_synced:", error)


def delete_client_db(cliente_id):
    """
    Elimina un cliente/préstamo localmente y corrige completamente la caja.

    Además de borrar el cliente y sus transacciones, elimina movimientos de caja
    relacionados con ese cliente, especialmente:
    - Egreso automático de desembolso del préstamo.
    - Movimientos cuya observación contenga el nombre del cliente.
    """
    cliente = get_client_by_id(cliente_id)

    conn = get_connection()
    cursor = conn.cursor()

    if cliente:
        nombre_cliente = str(cliente.get("nombre", "")).strip()
        valor_credito = int(cliente.get("valor_credito") or 0)

        # 1. Eliminar movimientos vinculados por observación con nombre del cliente.
        # Esto cubre el desembolso y cualquier movimiento manual donde se haya escrito el nombre.
        if nombre_cliente:
            cursor.execute("""
                DELETE FROM movimientos_caja
                WHERE observaciones LIKE ?
            """, (f"%{nombre_cliente}%",))

        # 2. Eliminar egreso automático de desembolso por concepto y valor.
        # Esto cubre versiones donde la observación no quedó completa.
        cursor.execute("""
            DELETE FROM movimientos_caja
            WHERE tipo = 'Egreso'
              AND concepto = 'Desembolso préstamo'
              AND valor = ?
        """, (valor_credito,))

    # 3. Eliminar transacciones del cliente.
    cursor.execute("DELETE FROM transacciones WHERE cliente_id = ?", (int(cliente_id),))

    # 4. Eliminar cliente/préstamo.
    cursor.execute("DELETE FROM clientes WHERE id = ?", (int(cliente_id),))

    conn.commit()
    conn.close()

    # 5. Marcar eliminado para que no vuelva a descargarse desde Supabase en este celular.
    mark_deleted_local("cliente", int(cliente_id))


def get_client_by_id(cliente_id):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, documento, nombre, telefono, direccion, barrio, zona, ruta, orden_visita, producto,
               valor_credito, interes, total_credito, cuota, numero_cuotas,
               saldo, pagadas, pendientes, cobro, estado, ultimo_tipo,
               codeudor_documento, codeudor_nombre, codeudor_movil,
               valor_seguro, beneficiario, obs_seguro, created_at, updated_at,
               proximo_cobro, ultima_fecha_pago, aporte_acumulado, synced, cobrador_id
        FROM clientes
        WHERE id = ?
          AND COALESCE(is_deleted, 0) = 0
          AND (? = '' OR COALESCE(cobrador_id, '') = ?)
    """, (int(cliente_id), active_cobrador_id(), active_cobrador_id()))

    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def reset_client_status_db(cliente_id):
    cliente = get_client_by_id(cliente_id)
    if cliente:
        cliente["estado"] = "pendiente"
        cliente["ultimo_tipo"] = "Pendiente por cobrar"
        update_client_db(cliente)


def insert_audit_log(accion, cliente=None, motivo="", detalle=""):
    """Registra acciones sensibles para control interno y trazabilidad."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_acciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                accion TEXT NOT NULL,
                cliente_id INTEGER,
                cliente TEXT,
                motivo TEXT NOT NULL DEFAULT '',
                detalle TEXT NOT NULL DEFAULT '',
                cobrador TEXT NOT NULL DEFAULT '',
                synced INTEGER NOT NULL DEFAULT 0
            )
        """)

        cliente_id = None
        cliente_nombre = ""
        if cliente:
            cliente_id = cliente.get("id")
            cliente_nombre = cliente.get("nombre", "")

        cursor.execute("""
            INSERT INTO auditoria_acciones
            (fecha, accion, cliente_id, cliente, motivo, detalle, cobrador, synced)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            now_text(),
            str(accion),
            cliente_id,
            cliente_nombre,
            str(motivo or "").strip(),
            str(detalle or "").strip(),
            cobrador_nombre(),
        ))
        conn.commit()
        conn.close()
    except Exception as error:
        print("AUDIT ERROR:", error)


def load_audit_logs(limit=100):
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_acciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                accion TEXT NOT NULL,
                cliente_id INTEGER,
                cliente TEXT,
                motivo TEXT NOT NULL DEFAULT '',
                detalle TEXT NOT NULL DEFAULT '',
                cobrador TEXT NOT NULL DEFAULT '',
                synced INTEGER NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("""
            SELECT id, fecha, accion, cliente_id, cliente, motivo, detalle, cobrador
            FROM auditoria_acciones
            ORDER BY id DESC
            LIMIT ?
        """, (int(limit),))
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as error:
        print("AUDIT LOAD ERROR:", error)
        return []


def motive_required_popup(title, message, on_confirm, options=None):
    """Popup reutilizable para exigir motivo antes de acciones delicadas."""
    content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))

    label = Label(
        text=message,
        color=WHITE,
        font_size="13sp",
        halign="center",
        valign="middle",
        size_hint_y=None,
        height=dp(62),
    )
    label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
    content.add_widget(label)

    motive_spinner = Spinner(
        text="Seleccione motivo",
        values=options or ["Corrección de datos", "Error de registro", "Solicitud del cliente", "Revisión de caja", "Otro"],
        size_hint_y=None,
        height=dp(44),
        background_normal="",
        background_color=WHITE,
        color=TEXT,
    )
    detail_input = AppTextInput(
        hint_text="Detalle obligatorio si aplica",
        multiline=True,
    )
    detail_input.height = dp(80)

    content.add_widget(motive_spinner)
    content.add_widget(detail_input)

    buttons = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(10))
    cancel = Button(text="Cancelar", background_normal="", background_color=(0.45, 0.48, 0.55, 1), color=WHITE, bold=True)
    confirm = Button(text="Confirmar", background_normal="", background_color=DANGER, color=WHITE, bold=True)
    buttons.add_widget(cancel)
    buttons.add_widget(confirm)
    content.add_widget(buttons)

    popup = Popup(title=title, content=content, size_hint=(0.92, None), height=dp(360), auto_dismiss=False)
    cancel.bind(on_release=popup.dismiss)

    def do_confirm(*_):
        motivo = motive_spinner.text.strip()
        detalle = detail_input.text.strip()
        if motivo == "Seleccione motivo":
            show_popup("Motivo requerido", "Seleccione un motivo antes de continuar.", height=240)
            return
        if motivo == "Otro" and not detalle:
            show_popup("Detalle requerido", "Escriba el detalle del motivo.", height=240)
            return
        popup.dismiss()
        on_confirm(motivo, detalle)

    confirm.bind(on_release=do_confirm)
    popup.open()


def insert_transaction_db(transaccion):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO transacciones (
            cliente_id, cliente, tipo, valor, metodo, fecha,
            numero_cuotas, saldo_anterior, saldo_nuevo,
            cuotas_pagadas_total, cuotas_pendientes_total,
            observacion, synced
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        transaccion.get("cliente_id"),
        transaccion.get("cliente", ""),
        transaccion.get("tipo", ""),
        int(transaccion.get("valor", 0)),
        transaccion.get("metodo", ""),
        transaccion.get("fecha", now_text()),
        int(transaccion.get("numero_cuotas", 0)),
        int(transaccion.get("saldo_anterior", 0)),
        int(transaccion.get("saldo_nuevo", 0)),
        int(transaccion.get("cuotas_pagadas_total", 0)),
        int(transaccion.get("cuotas_pendientes_total", 0)),
        transaccion.get("observacion", ""),
        int(transaccion.get("synced", 0)),
    ))

    new_id = cursor.lastrowid
    cursor.execute("""
        UPDATE transacciones
        SET uuid = CASE WHEN uuid IS NULL OR uuid = '' THEN ? ELSE uuid END,
            sync_status = 'pending',
            cobrador_id = CASE WHEN cobrador_id IS NULL OR cobrador_id = '' THEN ? ELSE cobrador_id END
        WHERE id = ?
    """, (str(uuid.uuid4()), active_cobrador_id() or COBRADOR_ID, new_id))
    conn.commit()
    conn.close()
    return new_id


def insert_movement_db(movimiento):
    conn = get_connection()
    cursor = conn.cursor()

    owner_id = str(movimiento.get("cobrador_id") or active_cobrador_id() or COBRADOR_ID).strip()

    cursor.execute("""
        INSERT INTO movimientos_caja
        (tipo, concepto, valor, observaciones, fecha, synced, cobrador_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        movimiento.get("tipo", ""),
        movimiento.get("concepto", ""),
        int(movimiento.get("valor", 0)),
        movimiento.get("observaciones", ""),
        movimiento.get("fecha", today_text()),
        int(movimiento.get("synced", 0)),
        owner_id,
    ))

    new_id = cursor.lastrowid
    cursor.execute("""
        UPDATE movimientos_caja
        SET uuid = CASE WHEN uuid IS NULL OR uuid = '' THEN ? ELSE uuid END,
            sync_status = 'pending',
            cobrador_id = CASE WHEN cobrador_id IS NULL OR cobrador_id = '' THEN ? ELSE cobrador_id END
        WHERE id = ?
    """, (str(uuid.uuid4()), owner_id, new_id))

    conn.commit()
    conn.close()
    return new_id


def clear_all_data_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transacciones")
    cursor.execute("DELETE FROM movimientos_caja")
    cursor.execute("DELETE FROM clientes")
    cursor.execute("DELETE FROM cierres_caja")
    conn.commit()
    conn.close()
    refresh_memory_from_db()



def cash_owner_id():
    """
    Propietario operativo de la caja.
    - Modo dueño único: admin y cobrador usan la misma caja del dueño.
    - Multiusuario: cada cobrador usa su propia caja y admin ve consolidado.
    """
    if MODO_DUENO_UNICO:
        return active_cobrador_id() or DUENO_COBRADOR_ID or COBRADOR_ID
    return active_cobrador_id()


def cash_owner_label():
    if MODO_DUENO_UNICO and is_admin_role():
        return active_cobrador_name() or DUENO_NOMBRE
    if is_admin_role():
        return "ADMINISTRADOR / CONSOLIDADO"
    return active_cobrador_name() or "COBRADOR"


def cash_period_key(date_iso=None, owner_id=None):
    """
    Llave única de caja por semana y cobrador.
    periodo_inicio conserva la fecha real; fecha_iso queda única por cobrador.
    """
    week_start, _ = week_bounds(date_iso)
    owner = str(owner_id if owner_id is not None else cash_owner_id() or COBRADOR_ID).strip()
    owner_short = owner.replace("-", "")[:12] or "principal"
    return f"{week_start}_{owner_short}"


def can_operate_cash():
    """
    Define quién puede abrir/cerrar caja.
    - Modo dueño único: el mismo usuario admin puede operar caja.
    - Multiusuario: solo cobradores operan caja; admin ve consolidado.
    """
    if MODO_DUENO_UNICO:
        return bool(cash_owner_id())
    return not is_admin_role() and bool(cash_owner_id())


def require_cash_open(action_text="realizar esta operación"):
    if not MODO_DUENO_UNICO and is_admin_role():
        return False, "El administrador no registra operación de caja directa. Debe revisar el consolidado o entrar como cobrador."

    if not cash_owner_id():
        return False, "No hay cobrador activo. Cierra sesión e inicia nuevamente."

    status = get_journey_status()
    if status != "abierta":
        return False, f"Debes abrir la caja semanal antes de {action_text}."
    return True, "OK"


def cash_summary_by_collector(date_iso=None):
    start_iso, end_iso = week_bounds(date_iso)
    owners = {}

    def ensure_owner(cobrador_id, nombre=""):
        key = str(cobrador_id or COBRADOR_ID).strip()
        if not key:
            key = COBRADOR_ID
        if key not in owners:
            owners[key] = {
                "cobrador_id": key,
                "nombre": nombre or key[:8],
                "caja_inicial": 0,
                "recaudo": 0,
                "ingresos": 0,
                "egresos": 0,
                "saldo_esperado": 0,
                "estado": "sin_abrir",
                "pagos": 0,
                "no_pagos": 0,
            }
        return owners[key]

    for user in load_app_users(active_only=False):
        if str(user.get("rol", "")).lower() == "cobrador":
            ensure_owner(user.get("cobrador_id") or "", user.get("nombre") or user.get("usuario") or "")

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM cierres_caja
        WHERE COALESCE(periodo_tipo, 'diario') = 'semanal'
          AND COALESCE(is_deleted, 0) = 0
          AND COALESCE(periodo_inicio, '') = ?
    """, (start_iso,))
    for row in cursor.fetchall():
        r = dict(row)
        owner = ensure_owner(r.get("cobrador_id") or COBRADOR_ID)
        owner["caja_inicial"] = safe_int(r.get("caja_inicial", 0))
        owner["estado"] = r.get("estado", "sin_abrir") or "sin_abrir"

    cursor.execute("""
        SELECT cobrador_id, tipo, valor
        FROM transacciones
        WHERE substr(COALESCE(fecha, ''), 1, 10) BETWEEN ? AND ?
    """, (start_iso, end_iso))
    for row in cursor.fetchall():
        r = dict(row)
        owner = ensure_owner(r.get("cobrador_id") or COBRADOR_ID)
        if r.get("tipo") in ("Cuota", "Aporte"):
            owner["recaudo"] += safe_int(r.get("valor", 0))
            owner["pagos"] += 1
        elif r.get("tipo") == "No Pago":
            owner["no_pagos"] += 1

    cursor.execute("""
        SELECT cobrador_id, tipo, valor
        FROM movimientos_caja
        WHERE substr(COALESCE(fecha, ''), 1, 10) BETWEEN ? AND ?
    """, (start_iso, end_iso))
    for row in cursor.fetchall():
        r = dict(row)
        owner = ensure_owner(r.get("cobrador_id") or COBRADOR_ID)
        if r.get("tipo") == "Ingreso":
            owner["ingresos"] += safe_int(r.get("valor", 0))
        elif r.get("tipo") == "Egreso":
            owner["egresos"] += safe_int(r.get("valor", 0))

    conn.close()

    for owner in owners.values():
        owner["saldo_esperado"] = owner["caja_inicial"] + owner["recaudo"] + owner["ingresos"] - owner["egresos"]

    return sorted(owners.values(), key=lambda item: item.get("nombre", ""))




def central_cash_movements():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM movimientos_caja
        WHERE COALESCE(cobrador_id, '') = ?
          AND COALESCE(is_deleted, 0) = 0
        ORDER BY id DESC
    """, (CENTRAL_CASH_ID,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def central_cash_balance():
    balance = 0
    for movement in central_cash_movements():
        value = safe_int(movement.get("valor", 0))
        if movement.get("tipo") == "Ingreso":
            balance += value
        elif movement.get("tipo") == "Egreso":
            balance -= value
    return balance


def collector_display_name_by_id(cobrador_id):
    for user in load_app_users(active_only=False):
        if str(user.get("cobrador_id") or "") == str(cobrador_id or ""):
            return user.get("nombre") or user.get("usuario") or str(cobrador_id)[:8]
    return str(cobrador_id or "")[:8]


def last_closed_cash_by_collector(cobrador_id):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM cierres_caja
        WHERE COALESCE(cobrador_id, '') = ?
          AND COALESCE(periodo_tipo, 'diario') = 'semanal'
          AND estado = 'cerrada'
          AND COALESCE(is_deleted, 0) = 0
        ORDER BY periodo_inicio DESC, id DESC
        LIMIT 1
    """, (str(cobrador_id or ""),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def assigned_base_for_collector(cobrador_id):
    """Última base entregada desde caja central al cobrador."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    pattern = f"BASE_ENTREGADA:{cobrador_id}"
    cursor.execute("""
        SELECT *
        FROM movimientos_caja
        WHERE COALESCE(cobrador_id, '') = ?
          AND concepto = 'Base entregada a cobrador'
          AND COALESCE(observaciones, '') LIKE ?
          AND COALESCE(is_deleted, 0) = 0
        ORDER BY id DESC
        LIMIT 1
    """, (CENTRAL_CASH_ID, f"%{pattern}%"))
    row = cursor.fetchone()
    conn.close()
    return safe_int(row["valor"]) if row else 0


def liquidated_base_for_collector(cobrador_id):
    """Última base dejada en manos del cobrador después de liquidación."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    pattern = f"BASE_PROXIMA:{cobrador_id}:"
    cursor.execute("""
        SELECT observaciones
        FROM movimientos_caja
        WHERE COALESCE(cobrador_id, '') = ?
          AND concepto = 'Liquidación cobrador'
          AND COALESCE(observaciones, '') LIKE ?
          AND COALESCE(is_deleted, 0) = 0
        ORDER BY id DESC
        LIMIT 1
    """, (CENTRAL_CASH_ID, f"%{pattern}%"))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return 0
    obs = str(row["observaciones"] or "")
    try:
        # formato: BASE_PROXIMA:<id>:<valor>
        parts = obs.split(pattern, 1)[1]
        value = parts.split()[0].replace(";", "").replace("|", "")
        return safe_int(value)
    except Exception:
        return 0


def suggested_opening_base_for_collector(cobrador_id):
    """
    Base sugerida para la próxima apertura:
    1) Base dejada en liquidación anterior.
    2) Base entregada por admin.
    3) 0 si no existe.
    """
    liquidated = liquidated_base_for_collector(cobrador_id)
    if liquidated > 0:
        return liquidated
    return assigned_base_for_collector(cobrador_id)


def hand_base_to_collector(cobrador_id, amount, observation=""):
    amount = safe_int(amount)
    if amount <= 0:
        raise ValueError("La base debe ser mayor que cero.")
    if amount > central_cash_balance():
        raise ValueError(f"Caja central insuficiente. Disponible: {money(central_cash_balance())}")

    name = collector_display_name_by_id(cobrador_id)
    insert_movement_db({
        "tipo": "Egreso",
        "concepto": "Base entregada a cobrador",
        "valor": amount,
        "observaciones": f"BASE_ENTREGADA:{cobrador_id} | Cobrador: {name} | {observation}",
        "fecha": today_text(),
        "synced": 0,
        "cobrador_id": CENTRAL_CASH_ID,
    })
    insert_audit_log("Base entregada a cobrador", None, name, f"Valor: {money(amount)}. {observation}")
    return True


def add_central_cash(amount, observation=""):
    amount = safe_int(amount)
    if amount <= 0:
        raise ValueError("El valor debe ser mayor que cero.")
    insert_movement_db({
        "tipo": "Ingreso",
        "concepto": "Ingreso caja central",
        "valor": amount,
        "observaciones": observation or "Ingreso manual a caja central",
        "fecha": today_text(),
        "synced": 0,
        "cobrador_id": CENTRAL_CASH_ID,
    })
    insert_audit_log("Ingreso caja central", None, "Caja central", f"Valor: {money(amount)}. {observation}")
    return True


def liquidate_collector_cash(cobrador_id, next_base, received_cash=None, observation=""):
    closure = last_closed_cash_by_collector(cobrador_id)
    if not closure:
        raise ValueError("Este cobrador no tiene una caja cerrada para liquidar.")

    expected = safe_int(closure.get("saldo_final", 0))
    counted = safe_int(closure.get("efectivo_contado", expected))
    next_base = safe_int(next_base)

    if received_cash is None:
        received_cash = max(counted - next_base, 0)
    received_cash = safe_int(received_cash)

    if next_base < 0 or received_cash < 0:
        raise ValueError("Los valores no pueden ser negativos.")

    # Lo que el cobrador debería entregar si se le deja esa base.
    should_receive = max(counted - next_base, 0)
    difference = received_cash - should_receive

    name = collector_display_name_by_id(cobrador_id)

    if received_cash > 0:
        insert_movement_db({
            "tipo": "Ingreso",
            "concepto": "Liquidación cobrador",
            "valor": received_cash,
            "observaciones": (
                f"LIQUIDACION:{cobrador_id} | BASE_PROXIMA:{cobrador_id}:{next_base} | "
                f"Cobrador: {name} | Esperado cierre: {money(expected)} | "
                f"Contado: {money(counted)} | Debía entregar: {money(should_receive)} | "
                f"Entregó: {money(received_cash)} | Diferencia: {money(difference)} | {observation}"
            ),
            "fecha": today_text(),
            "synced": 0,
            "cobrador_id": CENTRAL_CASH_ID,
        })
    else:
        # Registra movimiento 0 no se puede; dejar solo auditoría y base futura en meta por observación no es viable.
        # Para conservar la base futura, registramos un ingreso técnico de 1 y un egreso técnico de 1.
        insert_movement_db({
            "tipo": "Ingreso",
            "concepto": "Liquidación cobrador",
            "valor": 1,
            "observaciones": (
                f"LIQUIDACION_TECNICA:{cobrador_id} | BASE_PROXIMA:{cobrador_id}:{next_base} | "
                f"Cobrador: {name} | Sin dinero recibido | {observation}"
            ),
            "fecha": today_text(),
            "synced": 0,
            "cobrador_id": CENTRAL_CASH_ID,
        })
        insert_movement_db({
            "tipo": "Egreso",
            "concepto": "Ajuste técnico liquidación",
            "valor": 1,
            "observaciones": f"Compensa liquidación técnica de {name}",
            "fecha": today_text(),
            "synced": 0,
            "cobrador_id": CENTRAL_CASH_ID,
        })

    insert_audit_log(
        "Liquidación cobrador",
        None,
        name,
        f"Base próxima: {money(next_base)}. Recibido: {money(received_cash)}. Diferencia: {money(difference)}. {observation}"
    )
    return {
        "expected": expected,
        "counted": counted,
        "next_base": next_base,
        "should_receive": should_receive,
        "received_cash": received_cash,
        "difference": difference,
    }


def get_cash_closure(date_iso=None):
    """Obtiene la apertura/cierre semanal del cobrador activo."""
    week_start, _ = week_bounds(date_iso)
    owner_id = cash_owner_id() or COBRADOR_ID
    key = cash_period_key(date_iso, owner_id)

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM cierres_caja
        WHERE fecha_iso = ?
          AND COALESCE(periodo_tipo, 'diario') = 'semanal'
          AND COALESCE(cobrador_id, '') = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (key, owner_id),
    )
    row = cursor.fetchone()

    if row is None:
        cursor.execute(
            """
            SELECT * FROM cierres_caja
            WHERE fecha_iso = ?
              AND COALESCE(periodo_tipo, 'diario') = 'semanal'
              AND (COALESCE(cobrador_id, '') = ? OR COALESCE(cobrador_id, '') = '')
            ORDER BY id DESC
            LIMIT 1
            """,
            (week_start, owner_id),
        )
        row = cursor.fetchone()

    conn.close()
    return dict(row) if row else None



def get_journey_status(date_iso=None):
    closure = get_cash_closure(date_iso)
    if not closure:
        return "sin_abrir"
    return closure.get("estado", "sin_abrir")


def open_cash_journey(date_iso=None, opening_cash=None, observation=""):
    if not can_operate_cash():
        raise ValueError("Este usuario no tiene permiso para abrir caja.")

    week_start, week_end = week_bounds(date_iso)
    owner_id = cash_owner_id()
    key = cash_period_key(date_iso, owner_id)
    existing = get_cash_closure(date_iso)

    if existing and existing.get("estado") in ("abierta", "cerrada"):
        raise ValueError("Este cobrador ya tiene caja semanal abierta o cerrada.")

    calculated_opening = suggested_opening_base_for_collector(owner_id)
    if opening_cash is None:
        opening_cash = calculated_opening
    opening_cash = int(opening_cash)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO cierres_caja (
            uuid, fecha_iso, caja_inicial, recaudo, ingresos, egresos,
            saldo_final, pagos, no_pagos, aplazados, estado,
            observacion_apertura, observacion_cierre,
            efectivo_contado, diferencia_caja, estado_cuadre,
            periodo_tipo, periodo_inicio, periodo_fin,
            clientes_activos, cartera_pendiente, prestamos_nuevos, desembolsos,
            opened_at, closed_at, created_at, updated_at, synced,
            sync_status, cobrador_id
        )
        VALUES (?, ?, ?, 0, 0, 0, ?, 0, 0, 0, ?, ?, '', 0, 0, 'sin_arqueo',
                'semanal', ?, ?, 0, 0, 0, 0, ?, '', ?, ?, 0, 'pending', ?)
    """, (
        str(uuid.uuid4()), key, opening_cash, opening_cash, "abierta",
        observation.strip(), week_start, week_end,
        now_text(), now_text(), now_text(), owner_id,
    ))
    conn.commit()
    conn.close()
    return get_cash_closure(date_iso)



def save_cash_closure(date_iso=None, observation="", physical_cash=None):
    if not can_operate_cash():
        raise ValueError("Este usuario no tiene permiso para cerrar caja.")

    week_start, week_end = week_bounds(date_iso)
    existing = get_cash_closure(date_iso)

    if not existing:
        raise ValueError("La caja semanal del cobrador debe abrirse antes de cerrarla.")
    if existing.get("estado") != "abierta":
        raise ValueError("El cierre de esta semana ya fue realizado para este cobrador.")

    metrics = weekly_metrics(date_iso)
    opening_cash = int(existing.get("caja_inicial", 0))
    closing_cash = opening_cash + metrics["income"] + metrics["collected"] - metrics["expenses"]

    if physical_cash is None:
        physical_cash = closing_cash
    physical_cash = int(physical_cash)
    cash_difference = physical_cash - closing_cash

    if cash_difference == 0:
        reconciliation_status = "cuadrada"
    elif cash_difference > 0:
        reconciliation_status = "sobrante"
    else:
        reconciliation_status = "faltante"

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE cierres_caja
        SET recaudo = ?, ingresos = ?, egresos = ?, saldo_final = ?,
            pagos = ?, no_pagos = ?, aplazados = ?, estado = ?,
            observacion_cierre = ?, efectivo_contado = ?,
            diferencia_caja = ?, estado_cuadre = ?,
            periodo_tipo = 'semanal', periodo_inicio = ?, periodo_fin = ?,
            clientes_activos = ?, cartera_pendiente = ?,
            prestamos_nuevos = ?, desembolsos = ?,
            closed_at = ?, updated_at = ?, synced = 0, sync_status = 'pending',
            cobrador_id = ?
        WHERE id = ?
    """, (
        metrics["collected"], metrics["income"], metrics["expenses"], closing_cash,
        len(metrics["payments"]), len(metrics["no_payments"]), len(metrics["postponed"]),
        "cerrada", observation.strip(), physical_cash, cash_difference,
        reconciliation_status, week_start, week_end,
        metrics["active_clients"], metrics["outstanding_portfolio"],
        len(metrics["new_clients"]), metrics["disbursements"],
        now_text(), now_text(), cash_owner_id(), existing.get("id"),
    ))
    conn.commit()
    conn.close()
    return get_cash_closure(date_iso)



def load_weekly_closures():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    owner = active_cobrador_id()
    if owner:
        cursor.execute("""
            SELECT * FROM cierres_caja
            WHERE COALESCE(periodo_tipo, 'diario') = 'semanal'
              AND COALESCE(cobrador_id, '') = ?
            ORDER BY periodo_inicio DESC, id DESC
        """, (owner,))
    else:
        cursor.execute("""
            SELECT * FROM cierres_caja
            WHERE COALESCE(periodo_tipo, 'diario') = 'semanal'
            ORDER BY periodo_inicio DESC, id DESC
        """)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows



def mark_all_as_synced():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE clientes SET synced = 1, sync_status = 'synced', last_sync_at = ?", (now_text(),))
    cursor.execute("UPDATE transacciones SET synced = 1, sync_status = 'synced', last_sync_at = ?", (now_text(),))
    cursor.execute("UPDATE movimientos_caja SET synced = 1, sync_status = 'synced', last_sync_at = ?", (now_text(),))
    cursor.execute("UPDATE cierres_caja SET synced = 1, sync_status = 'synced', last_sync_at = ?", (now_text(),))
    try:
        cursor.execute("UPDATE auditoria_acciones SET synced = 1, sync_status = 'synced', last_sync_at = ?", (now_text(),))
    except Exception:
        pass
    try:
        cursor.execute("UPDATE configuracion_app SET synced = 1, sync_status = 'synced', last_sync_at = ?", (now_text(),))
    except Exception:
        pass
    try:
        cursor.execute("UPDATE usuarios_app SET synced = 1, sync_status = 'synced', last_sync_at = ?", (now_text(),))
    except Exception:
        pass
    conn.commit()
    conn.close()
    refresh_memory_from_db()


def count_pending_sync():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM clientes WHERE synced = 0")
    clientes = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM transacciones WHERE synced = 0")
    tx = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM movimientos_caja WHERE synced = 0")
    mv = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM cierres_caja WHERE synced = 0")
    cierres = cursor.fetchone()[0]
    try:
        cursor.execute("SELECT COUNT(*) FROM auditoria_acciones WHERE synced = 0")
        audit = cursor.fetchone()[0]
    except Exception:
        audit = 0
    try:
        cursor.execute("SELECT COUNT(*) FROM configuracion_app WHERE synced = 0")
        cfg = cursor.fetchone()[0]
    except Exception:
        cfg = 0
    try:
        cursor.execute("SELECT COUNT(*) FROM usuarios_app WHERE synced = 0")
        users = cursor.fetchone()[0]
    except Exception:
        users = 0
    conn.close()
    return clientes + tx + mv + cierres + audit + cfg + users



def set_app_meta(key, value):
    """Guarda una pequeña configuración local, como la última copia en nube."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
        """)
        cursor.execute("""
            INSERT INTO app_meta (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (str(key), str(value or "")))
        conn.commit()
        conn.close()
    except Exception as error:
        print("APP META SET ERROR:", error)


def get_app_meta(key, default=""):
    """Lee una pequeña configuración local."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
        """)
        cursor.execute("SELECT value FROM app_meta WHERE key = ?", (str(key),))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else default
    except Exception as error:
        print("APP META GET ERROR:", error)
        return default


def get_config_value(key, default=""):
    """Lee configuracion funcional del negocio desde SQLite."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS configuracion_app (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
        """)
        cursor.execute("SELECT value FROM configuracion_app WHERE key = ?", (str(key),))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] not in (None, "") else default
    except Exception as error:
        print("CONFIG GET ERROR:", error)
        return default


def set_config_value(key, value):
    """Guarda configuracion funcional del negocio en SQLite."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS configuracion_app (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
        """)
        for name, definition in [
            ("cobrador_id", "TEXT NOT NULL DEFAULT ''"),
            ("synced", "INTEGER NOT NULL DEFAULT 0"),
            ("sync_status", "TEXT NOT NULL DEFAULT 'pending'"),
            ("last_sync_at", "TEXT"),
            ("sync_error", "TEXT"),
        ]:
            ensure_column(cursor, "configuracion_app", name, definition)
        cursor.execute("""
            INSERT INTO configuracion_app (key, value, updated_at, cobrador_id, synced, sync_status)
            VALUES (?, ?, ?, ?, 0, 'pending')
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at,
                cobrador_id = excluded.cobrador_id,
                synced = 0,
                sync_status = 'pending',
                sync_error = ''
        """, (str(key), str(value or "").strip(), now_text(), COBRADOR_ID))
        conn.commit()
        conn.close()
        return True
    except Exception as error:
        print("CONFIG SET ERROR:", error)
        return False


def get_role_pin(role):
    if role == "Administrador":
        return get_config_value("pin_admin", "1234")
    return get_config_value("pin_cobrador", "0000")


def is_admin_role():
    app = App.get_running_app()
    role = str(getattr(app, "current_role", "Administrador") or "Administrador").lower()
    return role in ("administrador", "admin")


def active_cobrador_id():
    """
    ID operativo del cobrador activo.

    En modo dueño único, el administrador también opera caja como cobrador.
    Por eso no devuelve vacío para admin; devuelve su cobrador_id o el
    DUENO_COBRADOR_ID.
    """
    try:
        app = App.get_running_app()
        current_id = str(getattr(app, "current_cobrador_id", "") or "").strip()

        if MODO_DUENO_UNICO:
            return current_id or DUENO_COBRADOR_ID or COBRADOR_ID

        if is_admin_role():
            return ""

        return current_id
    except Exception:
        return DUENO_COBRADOR_ID if MODO_DUENO_UNICO else ""


def active_cobrador_name():
    try:
        app = App.get_running_app()
        return str(getattr(app, "current_user_name", "") or configured_collector_name()).strip()
    except Exception:
        return configured_collector_name()


def normalize_username(value):
    return str(value or "").strip().lower().replace(" ", "_")


def load_app_users(active_only=True):
    """Carga usuarios/cobradores guardados localmente."""
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios_app (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL DEFAULT '',
                nombre TEXT NOT NULL,
                usuario TEXT NOT NULL UNIQUE,
                pin TEXT NOT NULL,
                rol TEXT NOT NULL DEFAULT 'cobrador',
                cobrador_id TEXT NOT NULL DEFAULT '',
                activo INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                synced INTEGER NOT NULL DEFAULT 0,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                last_sync_at TEXT,
                sync_error TEXT
            )
        """)
        sql = "SELECT * FROM usuarios_app"
        if active_only:
            sql += " WHERE activo = 1"
        sql += " ORDER BY CASE WHEN rol='administrador' THEN 0 ELSE 1 END, nombre ASC"
        cursor.execute(sql)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as error:
        print("LOAD USERS ERROR:", error)
        return []


def get_app_user_by_username(usuario):
    usuario = normalize_username(usuario)
    for user in load_app_users(active_only=False):
        if normalize_username(user.get("usuario")) == usuario:
            return user
    return None


def save_app_user(data):
    """Crea o actualiza usuario/cobrador."""
    nombre = str(data.get("nombre") or "").strip()
    usuario = normalize_username(data.get("usuario") or nombre)
    pin = str(data.get("pin") or "").strip()
    rol = str(data.get("rol") or "cobrador").strip().lower()
    activo = 1 if int(data.get("activo", 1) or 0) else 0

    if not nombre or not usuario or not pin:
        raise ValueError("Nombre, usuario y PIN son obligatorios.")

    if rol not in ("administrador", "cobrador"):
        rol = "cobrador"

    conn = get_connection()
    cursor = conn.cursor()
    now = now_text()
    existing = get_app_user_by_username(usuario)

    # Importante para Supabase:
    # en tu nube cobrador_id puede ser UUID. Por eso los cobradores nuevos
    # reciben un UUID real y no el texto del usuario, como "juan".
    if existing and existing.get("cobrador_id"):
        cobrador_id = str(existing.get("cobrador_id")).strip()
    else:
        cobrador_id = str(data.get("cobrador_id") or uuid.uuid4()).strip()

    if existing:
        cursor.execute("""
            UPDATE usuarios_app
            SET nombre=?, pin=?, rol=?, cobrador_id=?, activo=?, updated_at=?, synced=0, sync_status='pending', sync_error=''
            WHERE usuario=?
        """, (nombre, pin, rol, cobrador_id, activo, now, usuario))
    else:
        cursor.execute("""
            INSERT INTO usuarios_app (
                uuid, nombre, usuario, pin, rol, cobrador_id, activo,
                created_at, updated_at, synced, sync_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'pending')
        """, (str(uuid.uuid4()), nombre, usuario, pin, rol, cobrador_id, activo, now, now))
    conn.commit()
    conn.close()
    return True


def deactivate_app_user(usuario):
    usuario = normalize_username(usuario)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE usuarios_app
        SET activo=0, updated_at=?, synced=0, sync_status='pending'
        WHERE usuario=? AND rol <> 'administrador'
    """, (now_text(), usuario))
    conn.commit()
    conn.close()


def load_collectors(active_only=True):
    """Devuelve solo usuarios con rol cobrador para asignación de clientes."""
    users = load_app_users(active_only=active_only)
    return [u for u in users if str(u.get("rol", "")).lower() == "cobrador"]


def collector_label(user):
    """Etiqueta visible para seleccionar cobrador sin mostrar el UUID completo."""
    name = str(user.get("nombre") or "Sin nombre").strip()
    username = str(user.get("usuario") or "").strip()
    return f"{name} ({username})"


def collector_by_label(label):
    for user in load_collectors(active_only=False):
        if collector_label(user) == label:
            return user
    return None


def collector_name_by_id(cobrador_id):
    cobrador_id = str(cobrador_id or "").strip()
    if not cobrador_id:
        return "Sin asignar"
    for user in load_app_users(active_only=False):
        if str(user.get("cobrador_id") or "").strip() == cobrador_id:
            return str(user.get("nombre") or user.get("usuario") or "Cobrador")
    if cobrador_id == COBRADOR_ID:
        return COBRADOR_NOMBRE
    return "Cobrador no identificado"


def collector_summary_data():
    """Resumen gerencial por cobrador: clientes, cartera y recaudo de hoy."""
    collectors = load_collectors(active_only=False)
    summary = []
    today_iso = iso_today()

    for user in collectors:
        cid = str(user.get("cobrador_id") or "").strip()
        clients = [c for c in CLIENTES if str(c.get("cobrador_id") or "").strip() == cid]
        active_clients = [c for c in clients if safe_int(c.get("saldo", 0)) > 0 and safe_int(c.get("pendientes", 0)) > 0]
        cartera = sum(safe_int(c.get("saldo", 0)) for c in active_clients)
        visitas_hoy = [
            c for c in active_clients
            if not c.get("proximo_cobro") or str(c.get("proximo_cobro", ""))[:10] <= today_iso
        ]
        recaudo_hoy = sum(
            safe_int(t.get("valor", 0))
            for t in TRANSACCIONES
            if str(t.get("fecha", ""))[:10] == today_iso
            and str(t.get("cobrador_id") or cid).strip() == cid
            and t.get("tipo") in ("Cuota", "Aporte")
        )
        summary.append({
            "user": user,
            "cobrador_id": cid,
            "clientes": len(clients),
            "activos": len(active_clients),
            "visitas_hoy": len(visitas_hoy),
            "cartera": cartera,
            "recaudo_hoy": recaudo_hoy,
        })

    return summary


def reassign_client_to_collector(cliente_id, collector_user):
    """Reasigna un cliente a otro cobrador y lo deja pendiente por sincronizar."""
    if not collector_user:
        raise ValueError("Seleccione un cobrador válido.")

    new_cobrador_id = str(collector_user.get("cobrador_id") or "").strip()
    if not new_cobrador_id:
        raise ValueError("El cobrador seleccionado no tiene identificador interno.")

    cliente = get_client_by_id(cliente_id)
    if not cliente:
        raise ValueError("Cliente no encontrado.")

    old_cobrador_id = str(cliente.get("cobrador_id") or "").strip()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE clientes
        SET cobrador_id = ?, synced = 0, sync_status = 'pending', updated_at = ?
        WHERE id = ?
    """, (new_cobrador_id, now_text(), int(cliente_id)))
    conn.commit()
    conn.close()

    insert_audit_log(
        "Cliente reasignado",
        cliente,
        "Cambio de cobrador",
        f"De {collector_name_by_id(old_cobrador_id)} a {collector_label(collector_user)}",
    )
    refresh_memory_from_db(clients=True, transactions=False, movements=False, normalize=False)
    return True


def register_successful_cloud_backup():
    """Marca la fecha/hora de la última sincronización completa correcta."""
    timestamp = now_text()
    set_app_meta("last_cloud_backup_at", timestamp)
    return timestamp


def cloud_backup_status_info():
    """
    Información visible para el usuario final sobre copia en nube.
    Muestra el último estado local conocido y los pendientes por subir.
    """
    pending = count_pending_sync()
    last_backup = get_app_meta("last_cloud_backup_at", "")

    if not supabase_configured():
        status = "Nube no configurada"
        detail = "La app trabaja local, pero falta conectar Supabase."
        color = DANGER
    elif pending > 0:
        status = "Pendiente por subir"
        detail = f"Hay {pending} registro(s) pendiente(s) por subir."
        color = GOLD
    elif last_backup:
        status = "Sincronizado"
        detail = "Todos los datos locales están respaldados."
        color = SUCCESS
    else:
        status = "Sin copia registrada"
        detail = "Presiona Carga Completa para crear la primera copia."
        color = GOLD

    return {
        "last_backup": last_backup or "Sin copia registrada",
        "status": status,
        "detail": detail,
        "pending": pending,
        "configured": supabase_configured(),
        "color": color,
    }



def current_cash_balance():
    """
    Saldo disponible real de la caja semanal del cobrador activo.
    Admin obtiene consolidado general, pero no debe registrar operaciones directas.
    """
    try:
        refresh_memory_from_db(
            clients=False,
            transactions=True,
            movements=True,
            normalize=False,
        )
    except Exception:
        pass

    try:
        week_start, week_end = week_bounds()
        closure = get_cash_closure()

        if closure and closure.get("estado") in ("abierta", "cerrada"):
            opening_cash = int(closure.get("caja_inicial", 0) or 0)
        else:
            opening_cash = cash_balance_before_date(week_start)

        transactions = records_for_period(TRANSACCIONES, week_start, week_end)
        movements = records_for_period(MOVIMIENTOS_CAJA, week_start, week_end)

        ingresos = sum(safe_int(m.get("valor", 0)) for m in movements if m.get("tipo") == "Ingreso")
        egresos = sum(safe_int(m.get("valor", 0)) for m in movements if m.get("tipo") == "Egreso")
        recaudos = sum(safe_int(t.get("valor", 0)) for t in transactions if t.get("tipo") in ("Cuota", "Aporte"))

        return opening_cash + ingresos + recaudos - egresos
    except Exception as error:
        print("CURRENT CASH BALANCE ERROR:", error)
        return 0



def update_due_statuses():
    """
    Reabre únicamente clientes que habían PAGADO o abonado y cuya
    próxima fecha de cobro ya llegó.

    Importante:
    - Los clientes en NO PAGO, SIGUIENTE DÍA o REPROGRAMADO no se
      convierten automáticamente a PENDIENTE.
    - Esos estados representan una visita real fallida o aplazada y
      deben conservarse para que aparezcan en el filtro "No pago"
      y en el historial de gestión.
    - Cuando su fecha de nueva visita llega, aparecen en la lista
      principal porque proximo_cobro <= hoy, pero mantienen su estado.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        today = iso_today()

        cursor.execute("""
            UPDATE clientes
            SET estado = 'pendiente',
                ultimo_tipo = 'Pendiente por cobrar',
                updated_at = ?,
                synced = 0
            WHERE estado IN ('pagado', 'aporte')
              AND proximo_cobro IS NOT NULL
              AND proximo_cobro <> ''
              AND proximo_cobro <= ?
              AND pendientes > 0
              AND saldo > 0
        """, (now_text(), today))

        conn.commit()
        conn.close()
    except Exception as error:
        print("ERROR update_due_statuses:", error)



def supabase_configured():
    return (
        SYNC_ENABLED
        and SUPABASE_URL.startswith("http")
        and len(SUPABASE_ANON_KEY) > 20
        and "PEGAR_AQUI" not in SUPABASE_URL
        and "PEGAR_AQUI" not in SUPABASE_ANON_KEY
        and "PEGAR_AQUI" not in COBRADOR_ID
    )


def supabase_request(table_name, payload, method="POST", query_suffix=""):
    if not supabase_configured():
        return False, "Supabase no configurado"

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table_name}{query_suffix}"
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    request = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=SYNC_TIMEOUT_SECONDS, context=SSL_CONTEXT) as response:
            status = response.getcode()
            return (200 <= status < 300), f"HTTP {status}"
    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode("utf-8")
        except Exception:
            detail = str(error)
        return False, f"HTTPError {error.code}: {detail}"
    except ssl.SSLCertVerificationError as error:
        return False, (
            "No se pudo validar el certificado SSL. "
            "Verifique que certifi esté incluido en buildozer.spec. "
            f"Detalle: {error}"
        )
    except Exception as error:
        return False, str(error)



def supabase_get(table_name, filter_by_cobrador=True):
    """
    Descarga datos desde Supabase respetando rol y cobrador activo.

    Reglas:
    - usuarios_app: siempre descarga todos los usuarios para que aparezcan en login.
    - configuracion_app: descarga toda la configuración disponible.
    - Administrador: descarga todo.
    - Cobrador: descarga solo datos de su cobrador_id.
    - Antes de login: descarga todo lo necesario para poder iniciar sesión.
    """
    if not supabase_configured():
        return False, "Supabase no configurado", []

    no_filter_tables = {"usuarios_app", "configuracion_app"}
    should_filter = filter_by_cobrador and table_name not in no_filter_tables

    try:
        app = App.get_running_app()
        authenticated = bool(getattr(app, "authenticated", False))
    except Exception:
        authenticated = False

    query = "?select=*"

    if should_filter and authenticated and not is_admin_role():
        cobrador = active_cobrador_id()
        if cobrador:
            query += f"&cobrador_id=eq.{urllib.parse.quote(str(cobrador), safe='')}"

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table_name}{query}"

    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }

    request = urllib.request.Request(url=url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(request, timeout=SYNC_TIMEOUT_SECONDS, context=SSL_CONTEXT) as response:
            status = response.getcode()
            raw = response.read().decode("utf-8")
            if 200 <= status < 300:
                return True, "OK", json.loads(raw or "[]")
            return False, f"HTTP {status}", []
    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode("utf-8")
        except Exception:
            detail = str(error)
        return False, f"HTTPError {error.code}: {detail}", []
    except Exception as error:
        return False, str(error), []



def repair_local_cloud_client_count():
    """
    Repara diferencias entre Supabase y SQLite usando la nube como fuente
    principal para los clientes ya sincronizados.

    Flujo:
    1. Sube clientes locales pendientes para no perder registros nuevos.
    2. Limpia marcas locales antiguas de eliminación de clientes.
    3. Descarga nuevamente todos los clientes de Supabase.
    4. Actualiza la memoria de la aplicación.
    """
    try:
        # Primero conservar cualquier alta o edición local pendiente.
        upload_ok, upload_message = sync_clients_to_cloud()

        if not upload_ok:
            return False, (
                "No se pudo proteger la información local antes de reparar. "
                f"Detalle: {upload_message}"
            )

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM eliminados
            WHERE entidad = 'cliente'
            """
        )
        removed_marks = cursor.rowcount

        conn.commit()
        conn.close()

        download_ok, download_message = pull_clients_from_cloud()
        refresh_memory_from_db()

        if not download_ok:
            return False, download_message

        return True, (
            f"Reparación completada. "
            f"Marcas locales eliminadas: {removed_marks}. "
            f"{download_message}. "
            f"Total local actual: {len(CLIENTES)}"
        )

    except Exception as error:
        return False, str(error)



def pull_clients_from_cloud():
    """
    Descarga clientes de Supabase incluyendo campos nuevos de base de datos:
    uuid, rutas, sync_status y soft delete.
    """
    ok, msg, rows = supabase_get("clientes")
    if not ok:
        return False, msg

    pending_deleted_client_ids = get_deleted_ids("cliente", only_pending=True)

    all_remote_ids = {
        int(row.get("id"))
        for row in rows
        if row.get("id") is not None
    }

    obsolete_marks_removed = clear_obsolete_deleted_marks("cliente", all_remote_ids)

    rows = [
        row
        for row in rows
        if row.get("id") is not None
        and int(row.get("id")) not in pending_deleted_client_ids
        and int(row.get("is_deleted") or 0) == 0
    ]

    conn = get_connection()
    cursor = conn.cursor()

    remote_ids = set()

    for r in rows:
        client_id = int(r.get("id"))
        remote_ids.add(client_id)

        cursor.execute("""
            INSERT OR REPLACE INTO clientes (
                id, uuid, documento, nombre, telefono, direccion,
                barrio, zona, ruta, orden_visita, producto,
                valor_credito, interes, total_credito, cuota, numero_cuotas,
                saldo, pagadas, pendientes, cobro, estado, ultimo_tipo,
                codeudor_documento, codeudor_nombre, codeudor_movil,
                valor_seguro, beneficiario, obs_seguro, created_at, updated_at,
                proximo_cobro, ultima_fecha_pago, aporte_acumulado,
                synced, sync_status, last_sync_at, sync_error,
                is_deleted, deleted_at, deleted_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'synced', ?, '', ?, ?, ?)
        """, (
            client_id,
            r.get("uuid") or str(uuid.uuid4()),
            r.get("documento", ""),
            r.get("nombre", "SIN NOMBRE"),
            r.get("telefono", ""),
            r.get("direccion", ""),
            r.get("barrio", ""),
            r.get("zona", ""),
            r.get("ruta", ""),
            int(r.get("orden_visita") or 0),
            r.get("producto", "5 - CREDITO EN EFECTIVO"),
            int(r.get("valor_credito") or 0),
            float(r.get("interes") or 0),
            int(r.get("total_credito") or 0),
            int(r.get("cuota") or 0),
            int(r.get("numero_cuotas") or 1),
            int(r.get("saldo") or 0),
            int(r.get("pagadas") or 0),
            int(r.get("pendientes") or 0),
            r.get("cobro", "Diario"),
            r.get("estado", "pendiente"),
            r.get("ultimo_tipo", "Pendiente por cobrar"),
            r.get("codeudor_documento", ""),
            r.get("codeudor_nombre", ""),
            r.get("codeudor_movil", ""),
            int(r.get("valor_seguro") or 0),
            r.get("beneficiario", ""),
            r.get("obs_seguro", ""),
            r.get("created_at", now_text()),
            r.get("updated_at", now_text()),
            r.get("proximo_cobro", ""),
            r.get("ultima_fecha_pago", ""),
            int(r.get("aporte_acumulado") or 0),
            r.get("last_sync_at") or now_text(),
            int(r.get("is_deleted") or 0),
            r.get("deleted_at", "") or "",
            r.get("deleted_reason", "") or "",
        ))
        cursor.execute("UPDATE clientes SET cobrador_id = ? WHERE id = ?", (r.get("cobrador_id") or COBRADOR_ID, client_id))

    active_filter = active_cobrador_id()
    if active_filter:
        cursor.execute(
            """
            SELECT id FROM clientes
            WHERE synced = 1
              AND COALESCE(is_deleted, 0) = 0
              AND COALESCE(cobrador_id, '') = ?
            """,
            (active_filter,),
        )
    else:
        cursor.execute("SELECT id FROM clientes WHERE synced = 1 AND COALESCE(is_deleted, 0) = 0")
    local_synced_ids = {int(row[0]) for row in cursor.fetchall()}

    ids_to_delete = local_synced_ids - remote_ids - pending_deleted_client_ids

    for client_id in ids_to_delete:
        cursor.execute("DELETE FROM transacciones WHERE cliente_id = ?", (client_id,))
        cursor.execute("DELETE FROM clientes WHERE id = ? AND synced = 1", (client_id,))

    conn.commit()
    conn.close()

    return True, (
        f"Clientes descargados: {len(rows)} | "
        f"Eliminados locales: {len(ids_to_delete)} | "
        f"Marcas obsoletas limpiadas: {obsolete_marks_removed}"
    )



def pull_transactions_from_cloud():
    """
    Descarga transacciones desde Supabase incluyendo UUID y estado de sincronización.
    """
    ok, msg, rows = supabase_get("transacciones")
    if not ok:
        return False, msg

    deleted_client_ids = get_deleted_ids("cliente")
    rows = [
        r for r in rows
        if (not r.get("cliente_id") or int(r.get("cliente_id")) not in deleted_client_ids)
        and int(r.get("is_deleted") or 0) == 0
    ]

    conn = get_connection()
    cursor = conn.cursor()

    remote_ids = set()

    for r in rows:
        tx_id = int(r.get("id"))
        remote_ids.add(tx_id)

        cursor.execute("""
            INSERT OR REPLACE INTO transacciones (
                id, uuid, cliente_id, cliente, tipo, valor, metodo, fecha,
                numero_cuotas, saldo_anterior, saldo_nuevo,
                cuotas_pagadas_total, cuotas_pendientes_total,
                observacion, synced, sync_status, last_sync_at, sync_error,
                is_deleted, deleted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'synced', ?, '', ?, ?)
        """, (
            tx_id,
            r.get("uuid") or str(uuid.uuid4()),
            r.get("cliente_id"),
            r.get("cliente", ""),
            r.get("tipo", ""),
            int(r.get("valor") or 0),
            r.get("metodo", ""),
            r.get("fecha", now_text()),
            int(r.get("numero_cuotas") or 0),
            int(r.get("saldo_anterior") or 0),
            int(r.get("saldo_nuevo") or 0),
            int(r.get("cuotas_pagadas_total") or 0),
            int(r.get("cuotas_pendientes_total") or 0),
            r.get("observacion", ""),
            r.get("last_sync_at") or now_text(),
            int(r.get("is_deleted") or 0),
            r.get("deleted_at", "") or "",
        ))

    active_filter = active_cobrador_id()
    if active_filter:
        cursor.execute(
            """
            SELECT id FROM transacciones
            WHERE synced = 1
              AND COALESCE(is_deleted, 0) = 0
              AND COALESCE(cobrador_id, '') = ?
            """,
            (active_filter,),
        )
    else:
        cursor.execute("SELECT id FROM transacciones WHERE synced = 1 AND COALESCE(is_deleted, 0) = 0")
    local_synced_ids = {int(row[0]) for row in cursor.fetchall()}

    ids_to_delete = local_synced_ids - remote_ids

    for tx_id in ids_to_delete:
        cursor.execute("DELETE FROM transacciones WHERE id = ? AND synced = 1", (tx_id,))

    conn.commit()
    conn.close()

    return True, f"Transacciones descargadas: {len(rows)} | Eliminadas locales: {len(ids_to_delete)}"



def pull_movements_from_cloud():
    """
    Descarga movimientos de caja desde Supabase incluyendo UUID y estado de sincronización.
    """
    ok, msg, rows = supabase_get("movimientos_caja")
    if not ok:
        return False, msg

    rows = [r for r in rows if int(r.get("is_deleted") or 0) == 0]

    conn = get_connection()
    cursor = conn.cursor()

    remote_ids = set()

    for r in rows:
        movement_id = int(r.get("id"))
        remote_ids.add(movement_id)

        cursor.execute("""
            INSERT OR REPLACE INTO movimientos_caja (
                id, uuid, tipo, concepto, valor, observaciones, fecha,
                synced, sync_status, last_sync_at, sync_error,
                is_deleted, deleted_at, cobrador_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'synced', ?, '', ?, ?, ?)
        """, (
            movement_id,
            r.get("uuid") or str(uuid.uuid4()),
            r.get("tipo", ""),
            r.get("concepto", ""),
            int(r.get("valor") or 0),
            r.get("observaciones", ""),
            r.get("fecha", today_text()),
            r.get("last_sync_at") or now_text(),
            int(r.get("is_deleted") or 0),
            r.get("deleted_at", "") or "",
            r.get("cobrador_id") or COBRADOR_ID,
        ))

    active_filter = active_cobrador_id()
    if active_filter:
        cursor.execute(
            """
            SELECT id FROM movimientos_caja
            WHERE synced = 1
              AND COALESCE(is_deleted, 0) = 0
              AND COALESCE(cobrador_id, '') = ?
            """,
            (active_filter,),
        )
    else:
        cursor.execute("SELECT id FROM movimientos_caja WHERE synced = 1 AND COALESCE(is_deleted, 0) = 0")
    local_synced_ids = {int(row[0]) for row in cursor.fetchall()}

    ids_to_delete = local_synced_ids - remote_ids

    for movement_id in ids_to_delete:
        cursor.execute("DELETE FROM movimientos_caja WHERE id = ? AND synced = 1", (movement_id,))

    conn.commit()
    conn.close()

    return True, f"Movimientos descargados: {len(rows)} | Eliminados locales: {len(ids_to_delete)}"



def rest_value(value):
    """
    Codifica un valor para filtros REST de Supabase/PostgREST.
    """
    return urllib.parse.quote(str(value or ""), safe="")


def rest_like(value):
    """
    Codifica un valor para filtro ilike de PostgREST.
    """
    return urllib.parse.quote(f"*{value or ''}*", safe="")


def supabase_delete_where(table_name, query_filter):
    """
    Ejecuta DELETE en Supabase usando filtros REST.
    """
    if not supabase_configured():
        return False, "Supabase no configurado"

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table_name}?{query_filter}"

    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    request = urllib.request.Request(
        url=url,
        headers=headers,
        method="DELETE",
    )

    try:
        with urllib.request.urlopen(request, timeout=SYNC_TIMEOUT_SECONDS, context=SSL_CONTEXT) as response:
            status = response.getcode()
            if 200 <= status < 300:
                return True, "OK"
            return False, f"HTTP {status}"
    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode("utf-8")
        except Exception:
            detail = str(error)
        return False, f"HTTPError {error.code}: {detail}"
    except ssl.SSLCertVerificationError as error:
        return False, (
            "No se pudo validar el certificado SSL. "
            "Verifique que certifi esté incluido en buildozer.spec. "
            f"Detalle: {error}"
        )
    except Exception as error:
        return False, str(error)


def delete_remote_client_bundle(cliente):
    """
    Elimina en Supabase:
    - cliente
    - transacciones del cliente
    - movimientos de caja relacionados con el cliente
    - egreso automático del desembolso
    """
    if not cliente or not supabase_configured():
        return False, "Supabase no configurado o cliente vacío"

    cliente_id = int(cliente.get("id"))
    valor_credito = int(cliente.get("valor_credito") or 0)
    nombre_cliente = str(cliente.get("nombre", "")).strip()

    results = []

    # 1. Borrar transacciones asociadas al cliente.
    results.append(supabase_delete_where(
        "transacciones",
        f"cliente_id=eq.{cliente_id}&cobrador_id=eq.{COBRADOR_ID}"
    ))

    # 2. Borrar movimientos cuya observación contenga el nombre del cliente.
    if nombre_cliente:
        results.append(supabase_delete_where(
            "movimientos_caja",
            f"cobrador_id=eq.{COBRADOR_ID}&observaciones=ilike.{rest_like(nombre_cliente)}"
        ))

    # 3. Borrar egreso automático por desembolso del préstamo.
    results.append(supabase_delete_where(
        "movimientos_caja",
        f"cobrador_id=eq.{COBRADOR_ID}&tipo=eq.Egreso&concepto=eq.{rest_value('Desembolso préstamo')}&valor=eq.{valor_credito}"
    ))

    # 4. Borrar cliente.
    results.append(supabase_delete_where(
        "clientes",
        f"id=eq.{cliente_id}&cobrador_id=eq.{COBRADOR_ID}"
    ))

    ok = all(item[0] for item in results)
    msg = " | ".join(item[1] for item in results)

    if ok:
        mark_deleted_synced("cliente", cliente_id)

    return ok, msg



def pull_closures_from_cloud():
    """Descarga aperturas y cierres semanales desde Supabase incluyendo UUID."""
    ok, message, rows = supabase_get("cierres_caja")
    if not ok:
        return False, message

    rows = [row for row in rows if int(row.get("is_deleted") or 0) == 0]

    conn = get_connection()
    cursor = conn.cursor()
    imported = 0

    for row in rows:
        fecha_iso = str(row.get("fecha_iso") or "").strip()
        if not fecha_iso:
            continue

        cursor.execute("""
            INSERT INTO cierres_caja (
                uuid, fecha_iso, caja_inicial, recaudo, ingresos, egresos,
                saldo_final, pagos, no_pagos, aplazados, estado,
                observacion_apertura, observacion_cierre,
                efectivo_contado, diferencia_caja, estado_cuadre,
                periodo_tipo, periodo_inicio, periodo_fin,
                clientes_activos, cartera_pendiente,
                prestamos_nuevos, desembolsos,
                opened_at, closed_at, created_at, updated_at,
                synced, sync_status, last_sync_at, sync_error,
                is_deleted, deleted_at, cobrador_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'synced', ?, '', ?, ?, ?)
            ON CONFLICT(fecha_iso) DO UPDATE SET
                uuid=excluded.uuid,
                caja_inicial=excluded.caja_inicial,
                recaudo=excluded.recaudo,
                ingresos=excluded.ingresos,
                egresos=excluded.egresos,
                saldo_final=excluded.saldo_final,
                pagos=excluded.pagos,
                no_pagos=excluded.no_pagos,
                aplazados=excluded.aplazados,
                estado=excluded.estado,
                observacion_apertura=excluded.observacion_apertura,
                observacion_cierre=excluded.observacion_cierre,
                efectivo_contado=excluded.efectivo_contado,
                diferencia_caja=excluded.diferencia_caja,
                estado_cuadre=excluded.estado_cuadre,
                periodo_tipo=excluded.periodo_tipo,
                periodo_inicio=excluded.periodo_inicio,
                periodo_fin=excluded.periodo_fin,
                clientes_activos=excluded.clientes_activos,
                cartera_pendiente=excluded.cartera_pendiente,
                prestamos_nuevos=excluded.prestamos_nuevos,
                desembolsos=excluded.desembolsos,
                opened_at=excluded.opened_at,
                closed_at=excluded.closed_at,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                synced=1,
                sync_status='synced',
                last_sync_at=excluded.last_sync_at,
                sync_error='',
                is_deleted=excluded.is_deleted,
                deleted_at=excluded.deleted_at,
                cobrador_id=excluded.cobrador_id
        """, (
            row.get("uuid") or str(uuid.uuid4()),
            fecha_iso,
            int(row.get("caja_inicial",0) or 0),
            int(row.get("recaudo",0) or 0),
            int(row.get("ingresos",0) or 0),
            int(row.get("egresos",0) or 0),
            int(row.get("saldo_final",0) or 0),
            int(row.get("pagos",0) or 0),
            int(row.get("no_pagos",0) or 0),
            int(row.get("aplazados",0) or 0),
            row.get("estado","sin_abrir"),
            row.get("observacion_apertura","") or "",
            row.get("observacion_cierre","") or "",
            int(row.get("efectivo_contado",0) or 0),
            int(row.get("diferencia_caja",0) or 0),
            row.get("estado_cuadre","sin_arqueo"),
            row.get("periodo_tipo","semanal"),
            row.get("periodo_inicio",fecha_iso) or fecha_iso,
            row.get("periodo_fin",fecha_iso) or fecha_iso,
            int(row.get("clientes_activos",0) or 0),
            int(row.get("cartera_pendiente",0) or 0),
            int(row.get("prestamos_nuevos",0) or 0),
            int(row.get("desembolsos",0) or 0),
            row.get("opened_at","") or "",
            row.get("closed_at","") or "",
            row.get("created_at",now_text()) or now_text(),
            row.get("updated_at",now_text()) or now_text(),
            row.get("last_sync_at") or now_text(),
            int(row.get("is_deleted") or 0),
            row.get("deleted_at", "") or "",
            row.get("cobrador_id") or COBRADOR_ID,
        ))
        imported += 1

    conn.commit()
    conn.close()
    return True, f"Cierres descargados: {imported}"



def pull_audit_from_cloud():
    """Descarga auditoría desde Supabase."""
    ok, msg, rows = supabase_get("auditoria_acciones")
    if not ok:
        return False, msg

    conn = get_connection()
    cursor = conn.cursor()
    imported = 0

    for r in rows:
        if r.get("id") is None:
            continue

        cursor.execute("""
            INSERT OR REPLACE INTO auditoria_acciones (
                id, uuid, fecha, accion, cliente_id, cliente,
                motivo, detalle, cobrador, synced, sync_status, last_sync_at, sync_error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'synced', ?, '')
        """, (
            int(r.get("id")),
            r.get("uuid") or str(uuid.uuid4()),
            r.get("fecha", now_text()),
            r.get("accion", ""),
            r.get("cliente_id"),
            r.get("cliente", ""),
            r.get("motivo", ""),
            r.get("detalle", ""),
            r.get("cobrador", ""),
            r.get("last_sync_at") or now_text(),
        ))
        imported += 1

    conn.commit()
    conn.close()
    return True, f"Auditoría descargada: {imported}"


def pull_users_from_cloud():
    """Descarga usuarios/cobradores desde Supabase."""
    ok, msg, rows = supabase_get("usuarios_app")
    if not ok:
        return False, msg
    conn = get_connection()
    cursor = conn.cursor()
    imported = 0
    for r in rows:
        usuario = normalize_username(r.get("usuario"))
        if not usuario:
            continue
        cursor.execute("""
            INSERT INTO usuarios_app (
                uuid, nombre, usuario, pin, rol, cobrador_id, activo,
                created_at, updated_at, synced, sync_status, last_sync_at, sync_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'synced', ?, '')
            ON CONFLICT(usuario) DO UPDATE SET
                uuid=excluded.uuid,
                nombre=excluded.nombre,
                pin=excluded.pin,
                rol=excluded.rol,
                cobrador_id=excluded.cobrador_id,
                activo=excluded.activo,
                updated_at=excluded.updated_at,
                synced=1,
                sync_status='synced',
                last_sync_at=excluded.last_sync_at,
                sync_error=''
        """, (
            r.get("uuid") or str(uuid.uuid4()),
            r.get("nombre", ""),
            usuario,
            str(r.get("pin", "")),
            str(r.get("rol", "cobrador")).lower(),
            r.get("cobrador_id") or usuario,
            int(r.get("activo", 1) or 0),
            r.get("created_at", now_text()) or now_text(),
            r.get("updated_at", now_text()) or now_text(),
            r.get("last_sync_at") or now_text(),
        ))
        imported += 1
    conn.commit(); conn.close()
    return True, f"Usuarios descargados: {imported}"


def sync_users_to_cloud():
    """Sube usuarios/cobradores pendientes a Supabase."""
    if not supabase_configured():
        return False, "Supabase no configurado"
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, uuid, nombre, usuario, pin, rol, cobrador_id, activo,
               created_at, updated_at, sync_status, last_sync_at, sync_error
        FROM usuarios_app
        WHERE synced = 0
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    if not rows:
        conn.close()
        return True, "Sin usuarios pendientes"
    for row in rows:
        row["uuid"] = row.get("uuid") or str(uuid.uuid4())
        row["sync_status"] = "pending"
    ok, msg = supabase_request("usuarios_app", rows, query_suffix="?on_conflict=usuario")
    if ok:
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(
            f"UPDATE usuarios_app SET synced=1, sync_status='synced', last_sync_at=?, sync_error='' WHERE id IN ({placeholders})",
            [now_text(), *ids],
        )
        conn.commit()
    else:
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(
            f"UPDATE usuarios_app SET sync_status='error', sync_error=? WHERE id IN ({placeholders})",
            [msg, *ids],
        )
        conn.commit()
    conn.close()
    return ok, msg

def pull_config_from_cloud():
    """Descarga configuración funcional del negocio desde Supabase."""
    ok, msg, rows = supabase_get("configuracion_app")
    if not ok:
        return False, msg

    rows = [row for row in rows if str(row.get("cobrador_id") or COBRADOR_ID) == COBRADOR_ID]

    conn = get_connection()
    cursor = conn.cursor()
    imported = 0

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracion_app (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )
    """)
    for name, definition in [
        ("cobrador_id", "TEXT NOT NULL DEFAULT ''"),
        ("synced", "INTEGER NOT NULL DEFAULT 0"),
        ("sync_status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("last_sync_at", "TEXT"),
        ("sync_error", "TEXT"),
    ]:
        ensure_column(cursor, "configuracion_app", name, definition)

    for row in rows:
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        cursor.execute("""
            INSERT INTO configuracion_app
            (key, value, updated_at, cobrador_id, synced, sync_status, last_sync_at, sync_error)
            VALUES (?, ?, ?, ?, 1, 'synced', ?, '')
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at,
                cobrador_id = excluded.cobrador_id,
                synced = 1,
                sync_status = 'synced',
                last_sync_at = excluded.last_sync_at,
                sync_error = ''
        """, (
            key,
            str(row.get("value") or ""),
            str(row.get("updated_at") or now_text()),
            str(row.get("cobrador_id") or COBRADOR_ID),
            str(row.get("last_sync_at") or now_text()),
        ))
        imported += 1

    conn.commit()
    conn.close()
    return True, f"Configuración descargada: {imported}"

def pull_all_from_cloud():
    """
    Descarga toda la informacion de Supabase hacia SQLite local.
    Ideal para celular nuevo o app recien instalada.
    """
    if not supabase_configured():
        return False, "Supabase no configurado"

    results = [
        pull_clients_from_cloud(),
        pull_transactions_from_cloud(),
        pull_movements_from_cloud(),
        pull_closures_from_cloud(),
        pull_audit_from_cloud(),
        pull_config_from_cloud(),
        pull_users_from_cloud(),
    ]

    refresh_memory_from_db()

    ok = all(item[0] for item in results)
    msg = " | ".join(item[1] for item in results)

    return ok, msg



def sync_clients_to_cloud():
    if not supabase_configured():
        return False, "Supabase no configurado"

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, uuid, documento, nombre, telefono, direccion,
               barrio, zona, ruta, orden_visita, producto,
               valor_credito, interes, total_credito, cuota, numero_cuotas,
               saldo, pagadas, pendientes, cobro, estado, ultimo_tipo,
               codeudor_documento, codeudor_nombre, codeudor_movil,
               valor_seguro, beneficiario, obs_seguro, created_at, updated_at,
               proximo_cobro, ultima_fecha_pago, aporte_acumulado,
               sync_status, last_sync_at, sync_error,
               is_deleted, deleted_at, deleted_reason, cobrador_id
        FROM clientes
        WHERE synced = 0
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    if not rows:
        conn.close()
        return True, "Sin clientes pendientes"

    payload = []
    for row in rows:
        row["cobrador_id"] = row.get("cobrador_id") or active_cobrador_id() or COBRADOR_ID
        row["uuid"] = row.get("uuid") or str(uuid.uuid4())
        row["sync_status"] = "pending"
        payload.append(row)

    ok, msg = supabase_request("clientes", payload)
    if ok:
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(
            f"UPDATE clientes SET synced = 1, sync_status = 'synced', last_sync_at = ?, sync_error = '' WHERE id IN ({placeholders})",
            [now_text(), *ids],
        )
        conn.commit()
    else:
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(
            f"UPDATE clientes SET sync_status = 'error', sync_error = ? WHERE id IN ({placeholders})",
            [msg, *ids],
        )
        conn.commit()

    conn.close()
    return ok, msg



def sync_transactions_to_cloud():
    if not supabase_configured():
        return False, "Supabase no configurado"

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, uuid, cliente_id, cliente, tipo, valor, metodo, fecha,
               numero_cuotas, saldo_anterior, saldo_nuevo,
               cuotas_pagadas_total, cuotas_pendientes_total, observacion,
               sync_status, last_sync_at, sync_error, is_deleted, deleted_at
        FROM transacciones
        WHERE synced = 0
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    if not rows:
        conn.close()
        return True, "Sin transacciones pendientes"

    for row in rows:
        row["cobrador_id"] = row.get("cobrador_id") or active_cobrador_id() or COBRADOR_ID
        row["uuid"] = row.get("uuid") or str(uuid.uuid4())
        row["sync_status"] = "pending"

    ok, msg = supabase_request("transacciones", rows)
    if ok:
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(
            f"UPDATE transacciones SET synced = 1, sync_status = 'synced', last_sync_at = ?, sync_error = '' WHERE id IN ({placeholders})",
            [now_text(), *ids],
        )
        conn.commit()
    else:
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(
            f"UPDATE transacciones SET sync_status = 'error', sync_error = ? WHERE id IN ({placeholders})",
            [msg, *ids],
        )
        conn.commit()

    conn.close()
    return ok, msg



def sync_movements_to_cloud():
    if not supabase_configured():
        return False, "Supabase no configurado"

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, uuid, tipo, concepto, valor, observaciones, fecha,
               sync_status, last_sync_at, sync_error, is_deleted, deleted_at, cobrador_id
        FROM movimientos_caja
        WHERE synced = 0
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    if not rows:
        conn.close()
        return True, "Sin movimientos pendientes"

    for row in rows:
        row["cobrador_id"] = row.get("cobrador_id") or active_cobrador_id() or COBRADOR_ID
        row["uuid"] = row.get("uuid") or str(uuid.uuid4())
        row["sync_status"] = "pending"

    ok, msg = supabase_request("movimientos_caja", rows)
    if ok:
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(
            f"UPDATE movimientos_caja SET synced = 1, sync_status = 'synced', last_sync_at = ?, sync_error = '' WHERE id IN ({placeholders})",
            [now_text(), *ids],
        )
        conn.commit()
    else:
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(
            f"UPDATE movimientos_caja SET sync_status = 'error', sync_error = ? WHERE id IN ({placeholders})",
            [msg, *ids],
        )
        conn.commit()

    conn.close()
    return ok, msg



def sync_closures_to_cloud():
    """Sube aperturas y cierres semanales pendientes a Supabase."""
    if not supabase_configured():
        return False, "Supabase no configurado"

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, uuid, fecha_iso, caja_inicial, recaudo, ingresos, egresos,
               saldo_final, pagos, no_pagos, aplazados, estado,
               observacion_apertura, observacion_cierre,
               efectivo_contado, diferencia_caja, estado_cuadre,
               periodo_tipo, periodo_inicio, periodo_fin,
               clientes_activos, cartera_pendiente,
               prestamos_nuevos, desembolsos,
               opened_at, closed_at, created_at, updated_at,
               sync_status, last_sync_at, sync_error, is_deleted, deleted_at, cobrador_id
        FROM cierres_caja
        WHERE synced = 0
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    if not rows:
        conn.close()
        return True, "Sin cierres pendientes"

    for row in rows:
        row["cobrador_id"] = row.get("cobrador_id") or active_cobrador_id() or COBRADOR_ID
        row["uuid"] = row.get("uuid") or str(uuid.uuid4())
        row["sync_status"] = "pending"

    ok, message = supabase_request(
        "cierres_caja",
        rows,
        query_suffix="?on_conflict=cobrador_id,fecha_iso",
    )

    if ok:
        ids = [int(row["id"]) for row in rows if row.get("id") is not None]
        placeholders = ",".join("?" for _ in ids)
        if ids:
            cursor.execute(
                f"UPDATE cierres_caja SET synced = 1, sync_status = 'synced', last_sync_at = ?, sync_error = '' WHERE id IN ({placeholders})",
                [now_text(), *ids],
            )
        conn.commit()
    else:
        ids = [int(row["id"]) for row in rows if row.get("id") is not None]
        placeholders = ",".join("?" for _ in ids)
        if ids:
            cursor.execute(
                f"UPDATE cierres_caja SET sync_status = 'error', sync_error = ? WHERE id IN ({placeholders})",
                [message, *ids],
            )
        conn.commit()

    conn.close()
    return ok, (f"Cierres subidos: {len(rows)}" if ok else message)



def sync_audit_to_cloud():
    """Sube auditoría pendiente a Supabase."""
    if not supabase_configured():
        return False, "Supabase no configurado"

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, uuid, fecha, accion, cliente_id, cliente,
               motivo, detalle, cobrador, sync_status, last_sync_at, sync_error
        FROM auditoria_acciones
        WHERE synced = 0
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    if not rows:
        conn.close()
        return True, "Sin auditoría pendiente"

    for row in rows:
        row["cobrador_id"] = COBRADOR_ID
        row["uuid"] = row.get("uuid") or str(uuid.uuid4())
        row["sync_status"] = "pending"

    ok, msg = supabase_request("auditoria_acciones", rows)
    if ok:
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(
            f"UPDATE auditoria_acciones SET synced = 1, sync_status = 'synced', last_sync_at = ?, sync_error = '' WHERE id IN ({placeholders})",
            [now_text(), *ids],
        )
        conn.commit()
    else:
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(
            f"UPDATE auditoria_acciones SET sync_status = 'error', sync_error = ? WHERE id IN ({placeholders})",
            [msg, *ids],
        )
        conn.commit()

    conn.close()
    return ok, msg

def sync_config_to_cloud():
    """Sube configuración funcional del negocio a Supabase."""
    if not supabase_configured():
        return False, "Supabase no configurado"

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracion_app (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )
    """)
    for name, definition in [
        ("cobrador_id", "TEXT NOT NULL DEFAULT ''"),
        ("synced", "INTEGER NOT NULL DEFAULT 0"),
        ("sync_status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("last_sync_at", "TEXT"),
        ("sync_error", "TEXT"),
    ]:
        ensure_column(cursor, "configuracion_app", name, definition)

    cursor.execute("""
        SELECT key, value, updated_at, cobrador_id, sync_status, last_sync_at, sync_error
        FROM configuracion_app
        WHERE synced = 0
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    if not rows:
        conn.close()
        return True, "Sin configuración pendiente"

    payload = []
    for row in rows:
        row["cobrador_id"] = row.get("cobrador_id") or COBRADOR_ID
        row["sync_status"] = "pending"
        payload.append(row)

    ok, msg = supabase_request(
        "configuracion_app",
        payload,
        query_suffix="?on_conflict=cobrador_id,key",
    )

    keys = [str(row["key"]) for row in rows]
    placeholders = ",".join("?" for _ in keys)
    if ok:
        cursor.execute(
            f"UPDATE configuracion_app SET synced = 1, sync_status = 'synced', last_sync_at = ?, sync_error = '' WHERE key IN ({placeholders})",
            [now_text(), *keys],
        )
    else:
        cursor.execute(
            f"UPDATE configuracion_app SET sync_status = 'error', sync_error = ? WHERE key IN ({placeholders})",
            [msg, *keys],
        )
    conn.commit()
    conn.close()
    return ok, msg

def sync_all_to_cloud(silent=True):
    """
    Sincronizacion bidireccional basica:
    1. Sube pendientes locales a Supabase.
    2. Descarga registros de Supabase al SQLite local.
    3. Si no hay internet, no borra nada y reintenta despues.
    """
    if not supabase_configured():
        return False, "Supabase no configurado"

    try:
        refresh_memory_from_db()

        push_results = [
            sync_clients_to_cloud(),
            sync_transactions_to_cloud(),
            sync_movements_to_cloud(),
            sync_closures_to_cloud(),
            sync_audit_to_cloud(),
            sync_config_to_cloud(),
            sync_users_to_cloud(),
        ]

        pull_result = pull_all_from_cloud()

        refresh_memory_from_db()

        all_ok = all(item[0] for item in push_results) and pull_result[0]
        message = " | ".join(item[1] for item in push_results + [pull_result])

        return all_ok, message
    except ssl.SSLCertVerificationError as error:
        return False, (
            "No se pudo validar el certificado SSL. "
            "Verifique que certifi esté incluido en buildozer.spec. "
            f"Detalle: {error}"
        )
    except Exception as error:
        return False, str(error)





def configure_mobile_keyboard():
    """
    En Android, reduce el área visible cuando aparece el teclado
    para que los ScrollView puedan seguir desplazándose.
    """
    try:
        Window.softinput_mode = "below_target"
    except Exception as error:
        print("ADVERTENCIA softinput_mode:", error)



def bind_scroll_to_input(scroll_view, widget):
    """
    Cuando un campo recibe foco, desplaza suavemente el ScrollView
    para mantenerlo visible sobre el teclado.
    """
    def _on_focus(instance, focused):
        if focused:
            Clock.schedule_once(
                lambda *_: scroll_view.scroll_to(instance, padding=dp(90), animate=True),
                0.20,
            )

    try:
        widget.bind(focus=_on_focus)
    except Exception:
        pass



class CalendarPopup(Popup):
    """
    Selector de fecha simple y compatible con Windows/Android.
    No requiere librerías externas.
    """

    MONTH_NAMES = [
        "",
        "Enero", "Febrero", "Marzo", "Abril",
        "Mayo", "Junio", "Julio", "Agosto",
        "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]

    WEEK_DAYS = ["L", "M", "M", "J", "V", "S", "D"]

    def __init__(self, initial_date=None, on_select=None, **kwargs):
        self.on_select_callback = on_select

        if isinstance(initial_date, str):
            parsed = None
            for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(initial_date, fmt).date()
                    break
                except ValueError:
                    continue
            initial_date = parsed

        self.selected_date = initial_date or datetime.now().date()
        self.current_year = self.selected_date.year
        self.current_month = self.selected_date.month

        super().__init__(
            title="Seleccionar próxima fecha",
            size_hint=(0.94, None),
            height=dp(520),
            auto_dismiss=False,
            **kwargs,
        )

        self.container = BoxLayout(
            orientation="vertical",
            padding=dp(12),
            spacing=dp(10),
        )
        self.content = self.container
        self.build_calendar()

    def build_calendar(self):
        self.container.clear_widgets()

        navigation = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(46),
            spacing=dp(8),
        )

        previous_button = Button(
            text="<",
            size_hint_x=None,
            width=dp(48),
            background_normal="",
            background_color=BLUE,
            color=WHITE,
            bold=True,
        )
        previous_button.bind(
            on_release=lambda *_: self.change_month(-1)
        )

        month_label = Label(
            text=(
                f"{self.MONTH_NAMES[self.current_month]} "
                f"{self.current_year}"
            ),
            color=WHITE,
            bold=True,
            font_size="16sp",
            halign="center",
            valign="middle",
        )
        month_label.bind(
            size=lambda instance, value: setattr(
                instance, "text_size", value
            )
        )

        next_button = Button(
            text=">",
            size_hint_x=None,
            width=dp(48),
            background_normal="",
            background_color=BLUE,
            color=WHITE,
            bold=True,
        )
        next_button.bind(
            on_release=lambda *_: self.change_month(1)
        )

        navigation.add_widget(previous_button)
        navigation.add_widget(month_label)
        navigation.add_widget(next_button)
        self.container.add_widget(navigation)

        week_header = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(30),
            spacing=dp(4),
        )

        for day_name in self.WEEK_DAYS:
            week_header.add_widget(
                Label(
                    text=day_name,
                    color=GOLD,
                    bold=True,
                    halign="center",
                    valign="middle",
                )
            )

        self.container.add_widget(week_header)

        month_grid = BoxLayout(
            orientation="vertical",
            spacing=dp(4),
        )

        weeks = calendar.monthcalendar(
            self.current_year,
            self.current_month,
        )

        while len(weeks) < 6:
            weeks.append([0] * 7)

        for week in weeks:
            row = BoxLayout(
                orientation="horizontal",
                spacing=dp(4),
            )

            for day_number in week:
                if day_number == 0:
                    row.add_widget(Widget())
                    continue

                candidate = datetime(
                    self.current_year,
                    self.current_month,
                    day_number,
                ).date()

                is_selected = candidate == self.selected_date

                day_button = Button(
                    text=str(day_number),
                    background_normal="",
                    background_color=(
                        GOLD
                        if is_selected
                        else (0.22, 0.25, 0.31, 1)
                    ),
                    color=DARK if is_selected else WHITE,
                    bold=is_selected,
                )
                day_button.bind(
                    on_release=lambda _button, date=candidate:
                    self.select_date(date)
                )
                row.add_widget(day_button)

            month_grid.add_widget(row)

        self.container.add_widget(month_grid)

        actions = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(46),
            spacing=dp(8),
        )

        today_button = Button(
            text="Hoy",
            background_normal="",
            background_color=(0.45, 0.48, 0.55, 1),
            color=WHITE,
            bold=True,
        )
        today_button.bind(
            on_release=lambda *_: self.go_today()
        )

        cancel_button = Button(
            text="Cancelar",
            background_normal="",
            background_color=DANGER,
            color=WHITE,
            bold=True,
        )
        cancel_button.bind(on_release=self.dismiss)

        actions.add_widget(today_button)
        actions.add_widget(cancel_button)
        self.container.add_widget(actions)

    def change_month(self, delta):
        month_index = (
            self.current_year * 12
            + self.current_month
            - 1
            + delta
        )
        self.current_year = month_index // 12
        self.current_month = month_index % 12 + 1
        self.build_calendar()

    def go_today(self):
        today = datetime.now().date()
        self.selected_date = today
        self.current_year = today.year
        self.current_month = today.month
        self.build_calendar()

    def select_date(self, selected_date):
        self.selected_date = selected_date

        if self.on_select_callback:
            self.on_select_callback(selected_date)

        self.dismiss()



# ============================================================
# WIDGETS BASE
# ============================================================


# ============================================================
# ASISTENTE AUTOMÁTICO DE RUTA Y NOTIFICACIONES
# ============================================================


def safe_int(value, default=0):
    try:
        return int(float(value or 0))
    except Exception:
        return default


def days_between_iso(start_iso, end_iso=None):
    """Días entre dos fechas ISO. Si hay error devuelve 0."""
    try:
        if not start_iso:
            return 0
        end_iso = end_iso or iso_today()
        start = datetime.strptime(str(start_iso)[:10], "%Y-%m-%d").date()
        end = datetime.strptime(str(end_iso)[:10], "%Y-%m-%d").date()
        return (end - start).days
    except Exception:
        return 0


def client_no_payment_count(cliente):
    """Cantidad histórica de registros No Pago para priorizar cobranza."""
    try:
        cid = int(cliente.get("id") or 0)
    except Exception:
        cid = 0
    nombre = str(cliente.get("nombre", "") or "").strip().lower()
    total = 0
    for tx in TRANSACCIONES:
        tipo = str(tx.get("tipo", "") or "").lower()
        obs = str(tx.get("observacion", "") or "").lower()
        tx_cid = safe_int(tx.get("cliente_id", 0))
        tx_cliente = str(tx.get("cliente", "") or "").strip().lower()
        same_client = (cid and tx_cid == cid) or (nombre and tx_cliente == nombre)
        if same_client and ("no pago" in tipo or "no pag" in tipo or "no pago" in obs or "no pag" in obs):
            total += 1
    return total


def client_reschedule_count(cliente):
    """Cantidad histórica de visitas reprogramadas o aplazadas."""
    try:
        cid = int(cliente.get("id") or 0)
    except Exception:
        cid = 0
    nombre = str(cliente.get("nombre", "") or "").strip().lower()
    total = 0
    for tx in TRANSACCIONES:
        tipo = str(tx.get("tipo", "") or "").lower()
        obs = str(tx.get("observacion", "") or "").lower()
        tx_cid = safe_int(tx.get("cliente_id", 0))
        tx_cliente = str(tx.get("cliente", "") or "").strip().lower()
        same_client = (cid and tx_cid == cid) or (nombre and tx_cliente == nombre)
        if same_client and ("siguiente" in tipo or "reprogram" in obs or "aplaz" in obs):
            total += 1
    return total



def _client_transactions(cliente):
    """Transacciones asociadas al cliente por id o por nombre."""
    try:
        cid = int(cliente.get("id") or 0)
    except Exception:
        cid = 0

    nombre = str(cliente.get("nombre", "") or "").strip().lower()
    result = []

    for tx in TRANSACCIONES:
        tx_cid = safe_int(tx.get("cliente_id", 0))
        tx_cliente = str(tx.get("cliente", "") or "").strip().lower()
        same_client = (cid and tx_cid == cid) or (nombre and tx_cliente == nombre)
        if same_client:
            result.append(tx)

    return result


def client_payment_count(cliente):
    """Pagos reales registrados: cuotas completas o aportes/abonos con dinero recibido."""
    total = 0

    for tx in _client_transactions(cliente):
        tipo = str(tx.get("tipo", "") or "").lower()
        obs = str(tx.get("observacion", "") or "").lower()
        valor = safe_int(tx.get("valor", 0))

        if valor <= 0:
            continue
        if "no pago" in tipo or "no pag" in tipo or "no pago" in obs or "no pag" in obs:
            continue
        if "siguiente" in tipo or "reprogram" in obs or "aplaz" in obs:
            continue

        if (
            "cuota" in tipo
            or "pago" in tipo
            or "aporte" in tipo
            or "abono" in tipo
        ):
            total += 1

    return total


def client_last_payment_date(cliente):
    """Última fecha en la que hubo dinero recibido del cliente."""
    last_iso = ""

    for tx in _client_transactions(cliente):
        tipo = str(tx.get("tipo", "") or "").lower()
        obs = str(tx.get("observacion", "") or "").lower()
        valor = safe_int(tx.get("valor", 0))

        if valor <= 0:
            continue
        if "no pago" in tipo or "no pag" in tipo or "no pago" in obs or "no pag" in obs:
            continue

        date_iso = record_date_iso(tx.get("fecha", ""))
        if date_iso and date_iso > last_iso:
            last_iso = date_iso

    return last_iso


def client_risk_profile(cliente, status=None):
    """
    Clasificación simple de riesgo para decidir renovación, seguimiento o reducción de monto.
    """
    status = status or cobranza_estado_profesional(cliente)
    dias = safe_int(status.get("dias_atraso", 0))
    saldo = safe_int(cliente.get("saldo", 0))
    no_pagos = client_no_payment_count(cliente)
    aplazamientos = client_reschedule_count(cliente)

    if dias >= 7 or no_pagos >= 4 or saldo >= 700000:
        return {
            "nivel": "Alto",
            "label": "RIESGO ALTO",
            "color": DANGER,
            "motivo": "Atraso fuerte, no pagos frecuentes o saldo alto.",
        }

    if dias >= 3 or no_pagos >= 2 or aplazamientos >= 3 or saldo >= 300000:
        return {
            "nivel": "Medio",
            "label": "RIESGO MEDIO",
            "color": GOLD,
            "motivo": "Requiere seguimiento antes de renovar o aumentar cupo.",
        }

    return {
        "nivel": "Bajo",
        "label": "RIESGO BAJO",
        "color": SUCCESS,
        "motivo": "Comportamiento controlado.",
    }


def client_traffic_light(cliente, status=None):
    """
    Semáforo operativo para decidir trato comercial:
    Verde: cliente confiable.
    Amarillo: cliente con cuidado.
    Rojo: cliente problemático.
    Gris/negro: no renovar.
    """
    status = status or cobranza_estado_profesional(cliente)
    risk = client_risk_profile(cliente, status)
    nivel = str(risk.get("nivel", "Bajo") or "Bajo").lower()
    no_pagos = client_no_payment_count(cliente)
    dias = safe_int(status.get("dias_atraso", 0))
    saldo = safe_int(cliente.get("saldo", 0))
    finished = saldo <= 0 or safe_int(cliente.get("pendientes", 0)) <= 0

    if nivel == "alto" and (no_pagos >= 4 or dias >= 10):
        return {
            "color_nombre": "Gris/Negro",
            "label": "NO RECOMENDADO PARA RENOVAR",
            "descripcion": "Cliente crítico. Revisar antes de entregar nuevo crédito.",
            "color": DARK,
            "grupo": "no_renovar",
        }

    if nivel == "alto" or no_pagos >= 3 or dias >= 7:
        return {
            "color_nombre": "Rojo",
            "label": "SEGUIMIENTO PRIORITARIO",
            "descripcion": "Requiere seguimiento cercano antes de renovar.",
            "color": DANGER,
            "grupo": "rojo",
        }

    if nivel == "medio" or no_pagos >= 1 or dias >= 2:
        return {
            "color_nombre": "Amarillo",
            "label": "CLIENTE EN OBSERVACIÓN",
            "descripcion": "Mantener seguimiento y renovar con control.",
            "color": GOLD,
            "grupo": "amarillo",
        }

    return {
        "color_nombre": "Verde",
        "label": "CLIENTE CONFIABLE",
        "descripcion": "Buen comportamiento operativo.",
        "color": SUCCESS,
        "grupo": "verde",
    }


def traffic_light_distribution(clients=None):
    clients = clients if clients is not None else CLIENTES
    result = {
        "verde": 0,
        "amarillo": 0,
        "rojo": 0,
        "no_renovar": 0,
    }
    for cliente in clients:
        if safe_int(cliente.get("saldo", 0)) <= 0 and str(cliente.get("estado", "")) != "paz_y_salvo":
            continue
        light = client_traffic_light(cliente)
        group = light.get("grupo", "verde")
        if group in result:
            result[group] += 1
    return result


def risky_clients_control():
    """Clientes que requieren atención del dueño o administrador."""
    risky = []
    for cliente in CLIENTES:
        saldo = safe_int(cliente.get("saldo", 0))
        pendientes = safe_int(cliente.get("pendientes", 0))
        if saldo <= 0 or pendientes <= 0:
            continue

        status = cobranza_estado_profesional(cliente)
        no_pagos = client_no_payment_count(cliente)
        dias = safe_int(status.get("dias_atraso", 0))
        light = client_traffic_light(cliente, status)

        reasons = []
        if light.get("grupo") in ("rojo", "no_renovar"):
            reasons.append(light.get("label"))
        if no_pagos > 2:
            reasons.append("Más de 2 no pagos")
        if dias > 7:
            reasons.append("Vencido más de 7 días")
        if saldo >= 500000:
            reasons.append("Saldo alto")

        if reasons:
            risky.append({
                "cliente": cliente,
                "status": status,
                "light": light,
                "reasons": reasons,
                "score": (dias * 10) + (no_pagos * 15) + min(saldo // 10000, 100),
            })

    risky.sort(key=lambda item: item["score"], reverse=True)
    return risky


def money_alert_info(date_iso=None):
    """Alerta gerencial de recaudo real contra recaudo esperado del día."""
    date_iso = date_iso or iso_today()
    metrics = daily_metrics(date_iso)
    expected = safe_int(metrics.get("expected", 0))
    collected = safe_int(metrics.get("collected", 0))
    missing = max(expected - collected, 0)
    effectiveness = round((collected / expected) * 100) if expected > 0 else 100

    now_hour = datetime.now().hour
    is_late_day = now_hour >= 12

    if expected <= 0:
        status = "Sin meta de cobro hoy"
        color = MUTED
        alert = False
    elif effectiveness < 40 and is_late_day:
        status = "ALERTA: recaudo bajo para la hora actual"
        color = DANGER
        alert = True
    elif effectiveness < 70:
        status = "Recaudo por debajo de lo esperado"
        color = GOLD
        alert = True
    else:
        status = "Recaudo controlado"
        color = SUCCESS
        alert = False

    return {
        "expected": expected,
        "collected": collected,
        "missing": missing,
        "effectiveness": effectiveness,
        "status": status,
        "color": color,
        "alert": alert,
    }


def client_behavior_summary(cliente, status=None):
    """Resumen profesional del comportamiento del cliente."""
    status = status or cobranza_estado_profesional(cliente)
    pagos = client_payment_count(cliente)
    no_pagos = client_no_payment_count(cliente)
    aplazamientos = client_reschedule_count(cliente)
    ultimo_pago_iso = client_last_payment_date(cliente)
    riesgo = client_risk_profile(cliente, status)
    semaforo = client_traffic_light(cliente, status)

    ultimo_pago_txt = (
        display_date_from_iso(ultimo_pago_iso)
        if ultimo_pago_iso
        else "Sin pago registrado"
    )

    return {
        "pagos": pagos,
        "no_pagos": no_pagos,
        "aplazamientos": aplazamientos,
        "ultimo_pago": ultimo_pago_txt,
        "riesgo": riesgo["nivel"],
        "riesgo_label": riesgo["label"],
        "riesgo_color": riesgo["color"],
        "riesgo_motivo": riesgo["motivo"],
        "semaforo": semaforo["label"],
        "semaforo_color": semaforo["color"],
        "semaforo_desc": semaforo["descripcion"],
        "resumen_corto": (
            f"Comp.: {pagos} pago(s) · {no_pagos} no pago(s) · "
            f"{aplazamientos} aplaz. · Riesgo: {riesgo['nivel']}"
        ),
        "resumen_largo": (
            f"Pagos cumplidos: {pagos} · No pagos: {no_pagos} · "
            f"Aplazamientos: {aplazamientos} · Último pago: {ultimo_pago_txt}"
        ),
    }


def cobranza_priority_label(cliente, status=None):
    """Etiqueta simple de prioridad operativa para el cobrador."""
    status = status or cobranza_estado_profesional(cliente)
    dias = safe_int(status.get("dias_atraso", 0))
    saldo = safe_int(cliente.get("saldo", 0))
    no_pagos = safe_int(status.get("no_pagos", client_no_payment_count(cliente)))

    if dias >= 5 or no_pagos >= 3 or saldo >= 500000:
        return "PRIORIDAD ALTA"
    if dias >= 2 or no_pagos >= 1 or saldo >= 200000:
        return "PRIORIDAD MEDIA"
    return "PRIORIDAD NORMAL"


def cobranza_sort_key(cliente, status=None, date_iso=None):
    """
    Orden profesional de trabajo de campo:
    1) más vencidos, 2) mayor saldo, 3) más no pagos,
    4) visitas de hoy, 5) reprogramados que ya llegaron.
    """
    date_iso = date_iso or iso_today()
    status = status or cobranza_estado_profesional(cliente, date_iso)
    codigo = status.get("codigo", "")
    dias = safe_int(status.get("dias_atraso", 0))
    saldo = safe_int(cliente.get("saldo", 0))
    no_pagos = safe_int(status.get("no_pagos", client_no_payment_count(cliente)))
    proximo = str(cliente.get("proximo_cobro", "") or "9999-12-31")[:10]

    if codigo in ("vencido", "abono_parcial_vencido", "no_pago_vencido", "reprogramado_vencido"):
        grupo = 0
    elif codigo in ("no_pago_hoy",):
        grupo = 1
    elif codigo in ("pendiente_hoy", "abono_parcial_hoy"):
        grupo = 2
    elif codigo in ("siguiente_dia", "reprogramado_hoy"):
        grupo = 3
    else:
        grupo = 4

    ruta = str(cliente.get("ruta", "") or "").upper()
    orden = safe_int(cliente.get("orden_visita", 0))
    return (grupo, -dias, ruta, orden, -saldo, -no_pagos, proximo, str(cliente.get("nombre", "") or "").upper())


def cobranza_estado_profesional(cliente, date_iso=None):
    """
    Estado operativo del cliente para trabajo de campo.

    La agenda de visitas manda sobre el estado contable:
    - Si tiene saldo y fecha vencida, debe volver a la ruta como VENCIDO.
    - Si no pagó, conserva la cuota pendiente y exige nueva visita.
    - Si fue reprogramado, sale de la lista hasta la nueva fecha.
    - Si llega la nueva fecha, vuelve a salir automáticamente.
    - El verde solo significa cumplido: PAGADO HOY o PAZ Y SALVO.
    """
    date_iso = date_iso or iso_today()
    estado = str(cliente.get("estado", "pendiente") or "pendiente").lower()
    proximo = str(cliente.get("proximo_cobro", "") or "").strip()[:10]
    saldo = safe_int(cliente.get("saldo", 0))
    pendientes = safe_int(cliente.get("pendientes", 0))
    ultimo_tipo = str(cliente.get("ultimo_tipo", "") or "").lower()
    ultima_fecha = record_date_iso(cliente.get("ultima_fecha", "")) or record_date_iso(cliente.get("ultima_fecha_pago", "")) or ""
    no_pagos_hist = client_no_payment_count(cliente)
    reprogramaciones = client_reschedule_count(cliente)

    tiene_aporte = estado == "aporte" or "aporte" in ultimo_tipo or "abono" in ultimo_tipo
    tiene_no_pago = estado == "no_pago" or "no pago" in ultimo_tipo or "no pag" in ultimo_tipo

    base = {
        "dias_atraso": 0,
        "no_pagos": no_pagos_hist,
        "reprogramaciones": reprogramaciones,
    }

    if saldo <= 0 or pendientes <= 0 or estado == "paz_y_salvo":
        return {
            **base,
            "codigo": "paz_y_salvo",
            "label": "PAZ Y SALVO",
            "detalle": "Crédito finalizado",
            "bg": STATUS_PAID_OFF,
            "border": STATUS_BORDER_PAID_OFF,
            "badge_bg": STATUS_BORDER_PAID_OFF,
            "badge_color": WHITE,
            "priority": 90,
        }

    if estado == "pagado" and ultima_fecha == date_iso:
        return {
            **base,
            "codigo": "pagado_hoy",
            "label": "PAGADO HOY",
            "detalle": "Ya cumplió la visita de hoy",
            "bg": STATUS_GREEN,
            "border": STATUS_BORDER_GREEN,
            "badge_bg": STATUS_BORDER_GREEN,
            "badge_color": WHITE,
            "priority": 80,
        }

    # La fecha vencida manda sobre cualquier otro estado.
    if proximo and proximo < date_iso:
        dias = max(days_between_iso(proximo, date_iso), 1)
        common = {**base, "dias_atraso": dias}
        if tiene_aporte:
            return {
                **common,
                "codigo": "abono_parcial_vencido",
                "label": "ABONO PARCIAL - VENCIDO",
                "detalle": f"Visita vencida hace {dias} día(s) · Última visita: {display_date_from_iso(proximo)}",
                "bg": (1.00, 0.94, 0.82, 1),
                "border": GOLD,
                "badge_bg": GOLD,
                "badge_color": DARK,
                "priority": 3,
            }
        if tiene_no_pago:
            return {
                **common,
                "codigo": "no_pago_vencido",
                "label": "NO PAGÓ - VENCIDO",
                "detalle": f"Visita vencida hace {dias} día(s) · No pagos: {no_pagos_hist}",
                "bg": STATUS_RED,
                "border": STATUS_BORDER_RED,
                "badge_bg": STATUS_BORDER_RED,
                "badge_color": WHITE,
                "priority": 1,
            }
        if estado == "siguiente":
            return {
                **common,
                "codigo": "reprogramado_vencido",
                "label": "REPROGRAMADO VENCIDO",
                "detalle": f"Visita vencida hace {dias} día(s) · Reprogramaciones: {reprogramaciones}",
                "bg": STATUS_RED,
                "border": STATUS_BORDER_RED,
                "badge_bg": STATUS_BORDER_RED,
                "badge_color": WHITE,
                "priority": 4,
            }
        return {
            **common,
            "codigo": "vencido",
            "label": "VENCIDO",
            "detalle": f"Visita vencida hace {dias} día(s) · Última visita: {display_date_from_iso(proximo)}",
            "bg": (1.00, 0.90, 0.90, 1),
            "border": DANGER,
            "badge_bg": DANGER,
            "badge_color": WHITE,
            "priority": 0,
        }

    if tiene_no_pago:
        if proximo and proximo > date_iso:
            return {
                **base,
                "codigo": "no_pago_reprogramado",
                "label": "NO PAGÓ - REPROG.",
                "detalle": f"Nueva visita: {display_date_from_iso(proximo)} · No pagos: {no_pagos_hist}",
                "bg": (1.00, 0.93, 0.82, 1),
                "border": GOLD,
                "badge_bg": GOLD,
                "badge_color": DARK,
                "priority": 60,
            }
        return {
            **base,
            "codigo": "no_pago_hoy",
            "label": "NO PAGÓ",
            "detalle": f"Debe gestionarse hoy · No pagos: {no_pagos_hist}",
            "bg": STATUS_RED,
            "border": STATUS_BORDER_RED,
            "badge_bg": STATUS_BORDER_RED,
            "badge_color": WHITE,
            "priority": 10,
        }

    if tiene_aporte:
        if proximo and proximo > date_iso:
            return {
                **base,
                "codigo": "abono_parcial_programado",
                "label": "ABONO PARCIAL",
                "detalle": f"Abono parcial · próxima visita: {display_date_from_iso(proximo)}",
                "bg": (1.00, 0.94, 0.82, 1),
                "border": GOLD,
                "badge_bg": GOLD,
                "badge_color": DARK,
                "priority": 70,
            }
        return {
            **base,
            "codigo": "abono_parcial_hoy",
            "label": "ABONO PARCIAL",
            "detalle": "Debe completar cuota o reprogramar visita",
            "bg": (1.00, 0.94, 0.82, 1),
            "border": GOLD,
            "badge_bg": GOLD,
            "badge_color": DARK,
            "priority": 12,
        }

    if estado == "siguiente":
        if proximo and proximo > date_iso:
            return {
                **base,
                "codigo": "reprogramado_futuro",
                "label": "REPROGRAMADO",
                "detalle": f"Reprogramado para {display_date_from_iso(proximo)}",
                "bg": STATUS_YELLOW,
                "border": STATUS_BORDER_YELLOW,
                "badge_bg": STATUS_BORDER_YELLOW,
                "badge_color": DARK,
                "priority": 65,
            }
        return {
            **base,
            "codigo": "reprogramado_hoy",
            "label": "REPROGRAMADO HOY",
            "detalle": "La visita reprogramada se debe hacer hoy",
            "bg": STATUS_YELLOW,
            "border": STATUS_BORDER_YELLOW,
            "badge_bg": STATUS_BORDER_YELLOW,
            "badge_color": DARK,
            "priority": 15,
        }

    if not proximo or proximo == date_iso:
        return {
            **base,
            "codigo": "pendiente_hoy",
            "label": "PENDIENTE HOY",
            "detalle": "Debe visitarse hoy",
            "bg": STATUS_YELLOW,
            "border": STATUS_BORDER_YELLOW,
            "badge_bg": GOLD,
            "badge_color": DARK,
            "priority": 20,
        }

    return {
        **base,
        "codigo": "programado",
        "label": "PROGRAMADO",
        "detalle": f"Próxima visita: {display_date_from_iso(proximo)}",
        "bg": (0.94, 0.96, 1.0, 1),
        "border": BLUE,
        "badge_bg": BLUE,
        "badge_color": WHITE,
        "priority": 75,
    }


def collection_workload(date_iso=None):
    """Devuelve tablero profesional de visitas para el día."""
    date_iso = date_iso or iso_today()
    active = [
        client for client in CLIENTES
        if safe_int(client.get("saldo", 0)) > 0
        and safe_int(client.get("pendientes", 0)) > 0
        and str(client.get("estado", "")) != "paz_y_salvo"
    ]

    enriched = []
    scheduled_future = []
    for client in active:
        status = cobranza_estado_profesional(client, date_iso)
        proximo = str(client.get("proximo_cobro", "") or "")[:10]
        if not proximo or proximo <= date_iso:
            enriched.append((client, status))
        else:
            scheduled_future.append((client, status))

    overdue_codes = ("vencido", "abono_parcial_vencido", "no_pago_vencido", "reprogramado_vencido")
    today_codes = ("pendiente_hoy", "no_pago_hoy", "reprogramado_hoy", "abono_parcial_hoy")

    overdue = [client for client, status in enriched if status["codigo"] in overdue_codes]
    due_today = [client for client, status in enriched if status["codigo"] in today_codes]
    repeat_no_payments = [client for client, status in enriched if safe_int(status.get("no_pagos", 0)) >= 2]
    high_balance = [client for client, status in enriched if safe_int(client.get("saldo", 0)) >= 200000]

    route_pairs = sorted(enriched, key=lambda item: cobranza_sort_key(item[0], item[1], date_iso))
    route_clients = [client for client, _status in route_pairs]

    critical = route_clients[:3]
    total_due = sum(safe_int(c.get("cuota", 0)) for c in route_clients)
    total_balance = sum(safe_int(c.get("saldo", 0)) for c in route_clients)

    return {
        "overdue": overdue,
        "today": due_today,
        "critical": critical,
        "route_clients": route_clients,
        "scheduled_future": [client for client, _status in scheduled_future],
        "repeat_no_payments": repeat_no_payments,
        "high_balance": high_balance,
        "risk": risk_distribution(route_clients),
        "semaforo": traffic_light_distribution(route_clients),
        "money_alert": money_alert_info(date_iso),
        "count": len(route_clients),
        "expected_today": total_due,
        "balance_in_route": total_balance,
    }


def request_android_notification_permission():
    """
    Solicita el permiso POST_NOTIFICATIONS en Android 13 o superior.

    En Android 12 o versiones anteriores no se necesita solicitar este
    permiso durante la ejecución. En PC y otros sistemas no hace nada.
    """
    if platform != "android":
        return

    try:
        # Importaciones dinámicas: estos módulos solo existen dentro del APK.
        # Así Pylance no los marca como faltantes cuando trabajas desde Windows.
        from importlib import import_module

        jnius_module = import_module("jnius")
        autoclass = jnius_module.autoclass

        BuildVersion = autoclass("android.os.Build$VERSION")
        if int(BuildVersion.SDK_INT) < 33:
            return

        permissions_module = import_module("android.permissions")
        request_permissions = permissions_module.request_permissions

        notification_permission = (
            "android.permission.POST_NOTIFICATIONS"
        )
        request_permissions([notification_permission])

    except Exception as error:
        print(
            "No fue posible solicitar permiso de notificaciones:",
            error,
        )


def send_collection_notification(workload=None):
    """Envía una notificación local al abrir o volver a la app."""
    workload = workload or collection_workload()
    if workload["count"] <= 0:
        return False

    overdue_count = len(workload["overdue"])
    today_count = len(workload["today"])
    title = f"Ruta de cobro: {workload['count']} visita(s)"
    message = (
        f"Vencidas: {overdue_count} · Para hoy: {today_count} · "
        f"Cuotas estimadas: {money(workload['expected_today'])}"
    )

    try:
        if platform == "android":
            # Plyer se carga dinámicamente solo dentro de Android.
            from importlib import import_module

            notification = import_module("plyer").notification
            notification.notify(
                title=title,
                message=message,
                app_name="Cobros V12",
                timeout=12,
            )
            return True
    except Exception as error:
        print("LOCAL NOTIFICATION ERROR:", error)
    return False


class RoundedBox(BoxLayout):
    bg_color = ObjectProperty(WHITE)
    radius = NumericProperty(14)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "padding" not in kwargs:
            self.padding = dp(12)
        if "spacing" not in kwargs:
            self.spacing = dp(8)

        with self.canvas.before:
            Color(*self.bg_color)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[self.radius])

        self.bind(pos=self._update_rect, size=self._update_rect, bg_color=self._update_rect)

    def _update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class Header(BoxLayout):
    def __init__(self, title, show_back=False, on_back=None, show_home=True, show_menu=True, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(66), **kwargs)
        self.padding = [dp(12), dp(8), dp(12), dp(8)]
        self.spacing = dp(8)
        self.title_text = str(title or "")

        with self.canvas.before:
            Color(*BLUE)
            self.bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        if show_back:
            back = Button(
                text="<",
                size_hint_x=None,
                width=dp(42),
                background_normal="",
                background_color=BLUE_DARK,
                color=WHITE,
                bold=True,
                font_size="18sp",
            )
            if on_back:
                back.bind(on_release=lambda *_: on_back())
            self.add_widget(back)

        label = Label(
            text=title,
            color=WHITE,
            bold=True,
            font_size="16sp",
            halign="left",
            valign="middle",
        )
        label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        self.add_widget(label)

        try:
            app = App.get_running_app()
            authenticated = bool(getattr(app, "authenticated", False))
        except Exception:
            app = None
            authenticated = False

        # Accesos rápidos visibles en todas las pantallas internas.
        if authenticated and show_home and self.title_text.strip().lower() != "inicio":
            home_btn = Button(
                text="Inicio",
                size_hint_x=None,
                width=dp(62),
                background_normal="",
                background_color=BLUE_DARK,
                color=WHITE,
                bold=True,
                font_size="11sp",
            )
            home_btn.bind(on_release=lambda *_: app.go("inicio") if app else None)
            self.add_widget(home_btn)

        if authenticated and show_menu:
            menu_btn = Button(
                text="Menu",
                size_hint_x=None,
                width=dp(56),
                background_normal="",
                background_color=GOLD,
                color=DARK,
                bold=True,
                font_size="11sp",
            )
            menu_btn.bind(on_release=self.open_quick_menu)
            self.add_widget(menu_btn)

    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size

    def open_quick_menu(self, *_):
        """Menú rápido global más profesional e intuitivo."""
        app = App.get_running_app()
        is_admin = getattr(app, "current_role", "") == "Administrador"
        user_name = getattr(app, "current_user_name", "") or "Usuario"
        role = getattr(app, "current_role", "") or "Cobrador"

        content = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(10),
        )

        popup = Popup(
            title="",
            content=content,
            size_hint=(0.94, None),
            height=dp(650) if is_admin else dp(560),
            auto_dismiss=True,
            separator_height=0,
        )

        def label(text_value, color=TEXT, bold=False, size="11sp", height=dp(24), halign="left", valign="middle"):
            item = Label(
                text=str(text_value),
                color=color,
                bold=bold,
                font_size=size,
                halign=halign,
                valign=valign,
                size_hint_y=None,
                height=height,
            )
            item.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            return item

        def go_to(screen_name):
            popup.dismiss()
            if screen_name == "logout":
                app.confirm_logout()
            else:
                app.go(screen_name)

        header = RoundedBox(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(82),
            padding=[dp(14), dp(10), dp(14), dp(10)],
            spacing=dp(10),
        )
        header.bg_color = BLUE_DARK

        avatar = Label(
            text=(user_name[:1] or "U").upper(),
            color=WHITE,
            bold=True,
            font_size="20sp",
            size_hint_x=None,
            width=dp(54),
            halign="center",
            valign="middle",
        )
        avatar.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        with avatar.canvas.before:
            Color(*BLUE)
            avatar.bg = RoundedRectangle(pos=avatar.pos, size=avatar.size, radius=[dp(16)])
        avatar.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
        avatar.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))

        header_text = BoxLayout(orientation="vertical", spacing=dp(2))
        header_text.add_widget(label("Menú rápido", WHITE, True, "17sp", dp(26)))
        header_text.add_widget(label(f"{user_name} · {role}", (0.88, 0.92, 1, 1), False, "11sp", dp(22)))
        header_text.add_widget(label("Navega sin devolverte pantalla por pantalla.", (0.78, 0.84, 0.96, 1), False, "9.5sp", dp(22)))
        header.add_widget(avatar)
        header.add_widget(header_text)
        content.add_widget(header)

        scroll = ScrollView(
            do_scroll_x=False,
            bar_width=dp(4),
            scroll_type=["bars", "content"],
        )
        body = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            size_hint_y=None,
            padding=[0, 0, 0, dp(4)],
        )
        body.bind(minimum_height=body.setter("height"))

        def section(title_text):
            box = BoxLayout(
                orientation="vertical",
                size_hint_y=None,
                height=dp(30),
                padding=[dp(2), 0, dp(2), 0],
            )
            box.add_widget(label(title_text.upper(), BLUE_DARK, True, "10sp", dp(30)))
            body.add_widget(box)

        def action_card(title_text, subtitle, screen_name, bg_color, icon_text="•", danger=False):
            card = RoundedBox(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(72),
                padding=[dp(12), dp(9), dp(12), dp(9)],
                spacing=dp(10),
            )
            card.bg_color = (1, 1, 1, 1) if not danger else (1.0, 0.93, 0.93, 1)

            icon = Label(
                text=icon_text,
                color=WHITE,
                bold=True,
                font_size="18sp",
                size_hint_x=None,
                width=dp(44),
                halign="center",
                valign="middle",
            )
            icon.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            with icon.canvas.before:
                Color(*bg_color)
                icon.bg = RoundedRectangle(pos=icon.pos, size=icon.size, radius=[dp(12)])
            icon.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
            icon.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))

            txt = BoxLayout(orientation="vertical", spacing=dp(2))
            txt.add_widget(label(title_text, DANGER if danger else TEXT, True, "12sp", dp(24)))
            txt.add_widget(label(subtitle, MUTED, False, "9.5sp", dp(30), valign="top"))

            arrow = Label(
                text=">",
                color=MUTED,
                bold=True,
                font_size="18sp",
                size_hint_x=None,
                width=dp(22),
                halign="center",
                valign="middle",
            )
            arrow.bind(size=lambda instance, value: setattr(instance, "text_size", value))

            card.add_widget(icon)
            card.add_widget(txt)
            card.add_widget(arrow)
            card.bind(on_touch_down=lambda widget, touch, target=screen_name: (
                go_to(target) if widget.collide_point(*touch.pos) else None
            ))
            body.add_widget(card)

        section("Principal")
        action_card("Inicio", "Volver al tablero principal del día.", "inicio", BLUE_DARK, "I")
        action_card("Clientes", "Buscar, cobrar o revisar clientes pendientes.", "clientes", BLUE, "C")
        action_card("Ruta del día", "Organizar visitas por barrio, ruta y prioridad.", "ruta_dia", BLUE, "R")
        action_card("Nuevo cliente", "Registrar cliente y préstamo nuevo.", "nuevo_cliente", SUCCESS, "+")

        section("Caja y operación")
        action_card("Caja / Resumen", "Apertura, recaudo, movimientos y cierre operativo.", "resumen", GOLD, "$")
        action_card("Pagaron hoy", "Ver clientes cobrados durante la jornada.", "clientes_pagaron_hoy", SUCCESS, "✓")

        if is_admin:
            section("Administración")
            action_card("Asignar clientes", "Reasignar clientes entre cobradores.", "asignar_cobradores", BLUE_DARK, "A")
            action_card("Usuarios / cobradores", "Crear cobradores, cambiar PIN y activar cuentas.", "usuarios", BLUE, "U")
            action_card("Configuración", "Datos del negocio, PIN e información general.", "configuracion", GOLD, "*")
            action_card("Caja Central", "Entregar bases, liquidar cobradores y controlar saldo central.", "caja_central", GOLD, "$")
            action_card("Auditoría", "Revisar cambios sensibles y motivos registrados.", "auditoria", (0.45, 0.48, 0.55, 1), "L")

        section("Sesión")
        action_card("Cerrar sesión", "Salir de la cuenta actual y volver al acceso con PIN.", "logout", DANGER, "X", danger=True)

        scroll.add_widget(body)
        content.add_widget(scroll)

        footer = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(10),
        )
        close_btn = Button(
            text="Cerrar menú",
            background_normal="",
            background_color=(0.45, 0.48, 0.55, 1),
            color=WHITE,
            bold=True,
            font_size="12sp",
        )
        close_btn.bind(on_release=lambda *_: popup.dismiss())
        home_btn = Button(
            text="Ir a Inicio",
            background_normal="",
            background_color=BLUE_DARK,
            color=WHITE,
            bold=True,
            font_size="12sp",
        )
        home_btn.bind(on_release=lambda *_: go_to("inicio"))
        footer.add_widget(close_btn)
        footer.add_widget(home_btn)
        content.add_widget(footer)

        popup.open()


class FieldLabel(Label):
    def __init__(self, text, **kwargs):
        super().__init__(
            text=text,
            color=MUTED,
            size_hint_y=None,
            height=dp(20),
            font_size="12sp",
            halign="left",
            valign="middle",
            **kwargs
        )
        self.bind(size=lambda instance, value: setattr(instance, "text_size", value))


class AppTextInput(TextInput):
    def __init__(self, hint_text="", text="", multiline=False, readonly=False, **kwargs):
        super().__init__(
            hint_text=hint_text,
            text=text,
            multiline=multiline,
            readonly=readonly,
            size_hint_y=None,
            height=dp(44) if not multiline else dp(88),
            background_normal="",
            background_color=(0.93, 0.95, 0.98, 1) if readonly else WHITE,
            foreground_color=TEXT,
            cursor_color=BLUE,
            padding=[dp(10), dp(10), dp(10), dp(10)],
            font_size="14sp",
            **kwargs
        )


class MoneyTextInput(AppTextInput):
    """
    Campo para valores monetarios.
    Permite escribir 500000 y lo convierte a 500.000 automáticamente.
    to_int() ya entiende puntos, así que no rompe los cálculos.
    """
    def __init__(self, hint_text="", text="", readonly=False, **kwargs):
        super().__init__(
            hint_text=hint_text,
            text=str(text) if text not in (None, "") else "",
            readonly=readonly,
            **kwargs
        )
        self._formatting = False
        self.bind(text=self._on_money_text)
        if self.text:
            Clock.schedule_once(lambda *_: self._format_current_text(), 0)

    def _on_money_text(self, *_):
        if self._formatting:
            return
        self._format_current_text()

    def _format_current_text(self):
        raw = str(self.text or "")
        digits = "".join(ch for ch in raw if ch.isdigit())

        if digits == "":
            return

        formatted = format_thousands(int(digits))

        if formatted != raw:
            self._formatting = True
            self.text = formatted
            self.cursor = (len(self.text), 0)
            self._formatting = False


class SmallButton(Button):
    def __init__(self, text, bg_color=BLUE, text_color=WHITE, **kwargs):
        super().__init__(
            text=text,
            size_hint_y=None,
            height=dp(46),
            background_normal="",
            background_color=bg_color,
            color=text_color,
            bold=True,
            font_size="12sp",
            **kwargs
        )


class PillButton(Button):
    def __init__(self, text, bg_color=DARK, **kwargs):
        super().__init__(
            text=text,
            size_hint_y=None,
            height=dp(46),
            background_normal="",
            background_color=bg_color,
            color=WHITE,
            bold=True,
            font_size="12sp",
            **kwargs
        )


class DetailRow(BoxLayout):
    def __init__(self, label, value, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(42),
            spacing=dp(10),
            padding=[dp(2), dp(3), dp(2), dp(3)],
            **kwargs
        )

        left = Label(
            text=str(label),
            color=MUTED,
            bold=True,
            font_size="11.5sp",
            halign="left",
            valign="middle",
            size_hint_x=0.42,
        )
        right = Label(
            text=str(value),
            color=TEXT,
            font_size="11.5sp",
            halign="right",
            valign="middle",
            size_hint_x=0.58,
        )
        left.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        right.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        self.add_widget(left)
        self.add_widget(right)


class NavItem(BoxLayout):
    def __init__(self, app, label, screen, icon_name, active=False, **kwargs):
        super().__init__(orientation="vertical", padding=[dp(6), dp(4), dp(6), dp(4)], spacing=dp(2), **kwargs)
        self.app = app
        self.screen = screen
        bg_color = GOLD if active else (0.91, 0.93, 0.96, 1)

        with self.canvas.before:
            Color(*bg_color)
            self.bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])
        self.bind(pos=self._update_bg, size=self._update_bg)

        source = asset_path(icon_name)
        if source:
            icon = Image(source=source, size_hint_y=None, height=dp(24), allow_stretch=True, keep_ratio=True)
        else:
            icon = Label(text=label[:2].upper(), color=DARK, bold=True, font_size="13sp", size_hint_y=None, height=dp(24))

        text = Label(text=label, color=DARK, bold=active, font_size="11sp", size_hint_y=None, height=dp(22), halign="center")
        text.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        self.add_widget(icon)
        self.add_widget(text)

    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.app.go(self.screen)
            return True
        return super().on_touch_down(touch)



# ============================================================
# SEGURIDAD Y CONFIGURACIÓN
# ============================================================

class LoginPinScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="login", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        # Al llegar al login, actualizar usuarios desde Supabase.
        # Esto permite que un cobrador creado en otro equipo o recién sincronizado
        # aparezca sin tener que cerrar/abrir la app.
        try:
            if supabase_configured():
                pull_users_from_cloud()
                pull_config_from_cloud()
        except Exception as error:
            print("LOGIN USERS PULL ERROR:", error)
        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Acceso seguro"))

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
        content = BoxLayout(orientation="vertical", padding=[dp(18), dp(24), dp(18), dp(24)], spacing=dp(14), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(405), padding=[dp(18), dp(18), dp(18), dp(18)], spacing=dp(12))
        card.bg_color = (0.98, 0.99, 1, 1)

        title = Label(text=business_name(), color=BLUE_DARK, bold=True, font_size="20sp", halign="center", valign="middle", size_hint_y=None, height=dp(42))
        title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        card.add_widget(title)

        subtitle = Label(text="Ingrese usuario y PIN", color=MUTED, font_size="12sp", halign="center", valign="middle", size_hint_y=None, height=dp(34))
        subtitle.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        card.add_widget(subtitle)

        users = load_app_users(active_only=True)
        usernames = [u.get("usuario", "") for u in users if u.get("usuario")]
        if not usernames:
            usernames = ["admin", "pacho"]

        self.user_spinner = Spinner(text=usernames[0], values=usernames, size_hint_y=None, height=dp(46), background_normal="", background_color=(0.92, 0.94, 0.98, 1), color=TEXT, bold=True)
        card.add_widget(self.user_spinner)

        self.pin_input = AppTextInput(hint_text="PIN", multiline=False, password=True)
        self.pin_input.input_filter = "int"
        card.add_widget(self.pin_input)

        login_btn = Button(text="Entrar", background_normal="", background_color=BLUE, color=WHITE, bold=True, size_hint_y=None, height=dp(50))
        login_btn.bind(on_release=lambda *_: self.try_login())
        card.add_widget(login_btn)

        sync_btn = Button(text="Actualizar usuarios desde nube", background_normal="", background_color=GOLD, color=DARK, bold=True, size_hint_y=None, height=dp(46))
        sync_btn.bind(on_release=lambda *_: self.sync_users_login())
        card.add_widget(sync_btn)

        help_label = Label(text="Inicial: admin / 1234 · pacho / 0000\nEl administrador crea nuevos cobradores.", color=MUTED, font_size="10.5sp", halign="center", valign="middle", size_hint_y=None, height=dp(52))
        help_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        card.add_widget(help_label)

        content.add_widget(card)
        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def sync_users_login(self):
        # Primero sube usuarios pendientes y luego descarga la lista completa.
        push_ok, push_msg = sync_users_to_cloud()
        pull_ok, pull_msg = pull_users_from_cloud()
        ok = push_ok and pull_ok
        msg = f"Subida: {push_msg}\nDescarga: {pull_msg}"
        show_popup("Usuarios", msg if ok else f"No se pudieron actualizar usuarios.\n{msg}", height=320)
        self.build()

    def try_login(self):
        usuario = normalize_username(self.user_spinner.text)
        pin = str(self.pin_input.text or "").strip()
        user = get_app_user_by_username(usuario)
        if not user or int(user.get("activo", 0) or 0) != 1:
            show_popup("Usuario inactivo", "Este usuario no existe o está desactivado.", height=240)
            return
        if pin != str(user.get("pin", "")).strip():
            show_popup("PIN incorrecto", "Verifique el PIN e intente nuevamente.", height=230)
            return

        app = App.get_running_app()
        app.current_user = user
        app.current_user_name = user.get("nombre", usuario)
        app.current_username = usuario
        app.current_role = "Administrador" if user.get("rol") == "administrador" else "Cobrador"

        raw_cobrador_id = str(user.get("cobrador_id", "") or "").strip()
        if MODO_DUENO_UNICO and not raw_cobrador_id:
            raw_cobrador_id = DUENO_COBRADOR_ID or COBRADOR_ID

        app.current_cobrador_id = raw_cobrador_id or usuario
        app.authenticated = True

        # Después de iniciar sesión, descargar datos según el rol:
        # admin ve todo; cobrador solo ve lo suyo.
        try:
            pull_clients_from_cloud()
            pull_transactions_from_cloud()
            pull_movements_from_cloud()
            pull_closures_from_cloud()
        except Exception as error:
            print("LOGIN DATA PULL ERROR:", error)

        refresh_memory_from_db(normalize=False)
        app.go("inicio")

        # Aviso operativo justo después del login:
        # solo para cobradores y solo si no han abierto caja.
        Clock.schedule_once(
            lambda *_: app.check_cash_opening_alert(),
            0.8,
        )


class ConfiguracionScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="configuracion", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.build()

    def row_label(self, text_value):
        lbl = Label(text=text_value, color=TEXT, bold=True, font_size="12sp", halign="left", valign="middle", size_hint_y=None, height=dp(24))
        lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        return lbl

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Configuración", show_back=True, on_back=lambda: self.app_ref.go("inicio")))
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
        content = BoxLayout(orientation="vertical", padding=[dp(14), dp(16), dp(14), dp(88)], spacing=dp(14), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(560), padding=[dp(14), dp(14), dp(14), dp(14)], spacing=dp(9))
        card.bg_color = (0.98, 0.99, 1, 1)
        title = Label(text="Datos del negocio", color=BLUE_DARK, bold=True, font_size="16sp", halign="left", valign="middle", size_hint_y=None, height=dp(30))
        title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        card.add_widget(title)

        self.nombre_negocio = AppTextInput(text=get_config_value("nombre_negocio", "COBROS V12 MOBILE"), hint_text="Nombre del negocio")
        self.nombre_cobrador = AppTextInput(text=get_config_value("nombre_cobrador", cobrador_nombre()), hint_text="Nombre del cobrador")
        self.telefono_negocio = AppTextInput(text=get_config_value("telefono_negocio", ""), hint_text="Teléfono del negocio")
        self.ciudad = AppTextInput(text=get_config_value("ciudad", ""), hint_text="Ciudad")
        self.interes_default = AppTextInput(text=get_config_value("interes_default", "20"), hint_text="Interés por defecto")
        self.pin_admin = AppTextInput(text=get_config_value("pin_admin", "1234"), hint_text="PIN administrador", password=True)
        self.pin_cobrador = AppTextInput(text=get_config_value("pin_cobrador", "0000"), hint_text="PIN cobrador", password=True)
        self.pin_admin.input_filter = "int"
        self.pin_cobrador.input_filter = "int"

        for label, widget in [("Nombre del negocio", self.nombre_negocio),("Nombre del cobrador", self.nombre_cobrador),("Teléfono", self.telefono_negocio),("Ciudad", self.ciudad),("Interés por defecto", self.interes_default),("PIN administrador", self.pin_admin),("PIN cobrador", self.pin_cobrador)]:
            card.add_widget(self.row_label(label))
            card.add_widget(widget)

        save_btn = Button(text="Guardar configuración", background_normal="", background_color=SUCCESS, color=WHITE, bold=True, size_hint_y=None, height=dp(50))
        save_btn.bind(on_release=lambda *_: self.save_config())
        card.add_widget(save_btn)
        content.add_widget(card)

        info = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(118), padding=[dp(14), dp(12), dp(14), dp(12)], spacing=dp(6))
        info.bg_color = (0.92, 0.96, 1, 1)
        lbl = Label(text="Roles activos", color=BLUE_DARK, bold=True, font_size="13sp", size_hint_y=None, height=dp(24), halign="left", valign="middle")
        lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        info.add_widget(lbl)
        detail = Label(text="Administrador: configuración, auditoría, cierres y mantenimiento.\nCobrador: ruta, clientes, cobros y caja operativa.", color=TEXT, font_size="11sp", halign="left", valign="top")
        detail.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        info.add_widget(detail)
        content.add_widget(info)

        assign_card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(128), padding=[dp(14), dp(12), dp(14), dp(12)], spacing=dp(8))
        assign_card.bg_color = (0.98, 0.99, 1, 1)
        assign_title = Label(text="Organización de cobradores", color=BLUE_DARK, bold=True, font_size="13sp", size_hint_y=None, height=dp(24), halign="left", valign="middle")
        assign_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        assign_card.add_widget(assign_title)
        assign_btn = Button(text="Asignar clientes a cobradores", background_normal="", background_color=BLUE, color=WHITE, bold=True, size_hint_y=None, height=dp(52))
        assign_btn.bind(on_release=lambda *_: self.app_ref.go("asignar_cobradores"))
        assign_card.add_widget(assign_btn)
        content.add_widget(assign_card)

        logout_card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(112), padding=[dp(14), dp(12), dp(14), dp(12)], spacing=dp(8))
        logout_card.bg_color = (1.0, 0.95, 0.95, 1)
        logout_title = Label(text="Sesión", color=DANGER, bold=True, font_size="13sp", size_hint_y=None, height=dp(24), halign="left", valign="middle")
        logout_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        logout_card.add_widget(logout_title)
        logout_btn = Button(text="Cerrar sesión", background_normal="", background_color=DANGER, color=WHITE, bold=True, size_hint_y=None, height=dp(48))
        logout_btn.bind(on_release=lambda *_: self.app_ref.confirm_logout())
        logout_card.add_widget(logout_btn)
        content.add_widget(logout_card)

        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def save_config(self):
        if len(str(self.pin_admin.text or "").strip()) < 4 or len(str(self.pin_cobrador.text or "").strip()) < 4:
            show_popup("PIN inválido", "Cada PIN debe tener mínimo 4 dígitos.", height=250)
            return
        for key, widget in [("nombre_negocio", self.nombre_negocio),("nombre_cobrador", self.nombre_cobrador),("telefono_negocio", self.telefono_negocio),("ciudad", self.ciudad),("interes_default", self.interes_default),("pin_admin", self.pin_admin),("pin_cobrador", self.pin_cobrador)]:
            set_config_value(key, widget.text)
        show_popup("Configuración guardada", "Los datos del negocio y los PIN fueron actualizados.", height=260)


class BottomNav(BoxLayout):
    def __init__(self, app, active="clientes", **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(66),
            padding=[dp(8), dp(7), dp(8), dp(7)],
            spacing=dp(8),
            **kwargs
        )
        self.app = app

        with self.canvas.before:
            Color(*WHITE)
            self.bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        for key, label, screen, icon_name in [
            ("inicio", "Inicio", "inicio", "inicio.png"),
            ("clientes", "Clientes", "clientes", "clientes.png"),
            ("nuevo", "Nuevo", "nuevo_cliente", "nuevo.png"),
            ("caja", "Caja", "movimientos", "caja.png"),
        ]:
            self.add_widget(NavItem(self.app, label, screen, icon_name, active=(key == active)))

    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size



# ============================================================
# ASIGNACIÓN DE CLIENTES A COBRADORES
# ============================================================

class AsignacionCobradoresScreen(Screen):
    """Panel administrativo para organizar clientes por cobrador."""

    def __init__(self, **kwargs):
        super().__init__(name="asignar_cobradores", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)
        self.selected_collector_label = ""
        self.query = ""

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        refresh_memory_from_db(clients=True, transactions=True, movements=False, normalize=False)
        self.build()

    def label(self, text, color=TEXT, bold=False, size="11sp", height=dp(24), halign="left", valign="middle"):
        item = Label(
            text=str(text),
            color=color,
            bold=bold,
            font_size=size,
            halign=halign,
            valign=valign,
            size_hint_y=None,
            height=height,
        )
        item.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        return item

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(
            Header(
                "Asignar clientes",
                show_back=True,
                on_back=lambda: self.app_ref.go("configuracion"),
            )
        )

        scroll = ScrollView(
            do_scroll_x=False,
            bar_width=dp(4),
            scroll_type=["bars", "content"],
        )
        self.content = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(14), dp(14), dp(92)],
            spacing=dp(14),
            size_hint_y=None,
        )
        self.content.bind(minimum_height=self.content.setter("height"))

        self.build_top_summary()
        self.build_collectors_summary()
        self.build_controls()
        self.build_clients()

        scroll.add_widget(self.content)
        self.root.add_widget(scroll)

    def metric_box(self, title, value, color=TEXT):
        box = RoundedBox(
            orientation="vertical",
            padding=[dp(8), dp(7), dp(8), dp(7)],
            spacing=dp(1),
        )
        box.bg_color = WHITE
        box.add_widget(self.label(title, MUTED, True, "8.6sp", dp(18), halign="center"))
        box.add_widget(self.label(value, color, True, "12sp", dp(26), halign="center"))
        return box

    def build_top_summary(self):
        summary = collector_summary_data()
        total_clients = sum(item["clientes"] for item in summary)
        total_cartera = sum(item["cartera"] for item in summary)
        total_today = sum(item["recaudo_hoy"] for item in summary)

        card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(178),
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(10),
        )
        card.bg_color = (0.92, 0.96, 1, 1)
        card.add_widget(self.label("Panel de asignación", BLUE_DARK, True, "16sp", dp(28)))
        card.add_widget(self.label("Organiza qué clientes pertenecen a cada cobrador.", MUTED, False, "10.5sp", dp(26)))

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(62), spacing=dp(8))
        row.add_widget(self.metric_box("Cobradores", str(len(summary)), BLUE_DARK))
        row.add_widget(self.metric_box("Clientes", str(total_clients), BLUE))
        row.add_widget(self.metric_box("Cartera", money(total_cartera), DANGER if total_cartera else SUCCESS))
        card.add_widget(row)
        card.add_widget(self.label(f"Recaudo de hoy: {money(total_today)}", SUCCESS, True, "11.5sp", dp(26)))
        self.content.add_widget(card)

    def build_collectors_summary(self):
        summary = collector_summary_data()

        card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(58) + max(1, min(len(summary), 8)) * dp(78),
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(8),
        )
        card.bg_color = (0.98, 0.99, 1, 1)
        card.add_widget(self.label("Resumen por cobrador", BLUE_DARK, True, "14sp", dp(28)))

        if not summary:
            card.add_widget(self.label("No hay cobradores activos registrados.", DANGER, True, "12sp", dp(48), halign="center"))
            self.content.add_widget(card)
            return

        for item in summary[:8]:
            user = item["user"]
            row = RoundedBox(
                orientation="vertical",
                size_hint_y=None,
                height=dp(70),
                padding=[dp(10), dp(7), dp(10), dp(7)],
                spacing=dp(2),
            )
            row.bg_color = WHITE
            row.add_widget(self.label(collector_label(user), TEXT, True, "11.2sp", dp(20)))
            row.add_widget(
                self.label(
                    f"Clientes: {item['clientes']}  ·  Activos: {item['activos']}  ·  Visitas hoy: {item['visitas_hoy']}",
                    MUTED,
                    False,
                    "9.5sp",
                    dp(19),
                )
            )
            row.add_widget(
                self.label(
                    f"Cartera: {money(item['cartera'])}  ·  Recaudo hoy: {money(item['recaudo_hoy'])}",
                    BLUE_DARK,
                    True,
                    "9.8sp",
                    dp(19),
                )
            )
            card.add_widget(row)

        if len(summary) > 8:
            card.add_widget(self.label("Hay más cobradores. Usa la pantalla de Usuarios para verlos todos.", GOLD, True, "10sp", dp(28)))

        self.content.add_widget(card)

    def build_controls(self):
        collectors = load_collectors(active_only=True)
        labels = [collector_label(u) for u in collectors]
        if labels and self.selected_collector_label not in labels:
            self.selected_collector_label = labels[0]

        card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(186),
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(10),
        )
        card.bg_color = (0.98, 0.99, 1, 1)
        card.add_widget(self.label("1. Selecciona el cobrador destino", BLUE_DARK, True, "13.5sp", dp(26)))

        self.collector_spinner = Spinner(
            text=self.selected_collector_label or "Seleccione cobrador",
            values=labels or ["Sin cobradores activos"],
            size_hint_y=None,
            height=dp(46),
            background_normal="",
            background_color=(0.92, 0.94, 0.98, 1),
            color=TEXT,
            bold=True,
            font_size="12sp",
        )
        self.collector_spinner.bind(text=self.on_collector_change)
        card.add_widget(self.collector_spinner)

        card.add_widget(self.label("2. Busca el cliente que deseas mover", BLUE_DARK, True, "13.5sp", dp(24)))
        self.search_input = AppTextInput(
            text=self.query,
            hint_text="Nombre, documento, teléfono, barrio o ruta",
            multiline=False,
        )
        self.search_input.bind(text=self.on_query_change)
        card.add_widget(self.search_input)

        self.content.add_widget(card)

    def on_collector_change(self, instance, value):
        self.selected_collector_label = value
        self.refresh_screen_later()

    def on_query_change(self, instance, value):
        self.query = str(value or "").strip().lower()
        self.refresh_screen_later()

    def refresh_screen_later(self):
        Clock.schedule_once(lambda *_: self.build(), 0.08)

    def client_match(self, cliente):
        q = self.query
        if not q:
            return True
        return (
            q in str(cliente.get("nombre", "") or "").lower()
            or q in str(cliente.get("documento", "") or "").lower()
            or q in str(cliente.get("telefono", "") or "").lower()
            or q in str(cliente.get("barrio", "") or "").lower()
            or q in str(cliente.get("ruta", "") or "").lower()
        )

    def build_clients(self):
        collector = collector_by_label(self.selected_collector_label)
        selected_cobrador_id = str(collector.get("cobrador_id") or "").strip() if collector else ""

        clients = [c for c in CLIENTES if self.client_match(c)]
        clients.sort(key=lambda c: (collector_name_by_id(c.get("cobrador_id")), str(c.get("nombre", ""))))

        header = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(84),
            padding=[dp(14), dp(10), dp(14), dp(10)],
            spacing=dp(4),
        )
        header.bg_color = (0.92, 0.96, 1, 1)
        header.add_widget(self.label(f"Clientes encontrados: {len(clients)}", BLUE_DARK, True, "14sp", dp(26)))
        destino = collector_label(collector) if collector else "Sin cobrador seleccionado"
        header.add_widget(self.label(f"Destino: {destino}", MUTED, False, "10.5sp", dp(26)))
        self.content.add_widget(header)

        if not collector:
            empty = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(110), padding=dp(14), spacing=dp(8))
            empty.bg_color = WHITE
            empty.add_widget(self.label("Crea primero un cobrador activo.", DANGER, True, "12sp", dp(44), halign="center"))
            self.content.add_widget(empty)
            return

        if not clients:
            empty = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(110), padding=dp(14), spacing=dp(8))
            empty.bg_color = WHITE
            empty.add_widget(self.label("No hay clientes para mostrar con ese filtro.", MUTED, False, "12sp", dp(44), halign="center"))
            self.content.add_widget(empty)
            return

        for cliente in clients[:80]:
            cid = str(cliente.get("cobrador_id") or "").strip()
            assigned = cid == selected_cobrador_id

            card = RoundedBox(
                orientation="vertical",
                size_hint_y=None,
                height=dp(128),
                padding=[dp(12), dp(10), dp(12), dp(10)],
                spacing=dp(7),
            )
            card.bg_color = (0.90, 0.98, 0.92, 1) if assigned else WHITE

            top = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(34), spacing=dp(8))
            name_box = BoxLayout(orientation="vertical", spacing=dp(1))
            name_box.add_widget(self.label(cliente.get("nombre", "SIN NOMBRE"), TEXT, True, "12sp", dp(18)))
            name_box.add_widget(self.label(f"Actual: {collector_name_by_id(cid)}", BLUE if assigned else MUTED, False, "9.5sp", dp(16)))

            btn = Button(
                text="Ya asignado" if assigned else "Asignar",
                size_hint_x=None,
                width=dp(104),
                background_normal="",
                background_color=(0.72, 0.78, 0.74, 1) if assigned else BLUE,
                color=WHITE,
                bold=True,
                font_size="10.5sp",
            )
            btn.disabled = assigned
            btn.bind(on_release=lambda _, c=cliente, u=collector: self.confirm_assign(c, u))

            top.add_widget(name_box)
            top.add_widget(btn)
            card.add_widget(top)

            details = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(46), spacing=dp(8))
            details.add_widget(self.metric_box("Saldo", money(cliente.get("saldo", 0)), DANGER if safe_int(cliente.get("saldo", 0)) > 0 else SUCCESS))
            details.add_widget(self.metric_box("Barrio", str(cliente.get("barrio", "") or "Sin barrio")[:18], BLUE_DARK))
            details.add_widget(self.metric_box("Ruta", str(cliente.get("ruta", "") or "Sin ruta")[:18], BLUE))
            card.add_widget(details)

            doc_tel = f"Doc: {cliente.get('documento','') or 'N/R'}  ·  Tel: {cliente.get('telefono','') or 'N/R'}"
            card.add_widget(self.label(doc_tel, MUTED, False, "9.5sp", dp(20)))

            self.content.add_widget(card)

        if len(clients) > 80:
            note = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(72), padding=dp(12), spacing=dp(6))
            note.bg_color = (1.0, 0.97, 0.88, 1)
            note.add_widget(self.label("Mostrando 80 clientes.", GOLD, True, "11sp", dp(24)))
            note.add_widget(self.label("Usa el buscador para encontrar uno específico.", MUTED, False, "10sp", dp(24)))
            self.content.add_widget(note)

    def confirm_assign(self, cliente, collector):
        confirm_popup(
            "Reasignar cliente",
            f"¿Asignar a {cliente.get('nombre', 'este cliente')} al cobrador {collector_label(collector)}?",
            lambda: self.assign_client(cliente, collector),
        )

    def assign_client(self, cliente, collector):
        try:
            reassign_client_to_collector(cliente.get("id"), collector)
            sync_clients_to_cloud()
            show_popup("Cliente reasignado", "El cliente quedó asignado y pendiente/sincronizado con Supabase.", height=260)
            self.build()
        except Exception as error:
            show_popup("No se pudo reasignar", str(error), height=300)

# ============================================================
# USUARIOS / COBRADORES
# ============================================================

class UsuariosScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="usuarios", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        # Admin: refrescar lista de usuarios desde Supabase antes de pintar.
        try:
            if supabase_configured():
                pull_users_from_cloud()
        except Exception as error:
            print("USERS SCREEN PULL ERROR:", error)
        self.build()

    def input_box(self, hint, text="", password=False):
        box = AppTextInput(hint_text=hint, text=str(text or ""), multiline=False, password=password)
        return box

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Usuarios / Cobradores", show_back=True, on_back=lambda: self.app_ref.go("configuracion")))

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
        content = BoxLayout(orientation="vertical", padding=[dp(14), dp(14), dp(14), dp(88)], spacing=dp(14), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        form = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(390), padding=[dp(14), dp(14), dp(14), dp(14)], spacing=dp(8))
        form.bg_color = (0.98, 0.99, 1, 1)
        title = Label(text="Nuevo / editar cobrador", color=BLUE_DARK, bold=True, font_size="15sp", halign="left", size_hint_y=None, height=dp(28))
        title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        form.add_widget(title)

        self.nombre_input = self.input_box("Nombre del cobrador")
        self.usuario_input = self.input_box("Usuario. Ej: juan")
        self.pin_input = self.input_box("PIN", password=True)
        self.pin_input.input_filter = "int"
        self.rol_spinner = Spinner(text="cobrador", values=["cobrador", "administrador"], size_hint_y=None, height=dp(44), background_normal="", background_color=(0.92,0.94,0.98,1), color=TEXT, bold=True)
        self.activo_spinner = Spinner(text="Activo", values=["Activo", "Inactivo"], size_hint_y=None, height=dp(44), background_normal="", background_color=(0.92,0.94,0.98,1), color=TEXT, bold=True)

        for w in [self.nombre_input, self.usuario_input, self.pin_input, self.rol_spinner, self.activo_spinner]:
            form.add_widget(w)

        save_btn = Button(text="Guardar usuario", background_normal="", background_color=SUCCESS, color=WHITE, bold=True, size_hint_y=None, height=dp(48))
        save_btn.bind(on_release=lambda *_: self.save_user())
        form.add_widget(save_btn)
        content.add_widget(form)

        users = load_app_users(active_only=False)
        list_height = max(dp(360), dp(76 + (len(users) * 66)))
        list_card = RoundedBox(orientation="vertical", size_hint_y=None, height=list_height, padding=[dp(14), dp(14), dp(14), dp(14)], spacing=dp(8))
        list_card.bg_color = (0.98, 0.99, 1, 1)
        list_title = Label(text="Usuarios registrados", color=BLUE_DARK, bold=True, font_size="15sp", halign="left", size_hint_y=None, height=dp(28))
        list_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        list_card.add_widget(list_title)

        sync_btn = Button(
            text="Actualizar lista desde Supabase",
            background_normal="",
            background_color=GOLD,
            color=DARK,
            bold=True,
            size_hint_y=None,
            height=dp(44),
        )
        sync_btn.bind(on_release=lambda *_: self.refresh_users_from_cloud())
        list_card.add_widget(sync_btn)

        if not users:
            list_card.add_widget(Label(text="No hay usuarios.", color=MUTED, size_hint_y=None, height=dp(36)))
        for user in users:
            row = RoundedBox(orientation="horizontal", size_hint_y=None, height=dp(58), padding=[dp(10), dp(8), dp(10), dp(8)], spacing=dp(8))
            row.bg_color = WHITE
            label = Label(text=f"{user.get('nombre')}\n{user.get('usuario')} · {user.get('rol')} · {'Activo' if int(user.get('activo',0) or 0) else 'Inactivo'}", color=TEXT, font_size="11sp", halign="left", valign="middle")
            label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            edit_btn = Button(text="Editar", size_hint_x=None, width=dp(76), background_normal="", background_color=BLUE, color=WHITE, bold=True, font_size="11sp")
            edit_btn.bind(on_release=lambda _, u=user: self.load_user(u))
            row.add_widget(label)
            row.add_widget(edit_btn)
            list_card.add_widget(row)
        content.add_widget(list_card)

        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def refresh_users_from_cloud(self):
        try:
            push_ok, push_msg = sync_users_to_cloud()
            pull_ok, pull_msg = pull_users_from_cloud()
            self.build()
            show_popup(
                "Usuarios actualizados",
                f"Subida: {push_msg}\nDescarga: {pull_msg}",
                height=310,
            )
        except Exception as error:
            show_popup("Error", str(error), height=280)

    def load_user(self, user):
        self.nombre_input.text = user.get("nombre", "")
        self.usuario_input.text = user.get("usuario", "")
        self.pin_input.text = user.get("pin", "")
        self.rol_spinner.text = user.get("rol", "cobrador")
        self.activo_spinner.text = "Activo" if int(user.get("activo", 0) or 0) else "Inactivo"

    def save_user(self):
        try:
            data = {
                "nombre": self.nombre_input.text,
                "usuario": self.usuario_input.text,
                "pin": self.pin_input.text,
                "rol": self.rol_spinner.text,
                "activo": 1 if self.activo_spinner.text == "Activo" else 0,
            }
            save_app_user(data)
            ok, msg = sync_users_to_cloud()
            try:
                pull_users_from_cloud()
            except Exception as error:
                print("PULL USERS AFTER SAVE ERROR:", error)

            self.nombre_input.text = ""
            self.usuario_input.text = ""
            self.pin_input.text = ""
            self.rol_spinner.text = "cobrador"
            self.activo_spinner.text = "Activo"

            show_popup(
                "Usuario guardado",
                "El usuario/cobrador quedó guardado.\n"
                + ("También quedó sincronizado con Supabase." if ok else f"Quedó local, pero falta sincronizar.\n{msg}"),
                height=320,
            )
            self.build()
        except Exception as error:
            show_popup("No se pudo guardar", str(error), height=290)


# ============================================================
# CLIENTES
# ============================================================

class ClienteCard(RoundedBox):
    def __init__(self, cliente, on_click, **kwargs):
        status = cobranza_estado_profesional(cliente)
        bg_status = status["bg"]
        border_color = status["border"]
        badge_text = status["label"]

        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(176),
            padding=[dp(0), dp(0), dp(12), dp(0)],
            spacing=dp(0),
            **kwargs
        )
        self.bg_color = bg_status
        self.cliente = cliente
        self.on_click = on_click

        side = BoxLayout(size_hint_x=None, width=dp(8))
        with side.canvas.before:
            Color(*border_color)
            side.rect = RoundedRectangle(pos=side.pos, size=side.size, radius=[dp(14), 0, 0, dp(14)])
        side.bind(pos=lambda w, *_: setattr(w.rect, "pos", w.pos))
        side.bind(size=lambda w, *_: setattr(w.rect, "size", w.size))

        body = BoxLayout(orientation="vertical", padding=[dp(12), dp(9), dp(0), dp(9)], spacing=dp(4))

        top = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(34), spacing=dp(8))
        initial = cliente.get("nombre", "C")[0].upper()

        avatar = Label(text=initial, size_hint_x=None, width=dp(34), color=WHITE, bold=True, font_size="16sp")
        with avatar.canvas.before:
            Color(*border_color)
            avatar.bg = RoundedRectangle(pos=avatar.pos, size=avatar.size, radius=[dp(17)])
        avatar.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
        avatar.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))

        name = Label(text=cliente.get("nombre", "SIN NOMBRE"), color=TEXT, bold=True, font_size="13sp", halign="left", valign="middle")
        name.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        badge = Label(
            text=badge_text,
            size_hint_x=None,
            width=dp(118),
            color=status.get("badge_color", WHITE),
            bold=True,
            font_size="8.5sp",
            halign="center",
            valign="middle",
        )
        with badge.canvas.before:
            Color(*status.get("badge_bg", border_color))
            badge.bg = RoundedRectangle(pos=badge.pos, size=badge.size, radius=[dp(12)])
        badge.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
        badge.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))

        top.add_widget(avatar)
        top.add_widget(name)
        top.add_widget(badge)

        amounts = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(26), spacing=dp(8))
        cuota = Label(text=f"Cuota: [b]{money(cliente.get('cuota', 0))}[/b]", markup=True, color=TEXT, font_size="12sp", halign="left")
        saldo = Label(text=f"Saldo: [b]{money(cliente.get('saldo', 0))}[/b]", markup=True, color=TEXT, font_size="12sp", halign="right")
        cuota.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        saldo.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        amounts.add_widget(cuota)
        amounts.add_widget(saldo)

        visita_txt = display_date_from_iso(cliente.get("proximo_cobro", ""))
        extra = Label(
            text=f"Código: {client_code(cliente)} | Ruta: {cliente.get('ruta', '') or 'Sin ruta'} | Orden: {cliente.get('orden_visita', 0) or '-'} | Visita: {visita_txt}",
            color=MUTED,
            font_size="10sp",
            halign="left",
            size_hint_y=None,
            height=dp(18),
        )
        priority_label = cobranza_priority_label(cliente, status)
        behavior = client_behavior_summary(cliente, status)

        status_detail = Label(
            text=f"{status.get('detalle', '')} · {priority_label}",
            color=border_color,
            bold=True,
            font_size="10sp",
            halign="left",
            size_hint_y=None,
            height=dp(18),
        )
        behavior_detail = Label(
            text=f"{behavior['semaforo']} · {behavior['resumen_corto']}",
            color=behavior["semaforo_color"],
            bold=True,
            font_size="9.2sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(24),
        )
        hint = Label(text="Tocar para gestionar", color=BLUE, bold=True, font_size="10sp", halign="left", size_hint_y=None, height=dp(18))
        for label in (extra, status_detail, behavior_detail, hint):
            label.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        body.add_widget(top)
        body.add_widget(amounts)
        body.add_widget(extra)
        body.add_widget(status_detail)
        body.add_widget(behavior_detail)
        body.add_widget(hint)

        self.add_widget(side)
        self.add_widget(body)
        self.bind(on_touch_down=self._pressed)

    def _pressed(self, widget, touch):
        if self.collide_point(*touch.pos):
            self.on_click(self.cliente)
            return True
        return False



class InicioDashboardScreen(Screen):
    """
    Inicio simple para operación diaria.
    """

    def __init__(self, **kwargs):
        super().__init__(name="inicio", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        refresh_clients_cache()
        self.build()

    def make_label(self, text, color=TEXT, bold=False, size="11sp", height=dp(24), halign="left", valign="middle"):
        item = Label(
            text=str(text),
            color=color,
            bold=bold,
            font_size=size,
            halign=halign,
            valign=valign,
            size_hint_y=None,
            height=height,
        )
        item.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        return item

    def metric(self, title, value, color=TEXT):
        box = RoundedBox(
            orientation="vertical",
            padding=[dp(10), dp(8), dp(10), dp(8)],
            spacing=dp(2),
        )
        box.bg_color = WHITE
        box.add_widget(self.make_label(title, MUTED, True, "9sp", dp(18), halign="center"))
        box.add_widget(self.make_label(value, color, True, "14sp", dp(28), halign="center"))
        return box

    def action_button(self, text_value, screen, color):
        btn = Button(
            text=text_value,
            background_normal="",
            background_color=color,
            color=WHITE if color != GOLD else DARK,
            bold=True,
            font_size="12sp",
            size_hint_y=None,
            height=dp(48),
        )
        btn.bind(on_release=lambda *_: self.app_ref.go(screen))
        return btn

    def logout_button(self):
        btn = Button(
            text="Cerrar sesión",
            background_normal="",
            background_color=DANGER,
            color=WHITE,
            bold=True,
            font_size="12sp",
            size_hint_y=None,
            height=dp(48),
        )
        btn.bind(on_release=lambda *_: self.app_ref.confirm_logout())
        return btn

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Inicio"))

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(14), dp(14), dp(88)],
            spacing=dp(14),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        workload = collection_workload()
        money_alert = workload.get("money_alert", money_alert_info())
        risk = workload.get("risk", {})
        no_payments = len(workload.get("repeat_no_payments", []))
        backup = cloud_backup_status_info()

        hero = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(170),
            padding=[dp(14), dp(14), dp(14), dp(14)],
            spacing=dp(10),
        )
        hero.bg_color = BLUE_DARK
        hero.add_widget(self.make_label("HOY", WHITE, True, "18sp", dp(30)))
        hero.add_widget(self.make_label(today_text(), (0.88, 0.92, 1, 1), False, "11sp", dp(22)))
        hero.add_widget(self.make_label(money_alert["status"], GOLD if money_alert["alert"] else SUCCESS, True, "13sp", dp(30)))
        hero.add_widget(self.make_label(f"Nube: {backup['status']} · Pendientes: {backup['pending']}", (0.88, 0.92, 1, 1), True, "10sp", dp(24)))
        content.add_widget(hero)

        today_card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(198),
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(10),
        )
        today_card.bg_color = (0.98, 0.99, 1, 1)
        today_card.add_widget(self.make_label("Resumen del día", DARK, True, "14sp", dp(26)))

        row_1 = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(62), spacing=dp(8))
        row_1.add_widget(self.metric("Visitas", str(workload["count"]), BLUE))
        row_1.add_widget(self.metric("Esperado", money(money_alert["expected"]), TEXT))
        row_1.add_widget(self.metric("Cobrado", money(money_alert["collected"]), SUCCESS))
        today_card.add_widget(row_1)

        row_2 = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(62), spacing=dp(8))
        row_2.add_widget(self.metric("Faltante", money(money_alert["missing"]), money_alert["color"]))
        row_2.add_widget(self.metric("Efectividad", f"{money_alert['effectiveness']}%", money_alert["color"]))
        row_2.add_widget(self.metric("Para hoy", str(len(workload["today"])), BLUE_DARK))
        today_card.add_widget(row_2)
        content.add_widget(today_card)

        alerts = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(176),
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(10),
        )
        alerts.bg_color = (1.0, 0.96, 0.90, 1)
        alerts.add_widget(self.make_label("Alertas", DARK, True, "14sp", dp(26)))

        row_alerts = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(62), spacing=dp(8))
        row_alerts.add_widget(self.metric("Vencidos", str(len(workload["overdue"])), DANGER if workload["overdue"] else SUCCESS))
        row_alerts.add_widget(self.metric("Riesgo alto", str(risk.get("alto", 0)), DANGER))
        row_alerts.add_widget(self.metric("No pagos", str(no_payments), GOLD))
        alerts.add_widget(row_alerts)

        alerts.add_widget(self.make_label("Prioriza vencidos, riesgo alto y no pagos antes de entregar nuevos créditos.", MUTED, False, "10.5sp", dp(38), valign="top"))
        content.add_widget(alerts)

        actions = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(394),
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(10),
        )
        actions.bg_color = (0.98, 0.99, 1, 1)
        actions.add_widget(self.make_label("Acciones", DARK, True, "14sp", dp(26)))

        row_a = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(50))
        row_a.add_widget(self.action_button("Iniciar ruta", "ruta_dia", BLUE_DARK))
        row_a.add_widget(self.action_button("Cobrar cliente", "clientes", BLUE))
        actions.add_widget(row_a)

        row_b = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(50))
        row_b.add_widget(self.action_button("Caja", "resumen", GOLD))
        row_b.add_widget(self.action_button("Cierre", "cierres_semanales", (0.36, 0.40, 0.48, 1)))
        actions.add_widget(row_b)

        row_c = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(50))
        row_c.add_widget(self.action_button("Riesgo", "clientes_riesgo", DANGER))
        row_c.add_widget(self.action_button("Pagaron hoy", "clientes_pagaron_hoy", SUCCESS))
        actions.add_widget(row_c)

        row_d = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(50))
        row_d.add_widget(self.action_button("Configuración", "configuracion", (0.36, 0.40, 0.48, 1)))
        row_d.add_widget(self.action_button("Auditoría", "auditoria", BLUE_DARK))
        actions.add_widget(row_d)

        if is_admin_role():
            row_admin_cash = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(50))
            row_admin_cash.add_widget(self.action_button("Caja Central", "caja_central", GOLD))
            row_admin_cash.add_widget(self.action_button("Resumen Caja", "resumen", BLUE_DARK))
            actions.add_widget(row_admin_cash)

        row_e = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(50))
        row_e.add_widget(self.action_button("Asignar clientes", "asignar_cobradores", BLUE))
        row_e.add_widget(self.action_button("Usuarios", "usuarios", (0.36, 0.40, 0.48, 1)))
        actions.add_widget(row_e)

        row_f = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(50))
        row_f.add_widget(self.logout_button())
        actions.add_widget(row_f)

        content.add_widget(actions)

        scroll.add_widget(content)
        self.root.add_widget(scroll)

        self.nav_container = BoxLayout(size_hint_y=None, height=dp(66))
        self.nav_container.add_widget(BottomNav(self.app_ref, active="inicio"))
        self.root.add_widget(self.nav_container)


class ClientesScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="clientes", **kwargs)
        self.app_ref = None

        self.root = BoxLayout(orientation="vertical")
        self.root.add_widget(Header("::V12:: Lista de Clientes"))

        tools = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(126),
            padding=[dp(12), dp(9), dp(12), dp(9)],
            spacing=dp(8),
        )
        row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(46))

        self.search = TextInput(
            hint_text="Buscar nombre, teléfono, barrio o ruta...",
            multiline=False,
            background_normal="",
            background_color=WHITE,
            foreground_color=TEXT,
            cursor_color=BLUE,
            padding=[dp(10), dp(10), dp(10), dp(10)],
            font_size="14sp",
        )
        self.search.bind(text=lambda *_: self.render_clients())

        all_clients_btn = Button(text="TODOS", size_hint_x=None, width=dp(72), background_normal="", background_color=BLUE, color=WHITE, bold=True, font_size="11sp")
        all_clients_btn.bind(on_release=lambda *_: self.app_ref.go("todos_clientes"))

        summary = Button(text="RES", size_hint_x=None, width=dp(54), background_normal="", background_color=GOLD, color=DARK, bold=True, font_size="12sp")
        summary.bind(on_release=lambda *_: self.app_ref.go("resumen"))

        row.add_widget(self.search)
        row.add_widget(all_clients_btn)
        row.add_widget(summary)
        tools.add_widget(row)

        filter_row = BoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(46),
        )
        self.quick_filter = Spinner(
            text="Pendientes",
            values=[
                "Pendientes",
                "Todos",
                "Vencidos",
                "Para hoy",
                "No pagaron",
                "Alto riesgo",
                "Pagaron hoy",
                "Por barrio",
                "Por ruta",
            ],
            background_normal="",
            background_color=(0.92, 0.94, 0.98, 1),
            color=TEXT,
            bold=True,
            font_size="12sp",
        )
        self.quick_filter.bind(text=lambda *_: self.render_clients())

        route_btn = Button(
            text="Ruta",
            size_hint_x=None,
            width=dp(72),
            background_normal="",
            background_color=BLUE_DARK,
            color=WHITE,
            bold=True,
            font_size="12sp",
        )
        route_btn.bind(on_release=lambda *_: self.app_ref.go("ruta_dia"))

        filter_row.add_widget(self.quick_filter)
        filter_row.add_widget(route_btn)
        tools.add_widget(filter_row)

        self.root.add_widget(tools)

        self.route_alert_container = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(0),
            padding=[dp(12), 0, dp(12), 0],
        )
        self.root.add_widget(self.route_alert_container)

        self.scroll = ScrollView()
        self.client_list = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(18), dp(12), dp(90)],
            spacing=dp(10),
            size_hint_y=None,
        )
        self.client_list.bind(minimum_height=self.client_list.setter("height"))
        self.scroll.add_widget(self.client_list)
        self.root.add_widget(self.scroll)

        self.nav_container = BoxLayout(size_hint_y=None, height=dp(66))
        self.root.add_widget(self.nav_container)

        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()

        # Garantiza que la lista esté alineada con Supabase.
        # Admin descarga todo; cobrador descarga solo su cartera.
        try:
            if supabase_configured():
                sync_clients_to_cloud()
                pull_clients_from_cloud()
        except Exception as error:
            print("CLIENTES SYNC ON ENTER ERROR:", error)

        refresh_clients_cache()

        # Cada vez que se vuelve a la lista principal, limpiar la búsqueda.
        # Así, después de pagar, editar, renovar, eliminar o reajustar,
        # la pantalla vuelve a mostrar la lista normal.
        if self.search.text:
            self.search.text = ""

        # Si el celular está nuevo y no tiene SQLite local,
        # intenta restaurar automáticamente desde Supabase.
        if not CLIENTES and supabase_configured():
            ok, msg = pull_all_from_cloud()
            print("RESTORE FROM CLOUD CLIENTES:", ok, msg)
            refresh_memory_from_db(normalize=True)

        self.nav_container.clear_widgets()
        self.nav_container.add_widget(BottomNav(self.app_ref, active="clientes"))
        # El tablero gerencial ahora vive en la pantalla inicial.
        # La lista queda limpia para trabajar clientes sin saturación visual.
        self.route_alert_container.clear_widgets()
        self.route_alert_container.height = dp(0)
        self.route_alert_container.padding = [dp(12), 0, dp(12), 0]
        self.render_clients()

    def render_route_alert(self):
        """
        Tablero profesional del día.

        Diseño:
        - Encabezado gerencial.
        - Tres indicadores principales.
        - Alerta de efectividad.
        - Semáforo de cartera.
        - Ruta crítica y estado de nube.
        """
        self.route_alert_container.clear_widgets()
        workload = collection_workload()
        money_alert = workload.get("money_alert", money_alert_info())

        def label(text, color=TEXT, bold=False, size="10sp", height=dp(24), halign="left", valign="middle"):
            item = Label(
                text=str(text),
                color=color,
                bold=bold,
                font_size=size,
                halign=halign,
                valign=valign,
                size_hint_y=None,
                height=height,
            )
            item.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            return item

        if workload["count"] <= 0:
            self.route_alert_container.height = dp(126)
            self.route_alert_container.padding = [dp(12), dp(10), dp(12), dp(10)]

            ok_box = RoundedBox(
                orientation="vertical",
                size_hint_y=None,
                height=dp(106),
                padding=[dp(14), dp(12), dp(14), dp(12)],
                spacing=dp(6),
            )
            ok_box.bg_color = (0.90, 0.98, 0.92, 1)
            ok_box.add_widget(label("TRABAJO DE HOY AL DÍA", SUCCESS, True, "13sp", dp(28)))
            ok_box.add_widget(label(f"Sin visitas pendientes. Recaudo hoy: {money(money_alert['collected'])}", TEXT, False, "11sp", dp(34)))
            ok_box.add_widget(label("Puedes revisar cartera, cierres o sincronización.", MUTED, False, "10sp", dp(24)))
            self.route_alert_container.add_widget(ok_box)
            return

        overdue_count = len(workload["overdue"])
        today_count = len(workload["today"])
        semaforo = workload.get("semaforo", {})
        backup = cloud_backup_status_info()

        critical_names = ", ".join(
            [c.get("nombre", "") for c in workload.get("critical", []) if c.get("nombre")]
        ) or "Sin ruta crítica"

        if money_alert.get("alert"):
            panel_bg = (1.0, 0.95, 0.92, 1)
            status_color = money_alert["color"]
        elif overdue_count:
            panel_bg = (1.0, 0.97, 0.90, 1)
            status_color = DANGER
        else:
            panel_bg = (0.93, 0.98, 0.95, 1)
            status_color = SUCCESS

        self.route_alert_container.height = dp(386)
        self.route_alert_container.padding = [dp(12), dp(10), dp(12), dp(12)]

        panel = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(364),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            spacing=dp(9),
        )
        panel.bg_color = panel_bg

        # Encabezado superior
        header = RoundedBox(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(54),
            padding=[dp(12), dp(8), dp(12), dp(8)],
            spacing=dp(8),
        )
        header.bg_color = BLUE_DARK

        header_left = BoxLayout(orientation="vertical", spacing=dp(1))
        header_left.add_widget(label("TABLERO DE COBRO", WHITE, True, "13sp", dp(22)))
        header_left.add_widget(label("Resumen operativo del día", (0.88, 0.92, 1, 1), False, "9.5sp", dp(18)))

        header_right = BoxLayout(orientation="vertical", size_hint_x=0.34, spacing=dp(1))
        header_right.add_widget(label(f"{workload['count']}", GOLD, True, "18sp", dp(24), halign="right"))
        header_right.add_widget(label("VISITAS", (0.88, 0.92, 1, 1), True, "9sp", dp(16), halign="right"))

        header.add_widget(header_left)
        header.add_widget(header_right)
        panel.add_widget(header)

        # Indicadores principales
        stats_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(72),
            spacing=dp(8),
        )

        def stat_card(title, value, color, subtitle=""):
            box = RoundedBox(
                orientation="vertical",
                padding=[dp(8), dp(7), dp(8), dp(7)],
                spacing=dp(1),
            )
            box.bg_color = WHITE
            box.add_widget(label(title, MUTED, True, "8.8sp", dp(18), halign="center"))
            box.add_widget(label(value, color, True, "12sp", dp(24), halign="center"))
            box.add_widget(label(subtitle, MUTED, False, "8.2sp", dp(16), halign="center"))
            return box

        stats_row.add_widget(
            stat_card(
                "VENCIDOS",
                str(overdue_count),
                DANGER if overdue_count else SUCCESS,
                "prioridad",
            )
        )
        stats_row.add_widget(
            stat_card(
                "PARA HOY",
                str(today_count),
                BLUE,
                "agenda",
            )
        )
        stats_row.add_widget(
            stat_card(
                "ESPERADO",
                money(workload["expected_today"]),
                DARK,
                "recaudo",
            )
        )
        panel.add_widget(stats_row)

        # Recaudo y faltante
        money_box = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(82),
            padding=[dp(10), dp(8), dp(10), dp(8)],
            spacing=dp(4),
        )
        money_box.bg_color = WHITE

        money_title = label(
            money_alert["status"],
            status_color,
            True,
            "11sp",
            dp(22),
            halign="left",
        )
        money_box.add_widget(money_title)

        money_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(42),
            spacing=dp(6),
        )
        money_row.add_widget(label(f"Debías\n{money(money_alert['expected'])}", TEXT, True, "9.5sp", dp(42), halign="center"))
        money_row.add_widget(label(f"Cobrado\n{money(money_alert['collected'])}", SUCCESS, True, "9.5sp", dp(42), halign="center"))
        money_row.add_widget(label(f"Faltan\n{money(money_alert['missing'])}", money_alert["color"], True, "9.5sp", dp(42), halign="center"))
        money_row.add_widget(label(f"Efect.\n{money_alert['effectiveness']}%", money_alert["color"], True, "9.5sp", dp(42), halign="center"))
        money_box.add_widget(money_row)
        panel.add_widget(money_box)

        # Semáforo
        sem_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(6),
        )

        def mini_sem(title, value, color):
            box = RoundedBox(
                orientation="vertical",
                padding=[dp(6), dp(5), dp(6), dp(5)],
                spacing=dp(1),
            )
            box.bg_color = WHITE
            box.add_widget(label(title, color, True, "8.2sp", dp(16), halign="center"))
            box.add_widget(label(str(value), color, True, "12sp", dp(18), halign="center"))
            return box

        sem_row.add_widget(mini_sem("Verde", semaforo.get("verde", 0), SUCCESS))
        sem_row.add_widget(mini_sem("Amarillo", semaforo.get("amarillo", 0), GOLD))
        sem_row.add_widget(mini_sem("Rojo", semaforo.get("rojo", 0), DANGER))
        sem_row.add_widget(mini_sem("No renovar", semaforo.get("no_renovar", 0), DARK))
        panel.add_widget(sem_row)

        # Ruta crítica
        critical_box = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(52),
            padding=[dp(10), dp(7), dp(10), dp(7)],
            spacing=dp(2),
        )
        critical_box.bg_color = WHITE
        critical_box.add_widget(label("RUTA CRÍTICA", MUTED, True, "8.8sp", dp(16)))
        critical_box.add_widget(label(critical_names, DANGER if overdue_count else BLUE, True, "10sp", dp(24), valign="top"))
        panel.add_widget(critical_box)

        # Pie del tablero
        footer = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(28),
            spacing=dp(8),
        )
        footer.add_widget(label(f"Nube: {backup['status']}", backup["color"], True, "9.2sp", dp(28)))
        footer.add_widget(label(f"Pendientes: {backup['pending']}", backup["color"], True, "9.2sp", dp(28), halign="right"))
        panel.add_widget(footer)

        self.route_alert_container.add_widget(panel)

    def clear_search(self):
        """Limpia el buscador y actualiza la lista principal."""
        if self.search.text:
            self.search.text = ""
        self.render_clients()

    def confirm_clear(self):
        confirm_popup("Limpiar datos", "Esto borrará clientes, pagos y movimientos.\nLa app quedará vacía para uso personal.", self.clear_all)

    def clear_all(self):
        clear_all_data_db()
        self.search.text = ""
        self.render_clients()
        show_popup("Datos limpiados", "La app quedó vacía para uso personal.")

    def render_clients(self):
        if not self.app_ref:
            return

        query = (self.search.text or "").strip().lower()
        active_filter = getattr(self, "quick_filter", None).text if hasattr(self, "quick_filter") else "Pendientes"
        self.client_list.clear_widgets()

        filtered = [
            cliente for cliente in CLIENTES
            if client_matches_quick_filter(cliente, active_filter, query)
        ]

        if active_filter not in ("Todos", "Pagaron hoy"):
            filtered = [
                cliente for cliente in filtered
                if int(cliente.get("pendientes", 0)) > 0
                and int(cliente.get("saldo", 0)) > 0
            ]

        if active_filter == "Por barrio" and not query:
            empty_hint = "Escribe el barrio en el buscador."
        elif active_filter == "Por ruta" and not query:
            empty_hint = "Escribe la ruta en el buscador."
        else:
            empty_hint = "Prueba otro filtro o busca por nombre, documento, barrio o ruta."

        filtered.sort(key=lambda cliente: cobranza_sort_key(cliente))

        if not filtered:
            empty_box = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(176), padding=dp(14), spacing=dp(8))
            empty_title = f"Sin resultados en: {active_filter}"
            empty_message = empty_hint

            title = Label(
                text=empty_title,
                color=TEXT,
                bold=True,
                font_size="15sp",
                halign="center",
                size_hint_y=None,
                height=dp(30),
            )
            msg = Label(
                text=empty_message,
                color=MUTED,
                font_size="12sp",
                halign="center",
                valign="middle",
            )
            btn = SmallButton("Crear nuevo cliente", bg_color=BLUE)
            btn.bind(on_release=lambda *_: self.app_ref.go("nuevo_cliente"))
            title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            msg.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            empty_box.add_widget(title)
            empty_box.add_widget(msg)
            empty_box.add_widget(btn)
            self.client_list.add_widget(empty_box)
            return

        header = RoundedBox(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(54),
            padding=[dp(12), dp(8), dp(12), dp(8)],
            spacing=dp(8),
        )
        header.bg_color = (0.92, 0.96, 1, 1)

        left = Label(
            text=f"Filtro: {active_filter}",
            color=BLUE_DARK,
            bold=True,
            font_size="12sp",
            halign="left",
            valign="middle",
        )
        right = Label(
            text=f"{len(filtered)} cliente(s)",
            color=TEXT,
            bold=True,
            font_size="12sp",
            halign="right",
            valign="middle",
        )
        left.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        right.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        header.add_widget(left)
        header.add_widget(right)
        self.client_list.add_widget(header)

        for cliente in filtered:
            self.client_list.add_widget(ClienteCard(cliente, self.open_client))

    def open_client(self, cliente):
        self.app_ref.selected_client = cliente
        self.app_ref.go("gestion_cliente")


class TodosClientesScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="todos_clientes", **kwargs)
        self.app_ref = None
        self.current_filter = "todos"

        root = BoxLayout(orientation="vertical")
        root.add_widget(Header("Todos los Clientes", show_back=True, on_back=self.go_back))

        top = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(252),
            padding=[dp(12), dp(12), dp(12), dp(10)],
            spacing=dp(10),
        )

        self.search = TextInput(
            hint_text="Buscar por nombre, documento o teléfono...",
            multiline=False,
            background_normal="",
            background_color=WHITE,
            foreground_color=TEXT,
            cursor_color=BLUE,
            padding=[dp(10), dp(10), dp(10), dp(10)],
            font_size="14sp",
        )
        self.search.bind(text=lambda *_: self.render_clients())
        top.add_widget(self.search)

        # Métricas rápidas
        metrics_wrap = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, height=dp(96))
        self.metrics_row_1 = BoxLayout(orientation="horizontal", spacing=dp(8))
        self.metrics_row_2 = BoxLayout(orientation="horizontal", spacing=dp(8))
        metrics_wrap.add_widget(self.metrics_row_1)
        metrics_wrap.add_widget(self.metrics_row_2)
        top.add_widget(metrics_wrap)

        filters = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, height=dp(70))
        self.filter_row_1 = BoxLayout(orientation="horizontal", spacing=dp(6))
        self.filter_row_2 = BoxLayout(orientation="horizontal", spacing=dp(6))
        filters.add_widget(self.filter_row_1)
        filters.add_widget(self.filter_row_2)
        top.add_widget(filters)

        actions = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
        )

        restore_button = Button(
            text="Restaurar desde nube",
            background_normal="",
            background_color=SUCCESS,
            color=WHITE,
            bold=True,
            font_size="12sp",
        )
        restore_button.bind(
            on_release=lambda *_: self.confirm_cloud_restore()
        )

        refresh_button = Button(
            text="Actualizar lista",
            background_normal="",
            background_color=BLUE,
            color=WHITE,
            bold=True,
            font_size="12sp",
        )
        refresh_button.bind(
            on_release=lambda *_: self.refresh_local_list()
        )

        actions.add_widget(restore_button)
        actions.add_widget(refresh_button)
        top.add_widget(actions)

        root.add_widget(top)

        self.info_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(28), padding=[dp(14), 0, dp(14), 0])
        self.result_info = Label(text="", color=MUTED, font_size="11sp", halign="left", valign="middle")
        self.result_info.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        self.info_row.add_widget(self.result_info)
        root.add_widget(self.info_row)

        self.scroll = ScrollView()
        self.client_list = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(4), dp(12), dp(84)],
            spacing=dp(10),
            size_hint_y=None,
        )
        self.client_list.bind(minimum_height=self.client_list.setter("height"))
        self.scroll.add_widget(self.client_list)
        root.add_widget(self.scroll)

        self.add_widget(root)

    def go_back(self, *_):
        if self.app_ref:
            self.app_ref.go("clientes")

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        refresh_clients_cache()
        self.build_filters()
        self.render_metrics()
        self.render_clients()

    def refresh_local_list(self):
        refresh_clients_cache()
        self.render_metrics()
        self.render_clients()

    def confirm_cloud_restore(self):
        confirm_popup(
            "Restaurar clientes",
            "Se volverán a descargar los clientes existentes en Supabase.\n\n"
            "Los clientes locales nuevos se subirán primero para evitar pérdidas.",
            self.restore_clients_from_cloud,
        )

    def restore_clients_from_cloud(self):
        if not supabase_configured():
            show_popup(
                "Supabase no configurado",
                "No se puede restaurar desde la nube.",
            )
            return

        show_popup(
            "Restauración iniciada",
            "La app está conciliando la base local con Supabase.\n"
            "La lista se actualizará al terminar.",
            height=260,
        )

        def worker():
            ok, message = repair_local_cloud_client_count()
            Clock.schedule_once(
                lambda *_: self.finish_cloud_restore(ok, message),
                0,
            )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

    def finish_cloud_restore(self, ok, message):
        refresh_memory_from_db()
        self.render_metrics()
        self.render_clients()

        show_popup(
            "Restauración completada" if ok else "No se pudo restaurar",
            message,
            height=330,
        )

    def build_filters(self):
        self.filter_row_1.clear_widgets()
        self.filter_row_2.clear_widgets()

        row_1 = [
            ("Todos", "todos"),
            ("Activos", "activos"),
            ("Verdes", "verdes"),
        ]
        row_2 = [
            ("No pago", "no_pago"),
            ("Paz y salvo", "paz_y_salvo"),
            ("Sig. día", "siguiente"),
        ]

        for text, key in row_1:
            self.filter_row_1.add_widget(self.filter_button(text, key))
        for text, key in row_2:
            self.filter_row_2.add_widget(self.filter_button(text, key))

    def filter_button(self, text, key):
        active = self.current_filter == key
        btn = Button(
            text=text,
            size_hint_y=None,
            height=dp(28),
            background_normal="",
            background_color=BLUE if active else (0.87, 0.89, 0.93, 1),
            color=WHITE if active else TEXT,
            bold=True,
            font_size="11sp",
        )
        btn.bind(on_release=lambda *_: self.set_filter(key))
        return btn

    def set_filter(self, key):
        self.current_filter = key
        self.build_filters()
        self.render_clients()

    def metric_card(self, title, value, bg):
        box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(44), padding=[dp(8), dp(4), dp(8), dp(4)])
        with box.canvas.before:
            Color(*bg)
            box._bg = RoundedRectangle(pos=box.pos, size=box.size, radius=[dp(8)])
        box.bind(pos=lambda instance, *_: setattr(instance._bg, 'pos', instance.pos),
                 size=lambda instance, *_: setattr(instance._bg, 'size', instance.size))

        title_lbl = Label(text=title, color=MUTED if bg != (0.12, 0.22, 0.54, 1) else WHITE, font_size="9sp", halign="center", valign="middle", size_hint_y=0.45)
        value_lbl = Label(text=str(value), color=TEXT if bg != (0.12, 0.22, 0.54, 1) else WHITE, bold=True, font_size="14sp", halign="center", valign="middle", size_hint_y=0.55)
        title_lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        value_lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        box.add_widget(title_lbl)
        box.add_widget(value_lbl)
        return box

    def render_metrics(self):
        self.metrics_row_1.clear_widgets()
        self.metrics_row_2.clear_widgets()

        total = len(CLIENTES)
        activos = len([c for c in CLIENTES if int(c.get("saldo", 0)) > 0 and int(c.get("pendientes", 0)) > 0])
        verdes = len([c for c in CLIENTES if c.get("estado") == "pagado" or c.get("estado") == "paz_y_salvo" or safe_int(c.get("saldo", 0)) <= 0 or safe_int(c.get("pendientes", 0)) <= 0])
        no_pago = len([
            c for c in CLIENTES
            if c.get("estado") == "no_pago"
            or "no pag" in str(c.get("ultimo_tipo", "")).lower()
        ])
        paz = len([c for c in CLIENTES if c.get("estado") == "paz_y_salvo" or int(c.get("saldo", 0)) <= 0 or int(c.get("pendientes", 0)) <= 0])
        sig = len([c for c in CLIENTES if c.get("estado") == "siguiente"])

        self.metrics_row_1.add_widget(self.metric_card("Total", total, (0.12, 0.22, 0.54, 1)))
        self.metrics_row_1.add_widget(self.metric_card("Activos", activos, (0.95, 0.96, 0.99, 1)))
        self.metrics_row_1.add_widget(self.metric_card("Verdes", verdes, (0.90, 0.98, 0.92, 1)))

        self.metrics_row_2.add_widget(self.metric_card("No pago", no_pago, (1.0, 0.93, 0.93, 1)))
        self.metrics_row_2.add_widget(self.metric_card("Paz y salvo", paz, (0.91, 0.97, 1.0, 1)))
        self.metrics_row_2.add_widget(self.metric_card("Sig. día", sig, (1.0, 0.97, 0.88, 1)))

    def apply_filter(self, cliente):
        estado = cliente.get("estado", "pendiente")
        saldo = int(cliente.get("saldo", 0))
        pendientes = int(cliente.get("pendientes", 0))

        if self.current_filter == "todos":
            return True
        if self.current_filter == "activos":
            return saldo > 0 and pendientes > 0
        if self.current_filter == "verdes":
            return estado == "pagado"
        if self.current_filter == "no_pago":
            ultimo = str(cliente.get("ultimo_tipo", "")).lower()
            return (
                estado == "no_pago"
                or "no pag" in ultimo
            )
        if self.current_filter == "paz_y_salvo":
            return estado == "paz_y_salvo" or saldo <= 0 or pendientes <= 0
        if self.current_filter == "siguiente":
            return estado == "siguiente"
        return True

    def render_clients(self):
        self.client_list.clear_widgets()
        query = (self.search.text or "").strip().lower()

        filtered = []
        for cliente in CLIENTES:
            if query:
                searchable = " ".join([
                    str(cliente.get("nombre", "")),
                    str(cliente.get("telefono", "")),
                    str(cliente.get("documento", "")),
                ]).lower()
                if query not in searchable:
                    continue

            if not self.apply_filter(cliente):
                continue
            filtered.append(cliente)

        filtered.sort(key=lambda c: str(c.get("nombre", "")).lower())

        self.result_info.text = (
            f"Mostrando {len(filtered)} de {len(CLIENTES)} clientes locales"
        )

        if not filtered:
            empty = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(140), padding=dp(14), spacing=dp(8))
            title = Label(text="No hay clientes para este filtro", color=TEXT, bold=True, font_size="15sp", halign="center", size_hint_y=None, height=dp(30))
            msg = Label(text="Prueba cambiando el filtro o escribiendo otro nombre en el buscador.", color=MUTED, font_size="12sp", halign="center", valign="middle")
            title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            msg.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            empty.add_widget(title)
            empty.add_widget(msg)
            self.client_list.add_widget(empty)
            return

        for cliente in filtered:
            self.client_list.add_widget(ClienteCard(cliente, self.open_client))

    def open_client(self, cliente):
        self.app_ref.selected_client = cliente
        self.app_ref.go("gestion_cliente")



# ============================================================
# GESTIÓN CLIENTE
# ============================================================

class GestionClienteScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="gestion_cliente", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        refresh_clients_cache()
        self.cliente = get_client_by_id(self.app_ref.selected_client.get("id")) if self.app_ref.selected_client else None
        if self.cliente:
            self.app_ref.selected_client = self.cliente
        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Gestión del Cliente", show_back=True, on_back=lambda: self.app_ref.go("clientes")))

        if not self.cliente:
            self.root.add_widget(Label(text="Cliente no encontrado", color=WHITE))
            return

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(14), dp(14), dp(24)],
            spacing=dp(14),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        status = cobranza_estado_profesional(self.cliente)
        behavior = client_behavior_summary(self.cliente, status)
        bg_status = status["bg"]
        badge_text = status["label"]
        prioridad = cobranza_priority_label(self.cliente, status)
        proxima_visita = display_date_from_iso(self.cliente.get("proximo_cobro", ""))
        credito_finalizado = (
            int(self.cliente.get("saldo", 0)) <= 0
            or int(self.cliente.get("pendientes", 0)) <= 0
        )

        def title_label(texto, color=BLUE_DARK, size="15sp", align="left"):
            lbl = Label(
                text=texto,
                color=color,
                bold=True,
                font_size=size,
                halign=align,
                valign="middle",
                size_hint_y=None,
                height=dp(28),
            )
            lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            return lbl

        def info_label(texto, color=MUTED, size="11sp", height=dp(20), align="left"):
            lbl = Label(
                text=texto,
                color=color,
                font_size=size,
                halign=align,
                valign="middle",
                size_hint_y=None,
                height=height,
            )
            lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            return lbl

        def section_header(card, texto):
            header_box = RoundedBox(
                orientation="vertical",
                size_hint_y=None,
                height=dp(48),
                padding=[dp(10), dp(8), dp(10), dp(8)],
                spacing=dp(2),
            )
            header_box.bg_color = (0.92, 0.96, 1.0, 1)
            header_box.add_widget(
                title_label(
                    texto,
                    color=BLUE_DARK,
                    size="14sp",
                    align="left",
                )
            )
            card.add_widget(header_box)

        def metric_box(titulo, valor, bg=(0.17, 0.27, 0.62, 0.10), value_color=TEXT):
            box = RoundedBox(
                orientation="vertical",
                size_hint_x=1,
                size_hint_y=None,
                height=dp(86),
                padding=[dp(10), dp(8), dp(10), dp(8)],
                spacing=dp(2),
            )
            box.bg_color = bg
            box.add_widget(info_label(titulo, MUTED, "10sp", dp(18)))
            v = Label(
                text=str(valor),
                color=value_color,
                bold=True,
                font_size="13sp",
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(34),
            )
            v.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            box.add_widget(v)
            return box

        def recommendation_text():
            if str(behavior["riesgo"]).lower() == "alto":
                return "Cliente para seguimiento estricto. Revisar antes de renovar o subir cupo."
            if str(behavior["riesgo"]).lower() == "medio":
                return "Cliente estable, pero conviene vigilar su continuidad de pagos."
            return "Cliente con buen comportamiento. Puede seguir en ruta normal de cobro."

        hero = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(242),
            padding=[dp(14), dp(14), dp(14), dp(14)],
            spacing=dp(12),
        )
        hero.bg_color = bg_status

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(34), spacing=dp(8))
        name_lbl = Label(
            text=self.cliente.get("nombre", "SIN NOMBRE"),
            color=TEXT,
            bold=True,
            font_size="18sp",
            halign="left",
            valign="middle",
        )
        name_lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        status_lbl = Label(
            text=badge_text,
            color=TEXT,
            bold=True,
            font_size="12sp",
            halign="right",
            valign="middle",
            size_hint_x=0.42,
        )
        status_lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        top_row.add_widget(name_lbl)
        top_row.add_widget(status_lbl)

        subtitle = info_label(
            f"Código: {client_code(self.cliente)} · Resumen claro para confirmar y gestionar el cobro.",
            MUTED,
            "11sp",
            dp(22),
        )

        metrics = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(92), spacing=dp(8))
        metrics.add_widget(metric_box("Próxima visita", proxima_visita, bg=(1, 1, 1, 0.22), value_color=BLUE_DARK))
        metrics.add_widget(metric_box("Cuotas pendientes", self.cliente.get("pendientes", 0), bg=(1, 1, 1, 0.22), value_color=TEXT))
        metrics.add_widget(metric_box("Saldo actual", money(self.cliente.get("saldo", 0)), bg=(1, 1, 1, 0.22), value_color=TEXT))

        hero.add_widget(top_row)
        hero.add_widget(subtitle)
        hero.add_widget(metrics)
        content.add_widget(hero)

        operativa = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(596),
            padding=[dp(14), dp(16), dp(14), dp(16)],
            spacing=dp(9),
        )
        section_header(operativa, "Estado de gestión del cliente")
        operativa.add_widget(info_label("Resumen de seguimiento, prioridad de cobro y datos de ubicación para la visita.", MUTED, "10.5sp", dp(34), align="left"))
        operativa.add_widget(DetailRow("Estado de cobranza", badge_text))
        operativa.add_widget(DetailRow("Prioridad", prioridad))
        operativa.add_widget(DetailRow("Riesgo", behavior["riesgo_label"]))
        operativa.add_widget(DetailRow("Semáforo", behavior["semaforo"]))
        operativa.add_widget(DetailRow("Tipo de cobro", self.cliente.get("cobro", "Diario")))
        operativa.add_widget(DetailRow("Próxima visita", proxima_visita))
        operativa.add_widget(DetailRow("Documento", self.cliente.get("documento") or "No registrado"))
        operativa.add_widget(DetailRow("Teléfono", self.cliente.get("telefono") or "No registrado"))
        operativa.add_widget(DetailRow("Ruta", self.cliente.get("ruta") or "Sin ruta"))
        operativa.add_widget(DetailRow("Orden de visita", str(self.cliente.get("orden_visita", 0) or "-")))
        content.add_widget(operativa)

        prestamo = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(458),
            padding=[dp(14), dp(16), dp(14), dp(16)],
            spacing=dp(9),
        )
        section_header(prestamo, "Datos del préstamo")
        prestamo.add_widget(info_label("Información financiera vigente del crédito, cuotas y saldo pendiente.", MUTED, "10.5sp", dp(34), align="left"))
        prestamo.add_widget(DetailRow("Producto", self.cliente.get("producto") or "Crédito"))
        prestamo.add_widget(DetailRow("Valor entregado", money(self.cliente.get("valor_credito", 0))))
        prestamo.add_widget(DetailRow("Total a cobrar", money(self.cliente.get("total_credito", 0))))
        prestamo.add_widget(DetailRow("Valor de la cuota", money(self.cliente.get("cuota", 0))))
        prestamo.add_widget(DetailRow("Saldo actual", money(self.cliente.get("saldo", 0))))
        prestamo.add_widget(DetailRow("Cuotas pagadas", str(self.cliente.get("pagadas", 0))))
        prestamo.add_widget(DetailRow("Cuotas pendientes", str(self.cliente.get("pendientes", 0))))
        content.add_widget(prestamo)

        comportamiento = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(392),
            padding=[dp(14), dp(16), dp(14), dp(16)],
            spacing=dp(9),
        )
        section_header(comportamiento, "Comportamiento del cliente")
        comportamiento.add_widget(DetailRow("Pagos cumplidos", str(behavior["pagos"])))
        comportamiento.add_widget(DetailRow("No pagos", str(behavior["no_pagos"])))
        comportamiento.add_widget(DetailRow("Aplazamientos", str(behavior["aplazamientos"])))
        comportamiento.add_widget(DetailRow("Último pago", behavior["ultimo_pago"]))
        comportamiento.add_widget(DetailRow("Nivel de riesgo", behavior["riesgo_label"]))
        note = Label(
            text=recommendation_text(),
            color=MUTED,
            font_size="11sp",
            halign="left",
            valign="top",
            size_hint_y=None,
            height=dp(52),
        )
        note.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        comportamiento.add_widget(note)
        content.add_widget(comportamiento)

        renewal = renewal_intelligence(self.cliente)
        renewal_card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(262),
            padding=[dp(14), dp(16), dp(14), dp(16)],
            spacing=dp(9),
        )
        renewal_card.bg_color = (0.96, 0.98, 1.0, 1)
        section_header(renewal_card, "Renovación inteligente")
        renewal_card.add_widget(DetailRow("Resultado", renewal["estado"]))
        renewal_card.add_widget(DetailRow("Monto sugerido", money(renewal["monto_sugerido"])))
        renewal_note = Label(
            text=renewal["motivo"],
            color=renewal["color"],
            bold=True,
            font_size="11sp",
            halign="left",
            valign="top",
            size_hint_y=None,
            height=dp(58),
        )
        renewal_note.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        renewal_card.add_widget(renewal_note)
        content.add_widget(renewal_card)

        btn_cobrar = SmallButton("COBRAR CUOTA / APORTE", bg_color=BLUE)
        btn_historial = SmallButton("VER HISTORIAL COMPLETO", bg_color=SUCCESS)
        btn_editar = SmallButton("EDITAR CLIENTE Y PRÉSTAMO", bg_color=GOLD, text_color=DARK)
        btn_reset = SmallButton("REINICIAR ESTADO A PENDIENTE", bg_color=(0.45, 0.48, 0.55, 1))
        btn_borrar = SmallButton("ELIMINAR CLIENTE", bg_color=DANGER)

        btn_cobrar.bind(on_release=lambda *_: self.go_cobrar())
        btn_historial.bind(on_release=lambda *_: self.go_historial())
        btn_editar.bind(on_release=lambda *_: self.go_editar())
        btn_reset.bind(on_release=lambda *_: self.reset_estado())
        btn_borrar.bind(on_release=lambda *_: self.confirm_delete())

        if credito_finalizado:
            btn_renovar = SmallButton("RENOVAR PRÉSTAMO", bg_color=SUCCESS)
            btn_renovar.bind(on_release=lambda *_: self.go_renovar())
            content.add_widget(btn_renovar)
        else:
            content.add_widget(btn_cobrar)

        content.add_widget(btn_historial)
        content.add_widget(btn_editar)
        if not credito_finalizado:
            content.add_widget(btn_reset)
        content.add_widget(btn_borrar)

        help_card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(252),
            padding=[dp(14), dp(14), dp(14), dp(14)],
            spacing=dp(7),
        )
        section_header(help_card, "Guía rápida para el cobrador")
        help_card.add_widget(DetailRow("Verde", "El cliente ya pagó o hizo abono hoy."))
        help_card.add_widget(DetailRow("Amarillo", "Cliente pendiente o programado para hoy."))
        help_card.add_widget(DetailRow("Rojo", "Cliente vencido o con no pago registrado."))
        help_card.add_widget(DetailRow("Bloqueo", "Si está en verde, normalmente solo admite aporte."))
        content.add_widget(help_card)

        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def go_cobrar(self):
        self.app_ref.selected_client = self.cliente
        self.app_ref.go("cuota")

    def go_historial(self):
        self.app_ref.selected_client = self.cliente
        self.app_ref.go("historial_cliente")

    def go_renovar(self):
        light = client_traffic_light(self.cliente)
        if light.get("grupo") in ("rojo", "no_renovar"):
            confirm_popup(
                "Renovación con riesgo",
                "Este cliente está marcado como seguimiento prioritario o no recomendado para renovar.\n\n"
                "¿Deseas continuar de todas formas?",
                self._go_renovar_confirmed,
            )
            return

        self._go_renovar_confirmed()

    def _go_renovar_confirmed(self):
        self.app_ref.selected_client = self.cliente
        self.app_ref.go("renovar_prestamo")

    def go_editar(self):
        self.app_ref.selected_client = self.cliente
        self.app_ref.go("editar_cliente")

    def reset_estado(self):
        motive_required_popup(
            "Reiniciar estado",
            f"Indique el motivo para reiniciar el estado de {self.cliente.get('nombre', 'este cliente')}",
            self.reset_estado_with_reason,
            options=["Error de registro", "Corrección de visita", "Solicitud del cliente", "Otro"],
        )

    def reset_estado_with_reason(self, motivo, detalle):
        reset_client_status_db(self.cliente.get("id"))
        insert_audit_log("Estado reiniciado", self.cliente, motivo, detalle)
        refresh_memory_from_db()
        show_popup("Estado reiniciado", "El cliente quedó pendiente por cobrar.")
        Clock.schedule_once(lambda *_: self.app_ref.go("clientes"), 0.7)

    def confirm_delete(self):
        motive_required_popup(
            "Eliminar cliente",
            f"Indique el motivo para eliminar a {self.cliente.get('nombre', 'este cliente')}.\nTambién se borrarán sus transacciones.",
            self.delete_client_with_reason,
            options=["Cliente duplicado", "Error de registro", "Cliente retirado", "Prueba del sistema", "Otro"],
        )

    def delete_client_with_reason(self, motivo, detalle):
        saldo = safe_int(self.cliente.get("saldo", 0)) if self.cliente else 0
        pendientes = safe_int(self.cliente.get("pendientes", 0)) if self.cliente else 0

        if saldo > 0 or pendientes > 0:
            strong_reasons = ("Cliente duplicado", "Error de registro")
            if motivo not in strong_reasons and len((detalle or "").strip()) < 15:
                show_popup(
                    "Motivo insuficiente",
                    "Este cliente aún tiene saldo o cuotas pendientes.\n\n"
                    "Para eliminarlo debes usar un motivo fuerte o escribir un detalle claro.",
                    height=330,
                )
                return

        self._delete_reason = (motivo, detalle)
        self.delete_client()

    def delete_client(self):
        cliente_eliminado = dict(self.cliente) if self.cliente else None

        try:
            if cliente_eliminado and supabase_configured():
                ok, msg = delete_remote_client_bundle(cliente_eliminado)
                print("DELETE REMOTE:", ok, msg)
        except Exception as error:
            print("ERROR DELETE REMOTE:", error)

        motivo, detalle = getattr(self, "_delete_reason", ("Sin motivo registrado", ""))
        insert_audit_log("Cliente eliminado", cliente_eliminado, motivo, detalle)
        delete_client_db(self.cliente.get("id"))
        refresh_memory_from_db()

        self.app_ref.selected_client = None

        show_popup(
            "Cliente eliminado",
            "El cliente, sus transacciones y el egreso del préstamo fueron eliminados correctamente."
        )
        Clock.schedule_once(lambda *_: self.app_ref.go("clientes"), 0.7)

# ============================================================
# HISTORIAL DEL CLIENTE
# ============================================================

class HistorialClienteScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="historial_cliente", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()

        # Refrescar solo clientes y transacciones del historial.
        refresh_client_history_cache()

        selected_id = (
            self.app_ref.selected_client.get("id")
            if self.app_ref.selected_client
            else None
        )

        self.cliente = (
            get_client_by_id(selected_id)
            if selected_id is not None
            else None
        )

        # Mantener actualizado el cliente seleccionado para las demás pantallas.
        if self.cliente:
            self.app_ref.selected_client = self.cliente

        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(
            Header(
                "Historial del Cliente",
                show_back=True,
                on_back=lambda: self.app_ref.go("gestion_cliente"),
            )
        )

        if not self.cliente:
            self.root.add_widget(Label(text="Cliente no encontrado", color=WHITE))
            return

        transactions = [
            t for t in TRANSACCIONES
            if int(t.get("cliente_id") or 0) == int(self.cliente.get("id"))
        ]
        transactions.sort(key=lambda item: int(item.get("id") or 0))

        # El último movimiento es la referencia inmediata del saldo y cuotas.
        # Si la ficha del cliente quedó temporalmente desactualizada, mostrar
        # los valores confirmados por la transacción más reciente.
        latest_transaction = transactions[-1] if transactions else None

        current_balance = int(self.cliente.get("saldo", 0))
        current_paid = int(self.cliente.get("pagadas", 0))
        current_pending = int(self.cliente.get("pendientes", 0))

        if latest_transaction:
            current_balance = int(
                latest_transaction.get("saldo_nuevo", current_balance) or 0
            )
            current_paid = int(
                latest_transaction.get(
                    "cuotas_pagadas_total",
                    current_paid,
                ) or 0
            )
            current_pending = int(
                latest_transaction.get(
                    "cuotas_pendientes_total",
                    current_pending,
                ) or 0
            )

        scroll = ScrollView(
            do_scroll_x=False,
            bar_width=dp(4),
            scroll_type=["bars", "content"],
        )

        content = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(16), dp(14), dp(72)],
            spacing=dp(14),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        # ---------------- RESUMEN DEL CRÉDITO ----------------
        summary = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(356),
            padding=[dp(16), dp(14), dp(16), dp(14)],
            spacing=dp(6),
        )

        title = Label(
            text=self.cliente.get("nombre", "SIN NOMBRE"),
            color=TEXT,
            bold=True,
            font_size="18sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(36),
        )
        title.bind(
            size=lambda instance, value: setattr(
                instance, "text_size", (value[0], None)
            )
        )
        summary.add_widget(title)

        divider = Widget(size_hint_y=None, height=dp(2))
        with divider.canvas:
            Color(0.88, 0.90, 0.94, 1)
            divider_line = Rectangle(pos=divider.pos, size=divider.size)
        divider.bind(
            pos=lambda instance, value: setattr(divider_line, "pos", value),
            size=lambda instance, value: setattr(divider_line, "size", value),
        )
        summary.add_widget(divider)

        summary.add_widget(DetailRow("Documento", self.cliente.get("documento") or "No registrado"))
        summary.add_widget(DetailRow("Fecha creación", self.cliente.get("created_at") or "No disponible"))
        summary.add_widget(DetailRow("Fecha final", actual_or_projected_end_date(self.cliente, transactions)))
        summary.add_widget(DetailRow("Tipo de cobro", self.cliente.get("cobro", "Diario")))
        summary.add_widget(DetailRow("Valor de cuota", money(self.cliente.get("cuota", 0))))
        summary.add_widget(
            DetailRow(
                "Aporte acumulado",
                money(self.cliente.get("aporte_acumulado", 0)),
            )
        )
        summary.add_widget(DetailRow("Cuotas pagadas", str(current_paid)))
        summary.add_widget(DetailRow("Cuotas pendientes", str(current_pending)))
        summary.add_widget(DetailRow("Saldo actual", money(current_balance)))
        content.add_widget(summary)

        section_box = RoundedBox(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(54),
            padding=[dp(14), dp(8), dp(14), dp(8)],
            spacing=dp(8),
        )
        section_box.bg_color = BLUE_DARK

        section_title = Label(
            text="MOVIMIENTOS DEL CLIENTE",
            color=WHITE,
            bold=True,
            font_size="13sp",
            halign="left",
            valign="middle",
            size_hint_x=0.68,
        )
        section_title.bind(
            size=lambda instance, value: setattr(
                instance, "text_size", value
            )
        )

        section_count = Label(
            text=f"{len(transactions)} registro(s)",
            color=GOLD,
            bold=True,
            font_size="11sp",
            halign="right",
            valign="middle",
            size_hint_x=0.32,
        )
        section_count.bind(
            size=lambda instance, value: setattr(
                instance, "text_size", value
            )
        )

        section_box.add_widget(section_title)
        section_box.add_widget(section_count)
        content.add_widget(section_box)

        if not transactions:
            empty = RoundedBox(
                orientation="vertical",
                size_hint_y=None,
                height=dp(120),
                padding=dp(16),
            )
            msg = Label(
                text="Este cliente todavía no tiene pagos ni novedades registradas.",
                color=MUTED,
                halign="center",
                valign="middle",
            )
            msg.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            empty.add_widget(msg)
            content.add_widget(empty)
        else:
            for tx in reversed(transactions):
                content.add_widget(self.transaction_card(tx))

        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def transaction_summary(self, tx):
        tipo = tx.get("tipo", "Movimiento")
        valor = money(tx.get("valor", 0))
        cuotas = int(tx.get("numero_cuotas", 0) or 0)
        pagadas = int(tx.get("cuotas_pagadas_total", 0) or 0)
        pendientes = int(tx.get("cuotas_pendientes_total", 0) or 0)
        saldo_anterior = money(tx.get("saldo_anterior", 0))
        saldo_nuevo = money(tx.get("saldo_nuevo", 0))
        observacion = " ".join(str(tx.get("observacion", "") or "").split())

        if tipo == "Cuota":
            return (
                f"Se registró un pago por {valor}. "
                f"Se acreditó {cuotas} cuota(s). "
                f"Ahora el cliente lleva {pagadas} pagadas y {pendientes} pendientes. "
                f"El saldo bajó de {saldo_anterior} a {saldo_nuevo}."
            )

        if tipo == "Aporte":
            base = (
                f"Se recibió un aporte por {valor}. "
                f"Cuotas acreditadas con este movimiento: {cuotas}. "
                f"El saldo cambió de {saldo_anterior} a {saldo_nuevo}."
            )
            if observacion:
                return f"{base} {observacion}"
            return base

        if tipo == "No Pago":
            return (
                "El cliente no realizó pago en esta visita. "
                f"Queda con {pendientes} cuota(s) pendiente(s) y saldo actual de {saldo_nuevo}."
            )

        if tipo == "Siguiente Día":
            return (
                "La visita fue aplazada para el siguiente cobro. "
                f"El saldo se mantiene en {saldo_nuevo} con {pendientes} cuota(s) pendientes."
            )

        if tipo == "Renovación":
            return observacion or "Se registró una renovación del préstamo."

        if tipo == "Migración":
            return observacion or "Se cargó un préstamo anterior al sistema."

        return observacion or f"Movimiento registrado: {tipo}."

    def transaction_card(self, tx):
        tipo = tx.get("tipo", "Movimiento")

        if tipo == "Cuota":
            accent = SUCCESS
            bg = (0.93, 0.98, 0.94, 1)
        elif tipo == "Aporte":
            accent = GOLD
            bg = (1.0, 0.98, 0.91, 1)
        elif tipo == "No Pago":
            accent = DANGER
            bg = (1.0, 0.94, 0.94, 1)
        elif tipo in ("Renovación", "Migración"):
            accent = BLUE
            bg = (0.95, 0.97, 1, 1)
        else:
            accent = (0.45, 0.48, 0.55, 1)
            bg = (0.96, 0.97, 0.99, 1)

        card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(348),
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(8),
        )
        card.bg_color = WHITE

        header = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            spacing=dp(8),
        )

        left_header = BoxLayout(
            orientation="vertical",
            size_hint_x=0.62,
            spacing=dp(1),
        )

        type_label = Label(
            text=str(tipo).upper(),
            color=accent if tipo != "Aporte" else DARK,
            bold=True,
            font_size="13sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(22),
        )
        type_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        value_label = Label(
            text=f"Valor: {money(tx.get('valor', 0))}",
            color=TEXT,
            bold=True,
            font_size="12sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(20),
        )
        value_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        left_header.add_widget(type_label)
        left_header.add_widget(value_label)

        right_header = BoxLayout(
            orientation="vertical",
            size_hint_x=0.38,
            spacing=dp(1),
        )

        date_label = Label(
            text=str(tx.get("fecha", "")),
            color=MUTED,
            font_size="10.5sp",
            halign="right",
            valign="middle",
            size_hint_y=None,
            height=dp(22),
        )
        reg_label = Label(
            text=f"Registro #{tx.get('id', '')}",
            color=GOLD,
            bold=True,
            font_size="10sp",
            halign="right",
            valign="middle",
            size_hint_y=None,
            height=dp(20),
        )
        for label in (date_label, reg_label):
            label.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        right_header.add_widget(date_label)
        right_header.add_widget(reg_label)

        header.add_widget(left_header)
        header.add_widget(right_header)
        card.add_widget(header)

        line = Widget(size_hint_y=None, height=dp(2))
        with line.canvas:
            Color(accent[0], accent[1], accent[2], 0.85)
            rect = Rectangle(pos=line.pos, size=line.size)
        line.bind(
            pos=lambda instance, value: setattr(rect, "pos", value),
            size=lambda instance, value: setattr(rect, "size", value),
        )
        card.add_widget(line)

        details = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(152),
            padding=[dp(10), dp(8), dp(10), dp(8)],
            spacing=dp(4),
        )
        details.bg_color = (0.98, 0.98, 1, 1)

        row_a = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(8))
        row_a.add_widget(DetailRow("Cuotas", str(tx.get("numero_cuotas", 0))))
        row_a.add_widget(DetailRow("Método", tx.get("metodo") or "No aplica"))

        row_b = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42), spacing=dp(8))
        row_b.add_widget(
            DetailRow(
                "Pagadas",
                str(tx.get("cuotas_pagadas_total", 0)),
            )
        )
        row_b.add_widget(
            DetailRow(
                "Pendientes",
                str(tx.get("cuotas_pendientes_total", 0)),
            )
        )

        saldo_text = (
            f"{money(tx.get('saldo_anterior', 0))}  →  "
            f"{money(tx.get('saldo_nuevo', 0))}"
        )
        saldo_row = DetailRow("Cambio de saldo", saldo_text)

        details.add_widget(row_a)
        details.add_widget(row_b)
        details.add_widget(saldo_row)
        card.add_widget(details)

        summary_box = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(118),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(6),
        )
        summary_box.bg_color = bg

        summary_title = Label(
            text="Resumen del movimiento",
            color=DARK,
            bold=True,
            font_size="12sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(22),
        )
        summary_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        summary_text = Label(
            text=self.transaction_summary(tx),
            color=TEXT,
            font_size="10.5sp",
            halign="left",
            valign="top",
            size_hint_y=None,
            height=dp(76),
        )
        summary_text.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        summary_box.add_widget(summary_title)
        summary_box.add_widget(summary_text)
        card.add_widget(summary_box)

        return card


# COBRO
# ============================================================

class CuotaScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="cuota", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        refresh_memory_from_db()
        self.cliente = get_client_by_id(self.app_ref.selected_client.get("id")) if self.app_ref.selected_client else None
        self.client_confirmed = False
        if self.cliente:
            self.app_ref.selected_client = self.cliente
        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Cuota Cliente / Ingreso Cuota", show_back=True, on_back=lambda: self.app_ref.go("gestion_cliente")))

        if not self.cliente:
            self.root.add_widget(Label(text="Cliente no encontrado", color=WHITE))
            return

        if not getattr(self, "client_confirmed", False):
            self.build_client_confirmation()
            return

        scroll = ScrollView()
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(16), dp(14), dp(36)],
            spacing=dp(16),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        # ====================================================
        # TARJETA RESUMEN DEL CLIENTE
        # ====================================================
        summary = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(348),
            padding=[dp(16), dp(14), dp(16), dp(14)],
            spacing=dp(9),
        )
        summary.bg_color = (0.98, 0.99, 1, 1)

        name_lbl = Label(
            text=self.cliente.get("nombre", "").title(),
            color=TEXT,
            bold=True,
            font_size="18sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(34),
        )
        name_lbl.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], None)))
        summary.add_widget(name_lbl)

        summary.add_widget(DetailRow("Código", client_code(self.cliente)))
        summary.add_widget(DetailRow("Teléfono", self.cliente.get("telefono", "") or "No registrado"))
        summary.add_widget(DetailRow("Pagadas", str(self.cliente.get("pagadas", 0))))
        summary.add_widget(DetailRow("Pendientes", str(self.cliente.get("pendientes", 0))))
        summary.add_widget(DetailRow("Tipo Cobro", self.cliente.get("cobro", "Diario")))
        summary.add_widget(
            DetailRow(
                "Visita programada",
                display_date_from_iso(
                    self.cliente.get("proximo_cobro", "")
                ) or "Hoy",
            )
        )
        summary.add_widget(DetailRow("Saldo Actual", money(self.cliente.get("saldo", 0))))

        content.add_widget(summary)

        # ====================================================
        # TARJETA TIPO DE TRANSACCIÓN
        # ====================================================
        action = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(196),
            padding=[dp(16), dp(14), dp(16), dp(14)],
            spacing=dp(12),
        )
        action.bg_color = (0.98, 0.99, 1, 1)

        action_title = Label(
            text="Resultado del cobro",
            color=TEXT,
            bold=True,
            font_size="14sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(24),
        )
        action_title.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], None)))
        action.add_widget(action_title)

        row = BoxLayout(
            orientation="horizontal",
            spacing=dp(7),
            size_hint_y=None,
            height=dp(52),
        )
        self.tipo_buttons = []

        for index, option in enumerate(["Cuota", "Aporte", "No Pago", "Siguiente Día"]):
            btn = ToggleButton(
                text=option,
                group="tipo_cuota",
                state="down" if index == 0 else "normal",
                background_normal="",
                background_color=SUCCESS if index == 0 else (0.88, 0.90, 0.94, 1),
                color=WHITE if index == 0 else DARK,
                font_size="10sp",
                bold=True,
                halign="center",
                valign="middle",
            )
            btn.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            btn.bind(on_release=self.update_tipo_colors)
            self.tipo_buttons.append(btn)
            row.add_widget(btn)

        action.add_widget(row)

        self.warning = Label(
            text="Seleccione si el cliente pagó, hizo aporte, no pagó o queda para el siguiente día.",
            color=MUTED,
            font_size="11sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(54),
        )
        self.warning.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        action.add_widget(self.warning)

        content.add_widget(action)

        # ====================================================
        # FORMULARIO DE PAGO
        # ====================================================
        form = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(820),
            padding=[dp(16), dp(16), dp(16), dp(18)],
            spacing=dp(12),
        )
        form.bg_color = WHITE

        form_title = Label(
            text="Detalle de la transacción",
            color=TEXT,
            bold=True,
            font_size="14sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(30),
        )
        form_title.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], None)))
        form.add_widget(form_title)

        self.valor_cuota = MoneyTextInput(text=format_thousands(self.cliente.get("cuota", 0)), readonly=True)
        self.saldo_actual = MoneyTextInput(text=format_thousands(self.cliente.get("saldo", 0)), readonly=True)
        self.valor_pagar = MoneyTextInput(text=format_thousands(self.cliente.get("cuota", 0)))
        self.numero_cuotas = AppTextInput(text="1", input_filter="int")
        self.nuevo_saldo = MoneyTextInput(
            text=format_thousands(max(int(self.cliente.get("saldo", 0)) - int(self.cliente.get("cuota", 0)), 0)),
            readonly=True,
        )
        self.metodo_pago = Spinner(
            text="Efectivo",
            values=["Efectivo", "Transferencia"],
            size_hint_y=None,
            height=dp(42),
            background_normal="",
            background_color=WHITE,
            color=TEXT,
        )
        self.fecha_nueva_visita = AppTextInput(
            text=display_date_from_iso(default_rescheduled_visit()),
            readonly=True,
        )
        self.motivo_novedad = Spinner(
            text="Seleccione motivo",
            values=["No estaba", "No tenía dinero", "Pidió reprogramar", "Se negó a pagar", "Otro"],
            size_hint_y=None,
            height=dp(44),
            background_normal="",
            background_color=WHITE,
            color=TEXT,
        )
        self.detalle_novedad = AppTextInput(hint_text="Detalle del motivo", multiline=True)
        self.detalle_novedad.height = dp(64)

        for label, widget in [
            ("Valor Cuota", self.valor_cuota),
            ("Saldo Actual", self.saldo_actual),
            ("Valor a Pagar", self.valor_pagar),
            ("Número de Cuotas", self.numero_cuotas),
            ("Nuevo Saldo", self.nuevo_saldo),
            ("Método de Pago", self.metodo_pago),
        ]:
            form.add_widget(self.field_container(label, widget, highlight=(label == "Nuevo Saldo")))

        visit_box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(78),
            spacing=dp(6),
        )
        visit_box.add_widget(FieldLabel("Nueva visita si no paga"))
        visit_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            spacing=dp(8),
        )
        visit_row.add_widget(self.fecha_nueva_visita)
        visit_calendar = Button(
            text="Calendario",
            size_hint_x=None,
            width=dp(106),
            background_normal="",
            background_color=BLUE,
            color=WHITE,
            bold=True,
            font_size="11sp",
        )
        visit_calendar.bind(
            on_release=lambda *_: self.open_visit_calendar()
        )
        visit_row.add_widget(visit_calendar)
        visit_box.add_widget(visit_row)
        form.add_widget(visit_box)

        motivo_box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(124),
            spacing=dp(6),
        )
        motivo_box.add_widget(FieldLabel("Motivo si no paga o se reprograma"))
        motivo_box.add_widget(self.motivo_novedad)
        motivo_box.add_widget(self.detalle_novedad)
        form.add_widget(motivo_box)

        self._updating_installment_amount = False
        for input_widget in [
            self.valor_pagar,
            self.numero_cuotas,
            self.metodo_pago,
            self.fecha_nueva_visita,
            self.detalle_novedad,
        ]:
            bind_scroll_to_input(scroll, input_widget)

        self.valor_pagar.bind(text=lambda *_: self.recalculate_balance())
        self.numero_cuotas.bind(text=lambda *_: self.on_installments_changed())

        register = SmallButton("Registrar Transacción", bg_color=BLUE)
        register.bind(on_release=lambda *_: self.register_transaction())
        form.add_widget(register)

        content.add_widget(form)
        scroll.add_widget(content)
        self.root.add_widget(scroll)

        self.apply_payment_rules()

    def build_client_confirmation(self):
        """
        Primera barrera de seguridad:
        antes de cobrar, el cobrador confirma visualmente que está en el cliente correcto.
        """
        scroll = ScrollView()
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(18), dp(14), dp(32)],
            spacing=dp(14),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(430),
            padding=[dp(16), dp(16), dp(16), dp(16)],
            spacing=dp(10),
        )
        card.bg_color = (0.98, 0.99, 1, 1)

        title = Label(
            text="¿ESTÁS COBRANDO A ESTE CLIENTE?",
            color=BLUE,
            bold=True,
            font_size="15sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(34),
        )
        title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        card.add_widget(title)

        warning = Label(
            text="Verifica nombre, código, teléfono, documento, dirección y saldo antes de continuar.",
            color=DANGER,
            bold=True,
            font_size="11sp",
            halign="left",
            valign="top",
            size_hint_y=None,
            height=dp(46),
        )
        warning.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        card.add_widget(warning)

        card.add_widget(DetailRow("Código", client_code(self.cliente)))
        card.add_widget(DetailRow("Nombre", self.cliente.get("nombre", "SIN NOMBRE")))
        card.add_widget(DetailRow("Teléfono", self.cliente.get("telefono") or "No registrado"))
        card.add_widget(DetailRow("Documento", self.cliente.get("documento") or "No registrado"))
        card.add_widget(DetailRow("Dirección", self.cliente.get("direccion") or "No registrada"))
        card.add_widget(DetailRow("Saldo actual", money(self.cliente.get("saldo", 0))))
        card.add_widget(DetailRow("Cuota", money(self.cliente.get("cuota", 0))))
        card.add_widget(DetailRow("Próxima visita", display_date_from_iso(self.cliente.get("proximo_cobro", ""))))

        content.add_widget(card)

        actions = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(52),
            spacing=dp(10),
        )

        back_btn = SmallButton("Volver", bg_color=(0.45, 0.48, 0.55, 1))
        back_btn.bind(on_release=lambda *_: self.app_ref.go("gestion_cliente"))

        confirm_btn = SmallButton("SÍ, ES ESTE CLIENTE", bg_color=SUCCESS)
        confirm_btn.bind(on_release=lambda *_: self.confirm_client_identity())

        actions.add_widget(back_btn)
        actions.add_widget(confirm_btn)
        content.add_widget(actions)

        help_card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(102),
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(6),
        )
        help_card.bg_color = (1.0, 0.95, 0.86, 1)
        msg = Label(
            text="Este paso evita registrar pagos en el cliente equivocado y protege la caja del negocio.",
            color=TEXT,
            bold=True,
            font_size="12sp",
            halign="left",
            valign="middle",
        )
        msg.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        help_card.add_widget(msg)
        content.add_widget(help_card)

        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def confirm_client_identity(self):
        self.client_confirmed = True
        self.build()

    def show_duplicate_payment_warning(self, last_tx):
        """
        Bloqueo contra doble pago accidental.

        Si ya existe una cuota/aporte hoy, no permite guardar otra cuota
        sin que el cobrador cambie conscientemente a aporte.
        """
        content = BoxLayout(
            orientation="vertical",
            padding=dp(14),
            spacing=dp(10),
        )

        msg = Label(
            text=(
                "ESTE CLIENTE YA TIENE UN PAGO REGISTRADO HOY\n\n"
                f"Último pago: {money(last_tx.get('valor', 0))}\n"
                f"Hora: {last_tx.get('fecha', '')}\n\n"
                "Para evitar duplicados, no se registrará otra cuota automática.\n"
                "Si recibió dinero adicional, regístrelo como APORTE."
            ),
            color=WHITE,
            font_size="13sp",
            halign="center",
            valign="middle",
        )
        msg.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        content.add_widget(msg)

        buttons = BoxLayout(
            orientation="horizontal",
            spacing=dp(10),
            size_hint_y=None,
            height=dp(48),
        )

        popup = Popup(
            title="Posible doble pago",
            content=content,
            size_hint=(0.92, None),
            height=dp(380),
            auto_dismiss=False,
        )

        cancel = Button(
            text="Cancelar",
            background_normal="",
            background_color=(0.45, 0.48, 0.55, 1),
            color=WHITE,
            bold=True,
        )
        aporte = Button(
            text="Registrar aporte",
            background_normal="",
            background_color=GOLD,
            color=DARK,
            bold=True,
        )

        cancel.bind(on_release=popup.dismiss)

        def switch_to_aporte(*_):
            popup.dismiss()
            for btn in self.tipo_buttons:
                if btn.text == "Aporte":
                    btn.disabled = False
                    btn.state = "down"
                else:
                    btn.state = "normal"
            self.update_tipo_colors()
            self.warning.text = "Modo aporte activado para evitar doble cuota accidental."
            self.warning.color = GOLD

        aporte.bind(on_release=switch_to_aporte)
        buttons.add_widget(cancel)
        buttons.add_widget(aporte)
        content.add_widget(buttons)

        popup.open()

    def build_transaction_preview(self):
        """
        Calcula una vista previa de la operación antes de guardar.
        No modifica base de datos ni cliente.
        """
        tipo = self.selected_tipo()
        pago = to_int(self.valor_pagar.text, 0)
        saldo_anterior = int(self.cliente.get("saldo", 0) or 0)
        pagadas_actuales = int(self.cliente.get("pagadas", 0) or 0)
        pendientes_actuales = int(self.cliente.get("pendientes", 0) or 0)
        cuota_unitaria = max(int(self.cliente.get("cuota", 0) or 0), 0)
        cantidad_cuotas = 0
        nueva_visita = self.cliente.get("proximo_cobro", "")

        if tipo == "Cuota":
            try:
                cantidad_cuotas = int(str(self.numero_cuotas.text or "0").strip())
            except Exception:
                cantidad_cuotas = 0

            nuevo_saldo = max(saldo_anterior - pago, 0)
            nuevas_pagadas = pagadas_actuales + max(cantidad_cuotas, 0)
            nuevas_pendientes = max(pendientes_actuales - max(cantidad_cuotas, 0), 0)

            if cantidad_cuotas > 0 and nuevo_saldo > 0 and nuevas_pendientes > 0:
                nueva_visita = next_visit_after_payment(
                    self.cliente.get("proximo_cobro", ""),
                    self.cliente.get("cobro", "Diario"),
                    cantidad_cuotas,
                )
            else:
                nueva_visita = ""

        elif tipo == "Aporte":
            nuevo_saldo = max(saldo_anterior - pago, 0)
            aporte_total = int(self.cliente.get("aporte_acumulado", 0) or 0) + pago
            if cuota_unitaria > 0:
                cantidad_cuotas = min(aporte_total // cuota_unitaria, pendientes_actuales)
            nuevas_pagadas = pagadas_actuales + cantidad_cuotas
            nuevas_pendientes = max(pendientes_actuales - cantidad_cuotas, 0)
            nueva_visita = self.cliente.get("proximo_cobro", "")

        else:
            pago = 0
            nuevo_saldo = saldo_anterior
            nuevas_pagadas = pagadas_actuales
            nuevas_pendientes = pendientes_actuales
            nueva_visita = self.selected_rescheduled_visit() or ""

        return {
            "tipo": tipo,
            "pago": pago,
            "saldo_anterior": saldo_anterior,
            "nuevo_saldo": nuevo_saldo,
            "pagadas": nuevas_pagadas,
            "pendientes": nuevas_pendientes,
            "nueva_visita": nueva_visita,
        }

    def register_transaction(self):
        """
        Segunda barrera de seguridad:
        el usuario revisa los efectos del pago antes de guardar definitivamente.
        """
        ok_cash, msg_cash = require_cash_open("registrar cobros")
        if not ok_cash:
            show_popup(
                "Caja no abierta",
                msg_cash,
                height=290,
            )
            return

        # Validaciones principales antes de abrir la confirmación.
        tipo = self.selected_tipo()
        pago = to_int(self.valor_pagar.text, 0)

        if tipo in ("Cuota", "Aporte") and pago <= 0:
            show_popup("Valor inválido", "Ingrese un valor mayor que cero.")
            return

        if tipo in ("No Pago", "Siguiente Día") and not self.selected_rescheduled_visit():
            show_popup(
                "Nueva visita requerida",
                "Selecciona una nueva fecha futura para reprogramar esta visita.",
                height=260,
            )
            return

        if tipo in ("No Pago", "Siguiente Día"):
            motivo = self.motivo_novedad.text.strip()
            detalle = self.detalle_novedad.text.strip()
            if motivo == "Seleccione motivo":
                show_popup("Motivo requerido", "Seleccione el motivo de la novedad.", height=250)
                return
            if motivo == "Otro" and not detalle:
                show_popup("Detalle requerido", "Escriba el detalle del motivo.", height=250)
                return

        if tipo == "Cuota":
            last_payment = latest_payment_today_for_client(self.cliente)
            if last_payment:
                self.show_duplicate_payment_warning(last_payment)
                return

        preview = self.build_transaction_preview()

        content = BoxLayout(
            orientation="vertical",
            padding=dp(14),
            spacing=dp(10),
        )

        msg = Label(
            text="CONFIRMAR MOVIMIENTO\nRevise los datos antes de guardar.",
            color=WHITE,
            bold=True,
            font_size="15sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(58),
        )
        msg.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        content.add_widget(msg)

        info = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(320),
            spacing=dp(6),
        )
        for left, right in [
            ("Código", client_code(self.cliente)),
            ("Cliente", self.cliente.get("nombre", "SIN NOMBRE")),
            ("Tipo", preview["tipo"]),
            ("Valor recibido", money(preview["pago"])),
            ("Saldo anterior", money(preview["saldo_anterior"])),
            ("Nuevo saldo", money(preview["nuevo_saldo"])),
            ("Cuotas pagadas", str(preview["pagadas"])),
            ("Cuotas pendientes", str(preview["pendientes"])),
            ("Próxima visita", display_date_from_iso(preview["nueva_visita"])),
        ]:
            info.add_widget(DetailRow(left, right))

        content.add_widget(info)

        question = Label(
            text="¿Guardar este movimiento?",
            color=WHITE,
            bold=True,
            font_size="13sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(34),
        )
        question.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        content.add_widget(question)

        buttons = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(10),
        )

        popup = Popup(
            title="Confirmación de cobro",
            content=content,
            size_hint=(0.92, None),
            height=dp(540),
            auto_dismiss=False,
        )

        cancel_btn = Button(
            text="Cancelar",
            background_normal="",
            background_color=(0.45, 0.48, 0.55, 1),
            color=WHITE,
            bold=True,
        )
        save_btn = Button(
            text="Confirmar pago",
            background_normal="",
            background_color=SUCCESS,
            color=WHITE,
            bold=True,
        )

        cancel_btn.bind(on_release=lambda *_: popup.dismiss())

        def do_save(*_):
            popup.dismiss()
            self._commit_transaction()

        save_btn.bind(on_release=do_save)

        buttons.add_widget(cancel_btn)
        buttons.add_widget(save_btn)
        content.add_widget(buttons)

        popup.open()

    def open_visit_calendar(self):
        initial = normalize_date_input(self.fecha_nueva_visita.text)
        CalendarPopup(
            initial_date=initial,
            on_select=self.set_visit_date,
        ).open()

    def set_visit_date(self, selected_date):
        self.fecha_nueva_visita.text = selected_date.strftime("%d/%m/%Y")

    def selected_rescheduled_visit(self):
        selected = normalize_date_input(self.fecha_nueva_visita.text)
        if not selected:
            return None
        try:
            selected_date = datetime.strptime(selected, "%Y-%m-%d").date()
            if selected_date <= datetime.now().date():
                return None
        except Exception:
            return None
        return selected

    def field_container(self, label, widget, highlight=False):
        box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(72),
            spacing=dp(7),
            padding=[0, dp(3), 0, 0],
        )

        lbl = FieldLabel(label)
        lbl.size_hint_y = None
        lbl.height = dp(18)
        lbl.color = BLUE if highlight else MUTED
        lbl.bold = True if highlight else False
        box.add_widget(lbl)

        try:
            widget.size_hint_y = None
            widget.height = dp(42)
            if highlight:
                widget.background_color = (1.0, 0.95, 0.78, 1)
                widget.foreground_color = TEXT
        except Exception:
            pass

        box.add_widget(widget)
        return box

    def apply_payment_rules(self):
        estado = self.cliente.get("estado", "pendiente")

        for btn in self.tipo_buttons:
            btn.disabled = False
            btn.state = "normal"
            btn.background_color = (0.88, 0.90, 0.94, 1)
            btn.color = DARK

        if estado in ("pagado", "aporte"):
            self.warning.text = "Cliente en verde. No se permite otra cuota; solo aporte."
            self.warning.color = DANGER

            for btn in self.tipo_buttons:
                if btn.text == "Aporte":
                    btn.disabled = False
                    btn.state = "down"
                    btn.background_color = GOLD
                    btn.color = DARK
                else:
                    btn.disabled = True
                    btn.state = "normal"
                    btn.background_color = (0.78, 0.80, 0.84, 1)
                    btn.color = (0.40, 0.40, 0.40, 1)

        elif estado in ("no_pago", "siguiente", "reprogramado"):
            self.warning.text = (
                "La visita anterior fue reprogramada. "
                "Puede registrar cuota, aporte o una nueva reprogramación."
            )
            self.warning.color = MUTED

            for btn in self.tipo_buttons:
                if btn.text == "Cuota":
                    btn.disabled = False
                    btn.state = "down"
                    btn.background_color = SUCCESS
                    btn.color = WHITE
                else:
                    btn.disabled = False
                    btn.state = "normal"
                    btn.background_color = (0.88, 0.90, 0.94, 1)
                    btn.color = DARK

        else:
            for btn in self.tipo_buttons:
                if btn.text == "Cuota":
                    btn.state = "down"
                    btn.background_color = SUCCESS
                    btn.color = WHITE
                else:
                    btn.state = "normal"
                    btn.background_color = (0.88, 0.90, 0.94, 1)
                    btn.color = DARK

    def update_tipo_colors(self, *_):
        selected = self.selected_tipo()

        for btn in self.tipo_buttons:
            if btn.disabled:
                continue

            if btn.state == "down":
                if btn.text == "Cuota":
                    btn.background_color = SUCCESS
                    btn.color = WHITE
                    self.warning.text = "Se registrará el pago normal de la cuota."
                    self.warning.color = SUCCESS
                elif btn.text == "Aporte":
                    btn.background_color = GOLD
                    btn.color = DARK
                    self.warning.text = "Se registrará un aporte adicional al saldo."
                    self.warning.color = MUTED
                elif btn.text == "No Pago":
                    btn.background_color = DANGER
                    btn.color = WHITE
                    self.warning.text = "No pagó. Elige una nueva fecha de visita; la cuota seguirá pendiente."
                    self.warning.color = DANGER
                else:
                    btn.background_color = (0.45, 0.48, 0.55, 1)
                    btn.color = WHITE
                    self.warning.text = "Se reprogramará la visita sin descontar ni acreditar cuotas."
                    self.warning.color = MUTED
            else:
                btn.background_color = (0.88, 0.90, 0.94, 1)
                btn.color = DARK

        if selected == "Cuota":
            self.numero_cuotas.readonly = False
            if not str(self.numero_cuotas.text or "").strip():
                self.numero_cuotas.text = "1"
            self.on_installments_changed()

        elif selected == "Aporte":
            # En aporte, las cuotas se calculan según el valor entregado.
            self.numero_cuotas.readonly = True
            self.numero_cuotas.text = "0"
            self.warning.text = (
                "Ingrese cualquier valor. El sistema acumulará el aporte "
                "y acreditará cuotas completas automáticamente."
            )
            self.warning.color = MUTED

        else:
            self.numero_cuotas.readonly = True
            self.numero_cuotas.text = "0"

    def selected_tipo(self):
        for btn in self.tipo_buttons:
            if not btn.disabled and btn.state == "down":
                return btn.text

        estado = self.cliente.get("estado", "pendiente")
        if estado in ("pagado", "aporte"):
            return "Aporte"

        return "Cuota"

    def on_installments_changed(self):
        """
        Permite editar libremente el número de cuotas.

        Mientras el usuario borra o escribe, el sistema no reemplaza el valor.
        Solo calcula el total cuando hay un número válido.
        La validación contra las cuotas pendientes se hace al registrar.
        """
        if self._updating_installment_amount:
            return

        tipo = self.selected_tipo()
        if tipo != "Cuota":
            return

        raw_value = str(self.numero_cuotas.text or "").strip()

        # Permitir que el campo quede vacío mientras el usuario edita.
        if raw_value == "":
            self._updating_installment_amount = True
            self.valor_pagar.text = ""
            self._updating_installment_amount = False
            self.recalculate_balance()
            return

        # Solo aceptar números enteros positivos para el cálculo.
        try:
            cantidad = int(raw_value)
        except ValueError:
            return

        if cantidad <= 0:
            self._updating_installment_amount = True
            self.valor_pagar.text = ""
            self._updating_installment_amount = False
            self.recalculate_balance()
            return

        valor = int(self.cliente.get("cuota", 0)) * cantidad

        self._updating_installment_amount = True
        self.valor_pagar.text = format_thousands(valor)
        self._updating_installment_amount = False
        self.recalculate_balance()

    def recalculate_balance(self):
        saldo = to_int(self.saldo_actual.text, 0)
        pago = to_int(self.valor_pagar.text, 0)
        self.nuevo_saldo.text = format_thousands(max(saldo - pago, 0))

    def show_payment_success_actions(self, receipt):
        """Popup de acciones después de guardar cuota o aporte."""
        content = BoxLayout(
            orientation="vertical",
            padding=dp(14),
            spacing=dp(10),
        )

        msg = Label(
            text=(
                "PAGO REGISTRADO CORRECTAMENTE\n\n"
                f"Cliente: {receipt.get('cliente')}\n"
                f"Código: {receipt.get('codigo')}\n"
                f"Valor: {money(receipt.get('valor', 0))}\n"
                f"Saldo nuevo: {money(receipt.get('saldo_nuevo', 0))}"
            ),
            color=WHITE,
            font_size="13sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(150),
        )
        msg.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        content.add_widget(msg)

        popup = Popup(
            title="Pago registrado",
            content=content,
            size_hint=(0.92, None),
            height=dp(460),
            auto_dismiss=False,
        )

        btn_pdf = Button(
            text="Generar comprobante",
            background_normal="",
            background_color=BLUE,
            color=WHITE,
            bold=True,
            size_hint_y=None,
            height=dp(44),
        )
        btn_whatsapp = Button(
            text="Compartir texto WhatsApp",
            background_normal="",
            background_color=SUCCESS,
            color=WHITE,
            bold=True,
            size_hint_y=None,
            height=dp(44),
        )
        btn_history = Button(
            text="Ver historial",
            background_normal="",
            background_color=GOLD,
            color=DARK,
            bold=True,
            size_hint_y=None,
            height=dp(44),
        )
        btn_close = Button(
            text="Finalizar",
            background_normal="",
            background_color=(0.45, 0.48, 0.55, 1),
            color=WHITE,
            bold=True,
            size_hint_y=None,
            height=dp(44),
        )

        btn_pdf.bind(on_release=lambda *_: self.generate_receipt_pdf(receipt))
        btn_whatsapp.bind(on_release=lambda *_: self.share_receipt_whatsapp(receipt))

        def go_history(*_):
            popup.dismiss()
            self.app_ref.selected_client = self.cliente
            self.app_ref.go("historial_cliente")

        def close_and_return(*_):
            popup.dismiss()
            self.app_ref.go("clientes")

        btn_history.bind(on_release=go_history)
        btn_close.bind(on_release=close_and_return)

        content.add_widget(btn_pdf)
        content.add_widget(btn_whatsapp)
        content.add_widget(btn_history)
        content.add_widget(btn_close)

        popup.open()

    def generate_receipt_pdf(self, receipt):
        try:
            private_pdf_path = generate_payment_receipt_pdf(receipt)
            final_path, open_ok, open_message = publish_pdf_to_downloads(
                private_pdf_path,
                open_after=True,
            )

            if not open_ok:
                show_popup(
                    "Comprobante generado",
                    f"El comprobante fue guardado.\n\nUbicación:\n{final_path}\n\nDetalle:\n{open_message}",
                    height=360,
                )

        except Exception as error:
            show_popup(
                "Error comprobante",
                f"No se pudo generar el comprobante.\n{error}",
                height=280,
            )

    def share_receipt_whatsapp(self, receipt):
        message = receipt_text(receipt)
        ok, detail = share_text_android(message)

        if not ok:
            show_popup(
                "Compartir comprobante",
                "En PC no se puede abrir WhatsApp automáticamente.\n\n"
                "Texto del comprobante:\n"
                f"{message}",
                height=520,
            )

    def _commit_transaction(self):
        if get_journey_status() != "abierta":
            show_popup(
                "Jornada no abierta",
                "Debes abrir la jornada antes de registrar cobros.",
                height=260,
            )
            return

        tipo = self.selected_tipo()
        pago = to_int(self.valor_pagar.text, 0)
        motivo_novedad = self.motivo_novedad.text.strip() if hasattr(self, "motivo_novedad") else ""
        detalle_novedad = self.detalle_novedad.text.strip() if hasattr(self, "detalle_novedad") else ""
        estado_actual = self.cliente.get("estado", "pendiente")
        pendientes_actuales = max(
            int(self.cliente.get("pendientes", 0)),
            0,
        )
        saldo_anterior = int(self.cliente.get("saldo", 0))
        pagadas_anteriores = int(self.cliente.get("pagadas", 0))
        cuota_unitaria = max(int(self.cliente.get("cuota", 0)), 0)
        aporte_anterior = max(
            int(self.cliente.get("aporte_acumulado", 0)),
            0,
        )

        if pendientes_actuales <= 0 or saldo_anterior <= 0:
            show_popup(
                "Crédito finalizado",
                "Este cliente ya no tiene deuda pendiente.",
            )
            return

        cantidad_cuotas = 0
        aporte_nuevo = aporte_anterior

        if tipo == "Cuota":
            raw_cuotas = str(
                self.numero_cuotas.text or ""
            ).strip()

            if raw_cuotas == "":
                show_popup(
                    "Número de cuotas requerido",
                    "Ingrese cuántas cuotas desea acreditar.",
                )
                return

            try:
                cantidad_cuotas = int(raw_cuotas)
            except ValueError:
                show_popup(
                    "Número de cuotas inválido",
                    "Ingrese un número entero.",
                )
                return

            if cantidad_cuotas <= 0:
                show_popup(
                    "Número de cuotas inválido",
                    "El número de cuotas debe ser mayor que cero.",
                )
                return

            if cantidad_cuotas > pendientes_actuales:
                show_popup(
                    "Número de cuotas inválido",
                    f"Solo quedan {pendientes_actuales} cuotas pendientes.",
                )
                return

            valor_minimo = cuota_unitaria * cantidad_cuotas

            if pago < valor_minimo:
                show_popup(
                    "Valor insuficiente",
                    f"Para acreditar {cantidad_cuotas} cuota(s), "
                    f"debe pagar mínimo {money(valor_minimo)}.",
                )
                return

            self.cliente["saldo"] = max(
                saldo_anterior - pago,
                0,
            )
            self.cliente["pagadas"] = (
                pagadas_anteriores + cantidad_cuotas
            )
            self.cliente["pendientes"] = max(
                pendientes_actuales - cantidad_cuotas,
                0,
            )
            self.cliente["aporte_acumulado"] = aporte_anterior
            self.cliente["estado"] = "pagado"
            self.cliente["ultimo_tipo"] = (
                f"{cantidad_cuotas} cuota(s) pagada(s)"
            )

        elif tipo == "Aporte":
            if pago <= 0:
                show_popup(
                    "Valor inválido",
                    "Ingrese un aporte mayor que cero.",
                )
                return

            # El saldo disminuye por todo el dinero recibido.
            self.cliente["saldo"] = max(
                saldo_anterior - pago,
                0,
            )

            total_acumulado = aporte_anterior + pago

            if cuota_unitaria > 0:
                cuotas_completas = (
                    total_acumulado // cuota_unitaria
                )
                cantidad_cuotas = min(
                    int(cuotas_completas),
                    pendientes_actuales,
                )
                aporte_nuevo = (
                    total_acumulado
                    - cantidad_cuotas * cuota_unitaria
                )
            else:
                cantidad_cuotas = 0
                aporte_nuevo = total_acumulado

            self.cliente["pagadas"] = (
                pagadas_anteriores + cantidad_cuotas
            )
            self.cliente["pendientes"] = max(
                pendientes_actuales - cantidad_cuotas,
                0,
            )

            # Si terminó el crédito, no debe quedar aporte residual.
            if (
                self.cliente["saldo"] <= 0
                or self.cliente["pendientes"] <= 0
            ):
                aporte_nuevo = 0

            self.cliente["aporte_acumulado"] = aporte_nuevo

            if cantidad_cuotas > 0:
                self.cliente["estado"] = "aporte"
                self.cliente["ultimo_tipo"] = (
                    f"Aporte de {money(pago)}: "
                    f"{cantidad_cuotas} cuota(s) acreditada(s). "
                    f"Acumulado restante: {money(aporte_nuevo)}"
                )
            else:
                # Sigue amarillo porque aún no completó una cuota.
                self.cliente["estado"] = "pendiente"
                faltante = max(
                    cuota_unitaria - aporte_nuevo,
                    0,
                )
                self.cliente["ultimo_tipo"] = (
                    f"Aporte parcial de {money(pago)}. "
                    f"Acumulado: {money(aporte_nuevo)}. "
                    f"Faltan {money(faltante)} para completar una cuota."
                )

        elif tipo in ("No Pago", "Siguiente Día"):
            pago = 0
            cantidad_cuotas = 0
            nueva_visita = self.selected_rescheduled_visit()

            if not nueva_visita:
                show_popup(
                    "Nueva visita requerida",
                    "Selecciona una nueva fecha futura. Si no pagó o se aplazó, la visita debe quedar reprogramada para que salga de la ruta de hoy y vuelva a aparecer en la nueva fecha.",
                    height=270,
                )
                return

            self.cliente["proximo_cobro"] = nueva_visita

            if tipo == "No Pago":
                self.cliente["estado"] = "no_pago"
                self.cliente["ultimo_tipo"] = (
                    "No pagó. Nueva visita: "
                    f"{display_date_from_iso(nueva_visita)}. "
                    f"Motivo: {motivo_novedad}. "
                    f"{detalle_novedad} "
                    "La cuota continúa pendiente."
                )
            else:
                self.cliente["estado"] = "siguiente"
                self.cliente["ultimo_tipo"] = (
                    "Visita reprogramada para "
                    f"{display_date_from_iso(nueva_visita)}. "
                    f"Motivo: {motivo_novedad}. "
                    f"{detalle_novedad} "
                    "La cuota continúa pendiente."
                )

        if tipo in ("Cuota", "Aporte"):
            self.cliente["ultima_fecha_pago"] = iso_today()

            if (
                self.cliente["pendientes"] <= 0
                or self.cliente["saldo"] <= 0
            ):
                self.cliente["estado"] = "paz_y_salvo"
                self.cliente["ultimo_tipo"] = (
                    "Crédito cancelado - Paz y salvo"
                )
                self.cliente["proximo_cobro"] = ""
                self.cliente["aporte_acumulado"] = 0

            elif cantidad_cuotas > 0:
                # Solo avanza el cronograma cuando se completa al menos
                # una cuota. Un aporte parcial no cambia la fecha.
                self.cliente["proximo_cobro"] = next_visit_after_payment(
                    self.cliente.get("proximo_cobro", ""),
                    self.cliente.get("cobro", "Diario"),
                    cantidad_cuotas,
                )

        self.cliente["synced"] = 0
        update_client_db(self.cliente)

        tx_fecha = now_text()
        tx_id = insert_transaction_db({
            "cliente_id": self.cliente.get("id"),
            "cliente": self.cliente.get("nombre", ""),
            "tipo": tipo,
            "valor": pago,
            "metodo": self.metodo_pago.text,
            "fecha": tx_fecha,
            "numero_cuotas": cantidad_cuotas,
            "saldo_anterior": saldo_anterior,
            "saldo_nuevo": int(
                self.cliente.get("saldo", 0)
            ),
            "cuotas_pagadas_total": int(
                self.cliente.get("pagadas", 0)
            ),
            "cuotas_pendientes_total": int(
                self.cliente.get("pendientes", 0)
            ),
            "observacion": self.cliente.get(
                "ultimo_tipo",
                "",
            ),
            "synced": 0,
        })

        if tipo in ("No Pago", "Siguiente Día"):
            insert_audit_log(
                "Registrar no pago" if tipo == "No Pago" else "Fecha reprogramada",
                self.cliente,
                motivo_novedad,
                detalle_novedad or f"Nueva visita: {display_date_from_iso(self.cliente.get('proximo_cobro', ''))}"
            )

        receipt = {
            "tx_id": tx_id,
            "cliente": self.cliente.get("nombre", ""),
            "codigo": client_code(self.cliente),
            "fecha": tx_fecha,
            "tipo": tipo,
            "valor": pago,
            "saldo_anterior": saldo_anterior,
            "saldo_nuevo": int(self.cliente.get("saldo", 0)),
            "cuotas_pagadas": int(self.cliente.get("pagadas", 0)),
            "cuotas_pendientes": int(self.cliente.get("pendientes", 0)),
            "cobrador": cobrador_nombre(),
        }

        refresh_memory_from_db()

        cliente_actualizado = get_client_by_id(self.cliente.get("id"))
        if cliente_actualizado:
            self.cliente = cliente_actualizado
            self.app_ref.selected_client = cliente_actualizado

        App.get_running_app().request_auto_sync()

        if tipo in ("Aporte", "Cuota"):
            self.show_payment_success_actions(receipt)

        elif tipo in ("No Pago", "Siguiente Día"):
            show_popup(
                "Visita reprogramada",
                f"El cliente saldrá de la lista de hoy.\n"
                f"Nueva visita: "
                f"{display_date_from_iso(self.cliente.get('proximo_cobro', ''))}.\n"
                "La cuota y el saldo permanecen pendientes.",
                height=300,
            )

        else:
            show_popup(
                "Transacción registrada",
                "La novedad fue guardada correctamente.",
            )

        if tipo not in ("Cuota", "Aporte"):
            Clock.schedule_once(
                lambda *_: self.app_ref.go("clientes"),
                0.9,
            )



# ============================================================
# NUEVO CLIENTE WIZARD
# ============================================================

class NuevoClienteScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="nuevo_cliente", **kwargs)
        self.step = 1
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

        self.documento = AppTextInput(hint_text="Número de documento")
        self.nombre = AppTextInput(hint_text="Nombre completo")
        self.movil = AppTextInput(hint_text="3000000000")
        self.direccion = AppTextInput(hint_text="Dirección del cliente")
        self.barrio = AppTextInput(hint_text="Barrio")
        self.zona = AppTextInput(hint_text="Zona")
        self.ruta = AppTextInput(hint_text="Ruta. Ej: Centro")
        self.orden_visita = AppTextInput(hint_text="Orden de visita", input_filter="int")

        self.producto = AppTextInput(text="5 - CREDITO EN EFECTIVO")
        self.valor_credito = MoneyTextInput(hint_text="Ej: 500.000")
        self.interes = AppTextInput(hint_text="Ej: 20")
        self.numero_cuotas = AppTextInput(hint_text="Ej: 30")
        self.total_credito = MoneyTextInput(text="0", readonly=True)
        self.valor_cuota = MoneyTextInput(text="0", readonly=True)
        self.cobro = Spinner(text="Diario", values=["Diario", "Semanal", "Quincenal", "Mensual"], size_hint_y=None, height=dp(44), background_normal="", background_color=WHITE, color=TEXT)

        self.valor_credito.bind(text=lambda *_: self.calculate_credit())
        self.interes.bind(text=lambda *_: self.calculate_credit())
        self.numero_cuotas.bind(text=lambda *_: self.calculate_credit())

        self.documento_codeudor = AppTextInput(hint_text="Opcional")
        self.nombre_codeudor = AppTextInput(hint_text="Opcional")
        self.movil_codeudor = AppTextInput(hint_text="Opcional")

        self.valor_seguro = MoneyTextInput(hint_text="Ej: 10.000")
        self.beneficiario = AppTextInput(hint_text="Nombre beneficiario")
        self.obs_seguro = AppTextInput(hint_text="Observaciones", multiline=True)

        # Tipo de registro:
        # - Nuevo préstamo: genera desembolso y descuenta caja.
        # - Préstamo existente: migra un cartón viejo sin afectar caja.
        self.tipo_registro = Spinner(
            text="Nuevo préstamo",
            values=["Nuevo préstamo", "Préstamo existente"],
            size_hint_y=None,
            height=dp(44),
            background_normal="",
            background_color=WHITE,
            color=TEXT,
        )
        self.tipo_registro.bind(
            text=lambda *_: self.on_record_type_changed()
        )

        self.fecha_inicio_existente = AppTextInput(
            hint_text="Seleccione fecha de inicio",
            readonly=True,
        )
        self.cuotas_pagadas_existente = AppTextInput(
            hint_text="Ej: 7",
            input_filter="int",
        )
        self.cuotas_pendientes_existente = AppTextInput(
            text="0",
            readonly=True,
        )
        self.total_pagado_existente = MoneyTextInput(
            text="0",
            readonly=True,
        )
        self.saldo_existente = MoneyTextInput(
            text="0",
            readonly=True,
        )
        self.aporte_existente = MoneyTextInput(
            hint_text="Aporte parcial acumulado",
        )
        self.proximo_cobro_existente = AppTextInput(
            hint_text="Seleccione próxima fecha",
            readonly=True,
        )

        self.cuotas_pagadas_existente.bind(
            text=lambda *_: self.calculate_existing_status()
        )
        self.aporte_existente.bind(
            text=lambda *_: self.calculate_existing_status()
        )

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()

        if getattr(self, "reset_on_next_entry", False):
            self.clear_form()
            self.reset_on_next_entry = False

        self.build()

    def clear_form(self):
        """
        Limpia todos los campos después de crear un cliente.
        """
        self.documento.text = ""
        self.nombre.text = ""
        self.movil.text = ""
        self.direccion.text = ""
        self.barrio.text = ""
        self.zona.text = ""
        self.ruta.text = ""
        self.orden_visita.text = ""

        self.producto.text = "5 - CREDITO EN EFECTIVO"
        self.valor_credito.text = ""
        self.interes.text = ""
        self.numero_cuotas.text = ""
        self.total_credito.text = "0"
        self.valor_cuota.text = "0"
        self.cobro.text = "Diario"

        self.documento_codeudor.text = ""
        self.nombre_codeudor.text = ""
        self.movil_codeudor.text = ""

        self.valor_seguro.text = ""
        self.beneficiario.text = ""
        self.obs_seguro.text = ""

        self.tipo_registro.text = "Nuevo préstamo"
        self.fecha_inicio_existente.text = ""
        self.cuotas_pagadas_existente.text = ""
        self.cuotas_pendientes_existente.text = "0"
        self.total_pagado_existente.text = "0"
        self.saldo_existente.text = "0"
        self.aporte_existente.text = ""
        self.proximo_cobro_existente.text = ""

    def is_existing_loan(self):
        return self.tipo_registro.text == "Préstamo existente"

    def on_record_type_changed(self):
        """
        Reconstruye el formulario para mostrar u ocultar los campos
        especiales del préstamo existente.
        """
        if hasattr(self, "root") and self.root.children:
            self.build()

    def calculate_existing_status(self):
        """
        Calcula automáticamente el estado económico de una cartulina vieja.

        Regla:
        - Las cuotas pagadas se descuentan del total.
        - El aporte acumulado también baja el saldo.
        - Si el aporte acumulado completa una o más cuotas, se reconocen como
          cuotas pagadas adicionales y solo queda como aporte el sobrante.
        - Este cálculo NO mueve caja, porque el dinero ya fue entregado antes.
        """
        total_installments = max(to_int(self.numero_cuotas.text, 0), 0)
        paid_entered = max(to_int(self.cuotas_pagadas_existente.text, 0), 0)
        installment_value = max(to_int(self.valor_cuota.text, 0), 0)
        total_credit = max(to_int(self.total_credito.text, 0), 0)
        contribution_entered = max(to_int(self.aporte_existente.text, 0), 0)

        paid_base = min(paid_entered, total_installments)
        remaining_slots = max(total_installments - paid_base, 0)

        extra_installments = 0
        if installment_value > 0 and remaining_slots > 0:
            extra_installments = min(
                contribution_entered // installment_value,
                remaining_slots,
            )

        effective_paid_installments = min(
            paid_base + extra_installments,
            total_installments,
        )

        pending_installments = max(
            total_installments - effective_paid_installments,
            0,
        )

        total_paid = min(
            (paid_base * installment_value) + contribution_entered,
            total_credit,
        )

        current_balance = max(total_credit - total_paid, 0)

        self.cuotas_pendientes_existente.text = str(pending_installments)
        self.total_pagado_existente.text = format_thousands(total_paid)
        self.saldo_existente.text = format_thousands(current_balance)


    def open_existing_date_calendar(self, target_input):
        initial_date = normalize_date_input(target_input.text)

        CalendarPopup(
            initial_date=initial_date,
            on_select=lambda selected: self.set_existing_date(
                target_input,
                selected,
            ),
        ).open()

    @staticmethod
    def set_existing_date(target_input, selected_date):
        target_input.text = selected_date.strftime("%d/%m/%Y")

    def calculate_credit(self):
        base = to_int(self.valor_credito.text, 0)
        interes = to_float(self.interes.text, 0)
        cuotas = to_int(self.numero_cuotas.text, 0)

        total = int(round(base * (1 + (interes / 100))))
        cuota = int(round(total / cuotas)) if cuotas > 0 else 0

        self.total_credito.text = format_thousands(total)
        self.valor_cuota.text = format_thousands(cuota)
        self.calculate_existing_status()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Nuevo Cliente y Crédito"))

        scroll = ScrollView(
            do_scroll_x=False,
            bar_width=dp(4),
            scroll_type=["bars", "content"],
        )

        content = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(14), dp(12), dp(100)],
            spacing=dp(14),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        intro = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(86),
            padding=[dp(14), dp(10), dp(14), dp(10)],
            spacing=dp(4),
        )
        intro.bg_color = (0.94, 0.97, 1, 1)

        intro_title = Label(
            text="Registro completo",
            color=TEXT,
            bold=True,
            font_size="16sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(30),
        )
        intro_title.bind(
            size=lambda instance, value: setattr(
                instance, "text_size", value
            )
        )

        intro_text = Label(
            text="Complete todos los datos y guarde el cliente al final.",
            color=MUTED,
            font_size="11sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(30),
        )
        intro_text.bind(
            size=lambda instance, value: setattr(
                instance, "text_size", value
            )
        )

        intro.add_widget(intro_title)
        intro.add_widget(intro_text)
        content.add_widget(intro)

        content.add_widget(
            self.form_card(
                "0",
                "TIPO DE REGISTRO",
                [
                    ("Seleccione una opción", self.tipo_registro),
                ],
                height=dp(138),
            )
        )

        content.add_widget(
            self.form_card(
                "1",
                "DATOS DEL CLIENTE",
                [
                    ("Documento", self.documento),
                    ("Nombre", self.nombre),
                    ("Móvil +57", self.movil),
                    ("Dirección", self.direccion),
                ],
                height=dp(382),
            )
        )

        content.add_widget(
            self.form_card(
                "2",
                "DATOS DEL CRÉDITO",
                [
                    ("Producto", self.producto),
                    ("Valor Crédito", self.valor_credito),
                    ("Interés %", self.interes),
                    ("Número de Cuotas", self.numero_cuotas),
                    ("Total Crédito", self.total_credito),
                    ("Valor Cuota Calculada", self.valor_cuota),
                    ("Cobro", self.cobro),
                ],
                height=dp(536),
            )
        )

        if self.is_existing_loan():
            existing_card = RoundedBox(
                orientation="vertical",
                size_hint_y=None,
                height=dp(668),
                padding=[dp(12), dp(10), dp(12), dp(14)],
                spacing=dp(8),
            )

            existing_header = Label(
                text="ESTADO ACTUAL DEL CARTÓN VIEJO",
                color=BLUE,
                bold=True,
                font_size="14sp",
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(36),
            )
            existing_header.bind(
                size=lambda instance, value: setattr(
                    instance,
                    "text_size",
                    value,
                )
            )
            existing_card.add_widget(existing_header)

            for label, widget in [
                ("Fecha original de inicio", self.fecha_inicio_existente),
                ("Cuotas ya pagadas", self.cuotas_pagadas_existente),
                ("Cuotas pendientes calculadas", self.cuotas_pendientes_existente),
                ("Aporte parcial acumulado", self.aporte_existente),
                ("Total pagado acumulado", self.total_pagado_existente),
                ("Saldo actual calculado", self.saldo_existente),
                ("Próxima fecha real de cobro", self.proximo_cobro_existente),
            ]:
                field = BoxLayout(
                    orientation="vertical",
                    size_hint_y=None,
                    height=dp(72),
                    spacing=dp(5),
                )
                field.add_widget(FieldLabel(label))

                if widget in (
                    self.fecha_inicio_existente,
                    self.proximo_cobro_existente,
                ):
                    date_row = BoxLayout(
                        orientation="horizontal",
                        size_hint_y=None,
                        height=dp(44),
                        spacing=dp(8),
                    )
                    detach_widget(widget)
                    date_row.add_widget(widget)

                    date_button = Button(
                        text="Calendario",
                        size_hint_x=None,
                        width=dp(108),
                        background_normal="",
                        background_color=BLUE,
                        color=WHITE,
                        bold=True,
                    )
                    date_button.bind(
                        on_release=lambda _button, target=widget:
                        self.open_existing_date_calendar(target)
                    )
                    date_row.add_widget(date_button)
                    field.add_widget(date_row)
                else:
                    detach_widget(widget)
                    field.add_widget(widget)

                existing_card.add_widget(field)

            note = Label(
                text=(
                    "Este modo no genera un nuevo egreso de caja. "
                    "Solo carga el estado real del préstamo anterior."
                ),
                color=MUTED,
                font_size="11sp",
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(50),
            )
            note.bind(
                size=lambda instance, value: setattr(
                    instance,
                    "text_size",
                    value,
                )
            )
            existing_card.add_widget(note)
            content.add_widget(existing_card)

        content.add_widget(
            self.form_card(
                "3",
                "CODEUDOR (OPCIONAL)",
                [
                    ("Documento Codeudor", self.documento_codeudor),
                    ("Nombre Codeudor", self.nombre_codeudor),
                    ("Móvil Codeudor", self.movil_codeudor),
                ],
                height=dp(322),
            )
        )

        content.add_widget(
            self.form_card(
                "4",
                "SEGURO (OPCIONAL)",
                [
                    ("Valor Seguro", self.valor_seguro),
                    ("Beneficiario", self.beneficiario),
                    ("Observaciones", self.obs_seguro),
                ],
                height=dp(370),
            )
        )

        create_button = SmallButton(
            "Crear Cliente y Activar Crédito",
            bg_color=SUCCESS,
        )
        create_button.size_hint_y = None
        create_button.height = dp(54)
        create_button.bind(
            on_release=lambda *_: self.create_client()
        )
        content.add_widget(create_button)

        for input_widget in [
            self.documento,
            self.nombre,
            self.movil,
            self.direccion,
            self.producto,
            self.valor_credito,
            self.interes,
            self.numero_cuotas,
            self.documento_codeudor,
            self.nombre_codeudor,
            self.movil_codeudor,
            self.valor_seguro,
            self.beneficiario,
            self.obs_seguro,
            self.fecha_inicio_existente,
            self.cuotas_pagadas_existente,
            self.aporte_existente,
            self.total_pagado_existente,
            self.saldo_existente,
            self.proximo_cobro_existente,
        ]:
            bind_scroll_to_input(scroll, input_widget)

        scroll.add_widget(content)
        self.root.add_widget(scroll)

        nav_container = BoxLayout(
            size_hint_y=None,
            height=dp(66),
        )
        nav_container.add_widget(
            BottomNav(self.app_ref, active="nuevo")
        )
        self.root.add_widget(nav_container)

    def progress_card(self):
        card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(72), padding=[dp(12), dp(8), dp(12), dp(8)], spacing=dp(2))
        card.bg_color = (0.94, 0.97, 1, 1)
        title = Label(text=f"Paso {self.step} de 4", color=TEXT, bold=True, font_size="16sp", halign="left", size_hint_y=None, height=dp(26))
        msg = Label(text="Formulario de producción. Los datos se guardan offline.", color=MUTED, font_size="11sp", halign="left", size_hint_y=None, height=dp(24))
        title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        msg.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        card.add_widget(title)
        card.add_widget(msg)
        return card

    def form_card(self, number, title, fields, height):
        card = RoundedBox(orientation="vertical", size_hint_y=None, height=height, padding=[dp(12), dp(10), dp(12), dp(12)], spacing=dp(7))
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42), spacing=dp(8))
        circle = Label(text=number, color=WHITE, bold=True, font_size="15sp", size_hint_x=None, width=dp(34))
        with circle.canvas.before:
            Color(*BLUE)
            circle.bg = RoundedRectangle(pos=circle.pos, size=circle.size, radius=[dp(17)])
        circle.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
        circle.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))
        lbl = Label(text=title, color=TEXT, bold=True, font_size="14sp", halign="left", valign="middle")
        lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        header.add_widget(circle)
        header.add_widget(lbl)
        card.add_widget(header)

        for label, widget in fields:
            field_box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(66) if not (isinstance(widget, TextInput) and widget.multiline) else dp(108), spacing=dp(3))
            field_box.add_widget(FieldLabel(label))
            detach_widget(widget)
            field_box.add_widget(widget)
            card.add_widget(field_box)

        return card

    def next_step(self):
        if self.step == 1 and not self.nombre.text.strip():
            show_popup("Falta nombre", "Ingrese el nombre del cliente para continuar.")
            return

        if self.step == 2:
            self.calculate_credit()
            base = to_int(self.valor_credito.text, 0)
            cuotas = to_int(self.numero_cuotas.text, 0)
            cuota = to_int(self.valor_cuota.text, 0)
            if base <= 0:
                show_popup("Valor inválido", "Ingrese el valor del crédito.")
                return
            if cuotas <= 0:
                show_popup("Valor inválido", "Ingrese el número de cuotas.")
                return
            if cuota <= 0:
                show_popup("Valor inválido", "La cuota calculada debe ser mayor a cero.")
                return

        self.step += 1
        self.build()

    def previous_step(self):
        if self.step > 1:
            self.step -= 1
            self.build()

    def create_client(self):
        # La caja solo es obligatoria para préstamo nuevo.
        # Las cartulinas/préstamos existentes son migración de cartera:
        # no generan desembolso y no deben mover caja.
        self.calculate_credit()

        nombre = normalize_client_name(self.nombre.text)

        if not nombre:
            show_popup(
                "Falta nombre",
                "Ingrese el nombre del cliente.",
            )
            return

        if client_name_exists(nombre):
            show_popup(
                "Cliente duplicado",
                "Ya existe un cliente registrado con ese nombre.\n"
                "Búsquelo en la lista antes de crear otro préstamo.",
                height=280,
            )
            return

        valor_credito = to_int(self.valor_credito.text, 0)
        total_credito = to_int(self.total_credito.text, 0)
        cuota = to_int(self.valor_cuota.text, 0)
        numero_cuotas = to_int(self.numero_cuotas.text, 0)

        if (
            valor_credito <= 0
            or total_credito <= 0
            or cuota <= 0
            or numero_cuotas <= 0
        ):
            show_popup(
                "Datos incompletos",
                "Revise valor crédito, interés y número de cuotas.",
            )
            return

        existing_loan = self.is_existing_loan()

        pagadas_digitadas = 0
        cuotas_por_aporte = 0
        total_pagado_acumulado = 0

        if existing_loan:
            fecha_inicio_iso = normalize_date_input(
                self.fecha_inicio_existente.text
            )
            proximo_cobro_iso = normalize_date_input(
                self.proximo_cobro_existente.text
            )

            pagadas_digitadas = max(
                to_int(self.cuotas_pagadas_existente.text, 0),
                0,
            )
            aporte_digitado = max(
                to_int(self.aporte_existente.text, 0),
                0,
            )

            if not fecha_inicio_iso:
                show_popup(
                    "Fecha requerida",
                    "Seleccione la fecha original de inicio.",
                )
                return

            if pagadas_digitadas > numero_cuotas:
                show_popup(
                    "Cuotas inválidas",
                    "Las cuotas pagadas no pueden superar el total de cuotas.",
                    height=270,
                )
                return

            # Conversión automática del aporte acumulado en cuotas completas.
            # Ejemplo: cuota 20.000 y aporte 25.000 => 1 cuota adicional
            # y 5.000 quedan como aporte parcial.
            cupos_pendientes = max(numero_cuotas - pagadas_digitadas, 0)
            aporte_acumulado = aporte_digitado

            if cuota > 0 and cupos_pendientes > 0:
                cuotas_por_aporte = min(
                    aporte_digitado // cuota,
                    cupos_pendientes,
                )
                aporte_acumulado = max(
                    aporte_digitado - (cuotas_por_aporte * cuota),
                    0,
                )

            pagadas = min(
                pagadas_digitadas + cuotas_por_aporte,
                numero_cuotas,
            )
            pendientes = max(numero_cuotas - pagadas, 0)

            total_pagado_acumulado = min(
                (pagadas * cuota) + aporte_acumulado,
                total_credito,
            )
            saldo_actual = max(
                total_credito - total_pagado_acumulado,
                0,
            )

            # Actualizar campos visibles para que el usuario vea exactamente
            # lo que se guardará.
            self.cuotas_pendientes_existente.text = str(pendientes)
            self.total_pagado_existente.text = format_thousands(
                total_pagado_acumulado
            )
            self.saldo_existente.text = format_thousands(saldo_actual)

            if not proximo_cobro_iso and pendientes > 0:
                show_popup(
                    "Próxima fecha requerida",
                    "Seleccione la próxima fecha real de cobro.",
                )
                return

            if saldo_actual < 0 or saldo_actual > total_credito:
                show_popup(
                    "Saldo inválido",
                    "El saldo actual debe estar entre cero y el total del crédito.",
                )
                return

            if saldo_actual <= 0 or pendientes <= 0:
                estado = "paz_y_salvo"
                ultimo_tipo = "Crédito cancelado - Paz y salvo"
                proximo_cobro_iso = ""
                aporte_acumulado = 0
            else:
                today = datetime.now().date()
                next_date = datetime.strptime(
                    proximo_cobro_iso,
                    "%Y-%m-%d",
                ).date()

                estado = (
                    "pendiente"
                    if next_date <= today
                    else "pagado"
                )
                ultimo_tipo = "Préstamo existente cargado"

            created_at = datetime.strptime(
                fecha_inicio_iso,
                "%Y-%m-%d",
            ).strftime("%d/%m/%Y 00:00")

        else:
            refresh_memory_from_db()
            ok_cash, msg_cash = require_cash_open("crear préstamo nuevo")
            if not ok_cash:
                show_popup("Caja no abierta", msg_cash, height=290)
                return

            saldo_caja = current_cash_balance()

            if valor_credito > saldo_caja:
                show_popup(
                    "Saldo insuficiente",
                    f"No se puede crear el préstamo.\n"
                    f"Valor a prestar: {money(valor_credito)}\n"
                    f"Saldo disponible en caja: {money(saldo_caja)}\n\n"
                    f"Revise que la caja esté abierta y que el saldo inicial haya quedado guardado.",
                )
                return

            pagadas = 0
            pendientes = numero_cuotas
            saldo_actual = total_credito
            aporte_acumulado = 0
            estado = "pendiente"
            ultimo_tipo = "Pendiente por cobrar"
            proximo_cobro_iso = iso_today()
            created_at = now_text()

        cliente = {
            "documento": self.documento.text.strip(),
            "nombre": nombre,
            "telefono": (
                f"+57 {self.movil.text.strip()}"
                if self.movil.text.strip()
                else ""
            ),
            "direccion": self.direccion.text.strip(),
            "barrio": self.barrio.text.strip(),
            "zona": self.zona.text.strip(),
            "ruta": self.ruta.text.strip(),
            "orden_visita": to_int(self.orden_visita.text, 0),
            "producto": (
                self.producto.text.strip()
                or "5 - CREDITO EN EFECTIVO"
            ),
            "valor_credito": valor_credito,
            "interes": to_float(self.interes.text, 0),
            "total_credito": total_credito,
            "cuota": cuota,
            "numero_cuotas": numero_cuotas,
            "saldo": saldo_actual,
            "pagadas": pagadas,
            "pendientes": pendientes,
            "cobro": self.cobro.text,
            "estado": estado,
            "ultimo_tipo": ultimo_tipo,
            "proximo_cobro": proximo_cobro_iso,
            "ultima_fecha_pago": "",
            "aporte_acumulado": aporte_acumulado,
            "created_at": created_at,
            "synced": 0,
            "codeudor_documento": (
                self.documento_codeudor.text.strip()
            ),
            "codeudor_nombre": (
                self.nombre_codeudor.text.strip()
            ),
            "codeudor_movil": (
                self.movil_codeudor.text.strip()
            ),
            "valor_seguro": to_int(
                self.valor_seguro.text,
                0,
            ),
            "beneficiario": self.beneficiario.text.strip(),
            "obs_seguro": self.obs_seguro.text.strip(),
        }

        cliente_id = insert_client_db(cliente)
        cliente["id"] = cliente_id
        insert_audit_log(
            "Cliente creado" if not existing_loan else "Préstamo existente cargado",
            cliente,
            "Registro inicial",
            f"Ruta: {cliente.get('ruta', '') or 'Sin ruta'} / Orden: {cliente.get('orden_visita', 0)}"
        )

        if existing_loan:
            # Registro inicial para que el historial explique cómo entró.
            # Valor 0 para que no afecte caja ni recaudo.
            insert_transaction_db({
                "cliente_id": cliente_id,
                "cliente": nombre,
                "tipo": "Migración",
                "valor": 0,
                "metodo": "Cartón anterior",
                "fecha": now_text(),
                "numero_cuotas": pagadas,
                "saldo_anterior": total_credito,
                "saldo_nuevo": saldo_actual,
                "cuotas_pagadas_total": pagadas,
                "cuotas_pendientes_total": pendientes,
                "observacion": (
                    "Préstamo existente/cartulina cargado al sistema. "
                    f"Fecha original: {self.fecha_inicio_existente.text}. "
                    f"Cuotas digitadas: {pagadas_digitadas}. "
                    f"Cuotas reconocidas por aporte: {cuotas_por_aporte}. "
                    f"Cuotas pagadas finales: {pagadas}. "
                    f"Aporte parcial restante: {money(aporte_acumulado)}. "
                    f"Total pagado acumulado: {money(total_pagado_acumulado)}. "
                    "No generó egreso de caja ni descontó dinero del cobrador."
                ),
                "synced": 0,
            })
        else:
            insert_movement_db({
                "tipo": "Egreso",
                "concepto": "Desembolso préstamo",
                "valor": valor_credito,
                "observaciones": (
                    f"Préstamo entregado a {nombre}"
                ),
                "fecha": today_text(),
                "synced": 0,
            })

        try:
            sync_clients_to_cloud()
            pull_clients_from_cloud()
        except Exception as error:
            print("SYNC AFTER CLIENT CREATE ERROR:", error)

        refresh_memory_from_db()
        App.get_running_app().request_auto_sync()

        self.reset_on_next_entry = True

        if existing_loan:
            message = (
                "Préstamo existente/cartulina cargado correctamente.\n"
                "No se descontó dinero de caja.\n"
                f"Saldo actual registrado: {money(saldo_actual)}"
            )
        else:
            message = (
                "Cliente y crédito activados correctamente.\n"
                "El desembolso fue descontado de caja."
            )

        show_popup(
            "Registro completado",
            message,
            height=300,
        )
        Clock.schedule_once(
            lambda *_: self.app_ref.go("clientes"),
            0.8,
        )



# ============================================================
# RENOVAR PRÉSTAMO
# ============================================================

class RenovarPrestamoScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="renovar_prestamo", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.cliente = (
            get_client_by_id(self.app_ref.selected_client.get("id"))
            if self.app_ref.selected_client
            else None
        )
        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(
            Header(
                "Renovar Préstamo",
                show_back=True,
                on_back=lambda: self.app_ref.go("gestion_cliente"),
            )
        )

        if not self.cliente:
            self.root.add_widget(
                Label(text="Cliente no encontrado", color=WHITE)
            )
            return

        scroll = ScrollView(
            do_scroll_x=False,
            bar_width=dp(4),
            scroll_type=["bars", "content"],
        )

        content = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(16), dp(14), dp(50)],
            spacing=dp(14),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        renewal = renewal_intelligence(self.cliente)

        summary = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(304),
            padding=dp(14),
            spacing=dp(8),
        )
        summary.add_widget(
            Label(
                text=self.cliente.get("nombre", "SIN NOMBRE"),
                color=TEXT,
                bold=True,
                font_size="18sp",
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(32),
            )
        )
        summary.add_widget(
            DetailRow(
                "Crédito anterior",
                money(self.cliente.get("total_credito", 0)),
            )
        )
        summary.add_widget(
            DetailRow(
                "Saldo anterior",
                money(self.cliente.get("saldo", 0)),
            )
        )
        summary.add_widget(
            DetailRow(
                "Estado",
                "FINALIZADO",
            )
        )
        summary.add_widget(
            DetailRow(
                "Evaluación",
                renewal["estado"],
            )
        )
        summary.add_widget(
            DetailRow(
                "Monto sugerido",
                money(renewal["monto_sugerido"]),
            )
        )
        renewal_msg = Label(
            text=renewal["motivo"],
            color=renewal["color"],
            bold=True,
            font_size="11sp",
            halign="left",
            valign="top",
            size_hint_y=None,
            height=dp(44),
        )
        renewal_msg.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        summary.add_widget(renewal_msg)
        content.add_widget(summary)

        self.valor_credito = MoneyTextInput(
            text=format_thousands(renewal["monto_sugerido"]) if renewal["monto_sugerido"] else ""
        )
        self.interes = AppTextInput(
            text=str(self.cliente.get("interes", 0))
        )
        self.numero_cuotas = AppTextInput(
            input_filter="int"
        )
        self.total_credito = MoneyTextInput(
            text="0",
            readonly=True,
        )
        self.valor_cuota = MoneyTextInput(
            text="0",
            readonly=True,
        )
        self.cobro = Spinner(
            text=self.cliente.get("cobro", "Diario"),
            values=["Diario", "Semanal", "Quincenal", "Mensual"],
            size_hint_y=None,
            height=dp(44),
            background_normal="",
            background_color=WHITE,
            color=TEXT,
        )

        self.valor_credito.bind(
            text=lambda *_: self.calculate_credit()
        )
        self.interes.bind(
            text=lambda *_: self.calculate_credit()
        )
        self.numero_cuotas.bind(
            text=lambda *_: self.calculate_credit()
        )

        form = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(560),
            padding=[dp(16), dp(14), dp(16), dp(16)],
            spacing=dp(10),
        )

        form.add_widget(
            Label(
                text="CONDICIONES DEL NUEVO PRÉSTAMO",
                color=BLUE,
                bold=True,
                font_size="14sp",
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(28),
            )
        )

        for label, widget in [
            ("Valor del nuevo préstamo", self.valor_credito),
            ("Interés %", self.interes),
            ("Número de cuotas", self.numero_cuotas),
            ("Total del nuevo crédito", self.total_credito),
            ("Valor de la cuota", self.valor_cuota),
            ("Frecuencia de cobro", self.cobro),
        ]:
            box = BoxLayout(
                orientation="vertical",
                size_hint_y=None,
                height=dp(68),
                spacing=dp(4),
            )
            box.add_widget(FieldLabel(label))
            box.add_widget(widget)
            form.add_widget(box)

        renew_button = SmallButton(
            "Confirmar Renovación",
            bg_color=SUCCESS,
        )
        renew_button.bind(
            on_release=lambda *_: self.renew_loan()
        )
        form.add_widget(renew_button)

        content.add_widget(form)

        for widget in [
            self.valor_credito,
            self.interes,
            self.numero_cuotas,
        ]:
            bind_scroll_to_input(scroll, widget)

        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def calculate_credit(self):
        principal = to_int(self.valor_credito.text, 0)
        interest = to_float(self.interes.text, 0)
        installments = to_int(self.numero_cuotas.text, 0)

        total = round(principal * (1 + interest / 100))
        installment_value = (
            round(total / installments)
            if installments > 0
            else 0
        )

        self.total_credito.text = format_thousands(total)
        self.valor_cuota.text = format_thousands(
            installment_value
        )

    def renew_loan(self):
        if get_journey_status() != "abierta":
            show_popup(
                "Jornada no abierta",
                "Debes abrir la jornada antes de renovar un préstamo.",
                height=260,
            )
            return

        renewal = renewal_intelligence(self.cliente)
        if not renewal.get("apto", False) and renewal.get("estado") == "RENOVACIÓN NO RECOMENDADA":
            show_popup(
                "Renovación con riesgo",
                renewal.get("motivo", "Revise el comportamiento del cliente antes de renovar."),
                height=280,
            )

        self.calculate_credit()

        principal = to_int(self.valor_credito.text, 0)
        total = to_int(self.total_credito.text, 0)
        installment_value = to_int(self.valor_cuota.text, 0)
        installments = to_int(self.numero_cuotas.text, 0)

        if (
            principal <= 0
            or total <= 0
            or installment_value <= 0
            or installments <= 0
        ):
            show_popup(
                "Datos incompletos",
                "Revise valor, interés y número de cuotas.",
            )
            return

        refresh_memory_from_db()
        ok_cash, msg_cash = require_cash_open("renovar préstamo")
        if not ok_cash:
            show_popup("Caja no abierta", msg_cash, height=290)
            return

        available_cash = current_cash_balance()

        if principal > available_cash:
            show_popup(
                "Saldo insuficiente",
                f"No se puede renovar el préstamo.\n"
                f"Valor a prestar: {money(principal)}\n"
                f"Saldo en caja: {money(available_cash)}",
                height=300,
            )
            return

        previous_total = int(
            self.cliente.get("total_credito", 0)
        )

        self.cliente["valor_credito"] = principal
        self.cliente["interes"] = to_float(
            self.interes.text,
            0,
        )
        self.cliente["total_credito"] = total
        self.cliente["cuota"] = installment_value
        self.cliente["numero_cuotas"] = installments
        self.cliente["saldo"] = total
        self.cliente["pagadas"] = 0
        self.cliente["pendientes"] = installments
        self.cliente["cobro"] = self.cobro.text
        self.cliente["estado"] = "pendiente"
        self.cliente["ultimo_tipo"] = "Préstamo renovado"
        self.cliente["proximo_cobro"] = iso_today()
        self.cliente["ultima_fecha_pago"] = ""
        self.cliente["synced"] = 0

        update_client_db(self.cliente)

        insert_transaction_db({
            "cliente_id": self.cliente.get("id"),
            "cliente": self.cliente.get("nombre", ""),
            "tipo": "Renovación",
            "valor": principal,
            "metodo": "Desembolso",
            "fecha": now_text(),
            "numero_cuotas": 0,
            "saldo_anterior": 0,
            "saldo_nuevo": total,
            "cuotas_pagadas_total": 0,
            "cuotas_pendientes_total": installments,
            "observacion": (
                f"Nuevo préstamo renovado. "
                f"Crédito anterior: {money(previous_total)}"
            ),
            "synced": 0,
        })

        insert_movement_db({
            "tipo": "Egreso",
            "concepto": "Renovación préstamo",
            "valor": principal,
            "observaciones": (
                f"Renovación entregada a "
                f"{self.cliente.get('nombre', '')}"
            ),
            "fecha": today_text(),
            "synced": 0,
        })

        refresh_memory_from_db()
        App.get_running_app().request_auto_sync()

        show_popup(
            "Préstamo renovado",
            "El nuevo préstamo fue activado y el historial anterior se conservó.",
            height=280,
        )

        Clock.schedule_once(
            lambda *_: self.app_ref.go("clientes"),
            0.9,
        )


# ============================================================
# EDITAR CLIENTE
# ============================================================

class EditarClienteScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="editar_cliente", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        refresh_memory_from_db()
        self.cliente = get_client_by_id(self.app_ref.selected_client.get("id")) if self.app_ref.selected_client else None
        if self.cliente:
            self.app_ref.selected_client = self.cliente
        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Editar Cliente / Préstamo", show_back=True, on_back=lambda: self.app_ref.go("gestion_cliente")))

        if not self.cliente:
            self.root.add_widget(Label(text="Cliente no encontrado", color=WHITE))
            return

        scroll = ScrollView(
            do_scroll_x=False,
            bar_width=dp(5),
            scroll_type=["bars", "content"],
        )
        self.edit_scroll = scroll

        content = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(16), dp(14), dp(110)],
            spacing=dp(14),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(1220), padding=[dp(12), dp(12), dp(12), dp(12)], spacing=dp(8))

        self.documento = AppTextInput(text=str(self.cliente.get("documento", "")))
        self.nombre = AppTextInput(text=str(self.cliente.get("nombre", "")))
        telefono = str(self.cliente.get("telefono", "")).replace("+57", "").strip()
        self.movil = AppTextInput(text=telefono)
        self.direccion = AppTextInput(text=str(self.cliente.get("direccion", "")))
        self.barrio = AppTextInput(text=str(self.cliente.get("barrio", "")))
        self.zona = AppTextInput(text=str(self.cliente.get("zona", "")))
        self.ruta = AppTextInput(text=str(self.cliente.get("ruta", "")))
        self.orden_visita = AppTextInput(text=str(self.cliente.get("orden_visita", "")), input_filter="int")
        self.motivo_edicion = Spinner(
            text="Seleccione motivo",
            values=["Corrección de datos", "Cambio de ruta", "Cambio de préstamo", "Solicitud del cliente", "Otro"],
            size_hint_y=None,
            height=dp(44),
            background_normal="",
            background_color=WHITE,
            color=TEXT,
        )
        self.detalle_edicion = AppTextInput(hint_text="Detalle del cambio", multiline=True)
        self.detalle_edicion.height = dp(72)
        self.valor_credito = MoneyTextInput(text=format_thousands(self.cliente.get("valor_credito", 0)))
        self.interes = AppTextInput(text=str(self.cliente.get("interes", 0)))
        self.numero_cuotas = AppTextInput(text=str(self.cliente.get("numero_cuotas", self.cliente.get("pendientes", 1))))
        self.total_credito = MoneyTextInput(text=format_thousands(self.cliente.get("total_credito", self.cliente.get("saldo", 0))), readonly=True)
        self.valor_cuota = MoneyTextInput(text=format_thousands(self.cliente.get("cuota", 0)), readonly=True)
        self.proximo_cobro = AppTextInput(
            text=(
                display_date_from_iso(
                    self.cliente.get("proximo_cobro", "")
                )
                if self.cliente.get("proximo_cobro")
                else ""
            ),
            hint_text="Seleccione la fecha",
            readonly=True,
        )

        self.valor_credito.bind(text=lambda *_: self.calculate_credit())
        self.interes.bind(text=lambda *_: self.calculate_credit())
        self.numero_cuotas.bind(text=lambda *_: self.calculate_credit())

        for label, widget in [
            ("Documento", self.documento),
            ("Nombre", self.nombre),
            ("Móvil +57", self.movil),
            ("Dirección", self.direccion),
            ("Barrio", self.barrio),
            ("Zona", self.zona),
            ("Ruta", self.ruta),
            ("Orden de visita", self.orden_visita),
            ("Valor Crédito", self.valor_credito),
            ("Interés %", self.interes),
            ("Número de Cuotas", self.numero_cuotas),
            ("Total Crédito", self.total_credito),
            ("Valor Cuota", self.valor_cuota),
        ]:
            field = BoxLayout(
                orientation="vertical",
                size_hint_y=None,
                height=dp(72),
                spacing=dp(5),
            )
            field.add_widget(FieldLabel(label))
            field.add_widget(widget)
            card.add_widget(field)

        date_field = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(82),
            spacing=dp(5),
        )
        date_field.add_widget(
            FieldLabel("Próxima Fecha de Cobro")
        )

        date_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(46),
            spacing=dp(8),
        )
        date_row.add_widget(self.proximo_cobro)

        calendar_button = Button(
            text="Calendario",
            size_hint_x=None,
            width=dp(112),
            background_normal="",
            background_color=BLUE,
            color=WHITE,
            bold=True,
        )
        calendar_button.bind(
            on_release=lambda *_: self.open_date_calendar(
                date_field
            )
        )

        date_row.add_widget(calendar_button)
        date_field.add_widget(date_row)
        card.add_widget(date_field)

        motive_field = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(140),
            spacing=dp(6),
        )
        motive_field.add_widget(FieldLabel("Motivo obligatorio del cambio"))
        motive_field.add_widget(self.motivo_edicion)
        motive_field.add_widget(self.detalle_edicion)
        card.add_widget(motive_field)

        save = SmallButton("Guardar Cambios", bg_color=SUCCESS)
        save.bind(on_release=lambda *_: self.save_changes())
        card.add_widget(save)

        content.add_widget(card)
        for input_widget in [w for w in self.walk(restrict=True) if isinstance(w, (AppTextInput, MoneyTextInput))]:
            bind_scroll_to_input(scroll, input_widget)

        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def open_date_calendar(self, date_field=None):
        """
        Abre el calendario y mantiene visible la zona de fecha.
        """
        if date_field is not None and hasattr(self, "edit_scroll"):
            Clock.schedule_once(
                lambda *_: self.edit_scroll.scroll_to(
                    date_field,
                    padding=dp(120),
                    animate=True,
                ),
                0.05,
            )

        initial_date = normalize_date_input(
            self.proximo_cobro.text
        )

        popup = CalendarPopup(
            initial_date=initial_date,
            on_select=self.set_selected_date,
        )
        popup.open()

    def set_selected_date(self, selected_date):
        self.proximo_cobro.text = selected_date.strftime(
            "%d/%m/%Y"
        )

        if hasattr(self, "edit_scroll"):
            Clock.schedule_once(
                lambda *_: self.edit_scroll.scroll_to(
                    self.proximo_cobro,
                    padding=dp(120),
                    animate=True,
                ),
                0.10,
            )

    def calculate_credit(self):
        base = to_int(self.valor_credito.text, 0)
        interes = to_float(self.interes.text, 0)
        cuotas = to_int(self.numero_cuotas.text, 0)
        total = int(round(base * (1 + interes / 100)))
        cuota = int(round(total / cuotas)) if cuotas > 0 else 0
        self.total_credito.text = format_thousands(total)
        self.valor_cuota.text = format_thousands(cuota)

    def save_changes(self):
        self.calculate_credit()
        nombre = normalize_client_name(self.nombre.text)

        if not nombre:
            show_popup(
                "Falta nombre",
                "Ingrese el nombre del cliente.",
            )
            return

        if client_name_exists(
            nombre,
            exclude_client_id=self.cliente.get("id"),
        ):
            show_popup(
                "Nombre duplicado",
                "Ya existe otro cliente registrado con ese nombre.",
                height=260,
            )
            return

        valor_credito = to_int(self.valor_credito.text, 0)
        total_credito = to_int(self.total_credito.text, 0)
        cuota = to_int(self.valor_cuota.text, 0)
        numero_cuotas = to_int(self.numero_cuotas.text, 0)

        if valor_credito < 0 or total_credito < 0 or cuota < 0 or numero_cuotas < 0:
            show_popup("Datos inválidos", "Los valores no pueden ser negativos.")
            return

        motivo_edicion = self.motivo_edicion.text.strip()
        detalle_edicion = self.detalle_edicion.text.strip()

        if motivo_edicion == "Seleccione motivo":
            show_popup("Motivo requerido", "Seleccione el motivo del cambio antes de guardar.", height=250)
            return

        if motivo_edicion == "Otro" and not detalle_edicion:
            show_popup("Detalle requerido", "Escriba el detalle del motivo.", height=250)
            return

        fecha_proxima = normalize_date_input(self.proximo_cobro.text)
        if self.proximo_cobro.text.strip() and not fecha_proxima:
            show_popup("Fecha inválida", "Use DD/MM/AAAA. Ejemplo: 15/06/2026.")
            return

        # Mantener el progreso ya registrado.
        # Si se cambian las condiciones del crédito, el saldo y pendientes se
        # recalculan descontando lo que el cliente ya había pagado.
        saldo_anterior = int(self.cliente.get("saldo", 0))
        total_anterior = int(self.cliente.get("total_credito", saldo_anterior))
        pagadas_anteriores = int(self.cliente.get("pagadas", 0))
        estado_anterior = self.cliente.get("estado", "pendiente")
        ultimo_tipo_anterior = self.cliente.get("ultimo_tipo", "Pendiente por cobrar")

        valor_pagado_acumulado = max(total_anterior - saldo_anterior, 0)
        nuevo_saldo_pendiente = max(total_credito - valor_pagado_acumulado, 0)
        nuevas_pendientes = max(numero_cuotas - pagadas_anteriores, 0)

        self.cliente["documento"] = self.documento.text.strip()
        self.cliente["nombre"] = nombre
        self.cliente["telefono"] = f"+57 {self.movil.text.strip()}" if self.movil.text.strip() else ""
        self.cliente["direccion"] = self.direccion.text.strip()
        self.cliente["barrio"] = self.barrio.text.strip()
        self.cliente["zona"] = self.zona.text.strip()
        self.cliente["ruta"] = self.ruta.text.strip()
        self.cliente["orden_visita"] = to_int(self.orden_visita.text, 0)
        self.cliente["valor_credito"] = valor_credito
        self.cliente["interes"] = to_float(self.interes.text, 0)
        self.cliente["total_credito"] = total_credito
        self.cliente["cuota"] = cuota
        self.cliente["numero_cuotas"] = numero_cuotas

        self.cliente["saldo"] = nuevo_saldo_pendiente
        self.cliente["pagadas"] = pagadas_anteriores
        self.cliente["pendientes"] = nuevas_pendientes

        if nuevas_pendientes <= 0 or nuevo_saldo_pendiente <= 0:
            self.cliente["estado"] = "paz_y_salvo"
            self.cliente["ultimo_tipo"] = "Crédito cancelado - Paz y salvo"
            self.cliente["proximo_cobro"] = ""
        else:
            # Editar la fecha no debe cambiar el estado visual ni borrar
            # la última novedad del cliente.
            self.cliente["estado"] = estado_anterior
            self.cliente["ultimo_tipo"] = ultimo_tipo_anterior
            self.cliente["proximo_cobro"] = fecha_proxima or self.cliente.get("proximo_cobro", "")

        self.cliente["synced"] = 0
        update_client_db(self.cliente)
        insert_audit_log(
            "Cliente editado",
            self.cliente,
            motivo_edicion,
            detalle_edicion or "Modificación de cliente/préstamo"
        )
        refresh_memory_from_db()
        App.get_running_app().request_auto_sync()
        show_popup("Cambios guardados", "Cliente y préstamo actualizados correctamente.")
        Clock.schedule_once(lambda *_: self.app_ref.go("clientes"), 0.7)


# ============================================================
# MOVIMIENTOS DE CAJA
# ============================================================

class MovimientosScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="movimientos", **kwargs)
        root = BoxLayout(orientation="vertical")
        root.add_widget(Header("Movimientos de Caja"))

        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", padding=[dp(12), dp(14), dp(12), dp(80)], spacing=dp(12), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        type_card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(104))
        type_card.add_widget(FieldLabel("Tipo de movimiento"))

        row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(46))
        self.egreso = ToggleButton(text="(*) Egreso", group="movimiento", state="down", background_normal="", background_color=GOLD, color=DARK, bold=True)
        self.ingreso = ToggleButton(text="( ) Ingreso", group="movimiento", background_normal="", background_color=(0.88, 0.90, 0.94, 1), color=TEXT, bold=True)
        self.egreso.bind(on_release=self.update_type)
        self.ingreso.bind(on_release=self.update_type)
        row.add_widget(self.egreso)
        row.add_widget(self.ingreso)
        type_card.add_widget(row)
        content.add_widget(type_card)

        form = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(330))
        form.add_widget(FieldLabel("Concepto"))
        self.concepto = Spinner(text="Seleccione concepto", values=["Caja inicial", "Transporte", "Alimentación", "Papelería", "Recaudo adicional", "Ajuste de caja", "Otro"], size_hint_y=None, height=dp(44), background_normal="", background_color=WHITE, color=TEXT)
        form.add_widget(self.concepto)

        form.add_widget(FieldLabel("Valor"))
        self.valor = MoneyTextInput(hint_text="Ej: 50.000")
        form.add_widget(self.valor)

        form.add_widget(FieldLabel("Observaciones"))
        self.obs = AppTextInput(hint_text="Escriba observaciones", multiline=True)
        form.add_widget(self.obs)

        save = PillButton("Guardar")
        save.bind(on_release=lambda *_: self.save_movement())
        form.add_widget(save)

        content.add_widget(form)
        scroll.add_widget(content)
        root.add_widget(scroll)

        self.nav_container = BoxLayout(size_hint_y=None, height=dp(66))
        root.add_widget(self.nav_container)
        self.add_widget(root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.nav_container.clear_widgets()
        self.nav_container.add_widget(BottomNav(self.app_ref, active="caja"))

    def update_type(self, *_):
        if self.egreso.state == "down":
            self.egreso.text = "(*) Egreso"
            self.ingreso.text = "( ) Ingreso"
        else:
            self.egreso.text = "( ) Egreso"
            self.ingreso.text = "(*) Ingreso"
        self.egreso.background_color = GOLD if self.egreso.state == "down" else (0.88, 0.90, 0.94, 1)
        self.ingreso.background_color = GOLD if self.ingreso.state == "down" else (0.88, 0.90, 0.94, 1)

    def save_movement(self):
        ok_cash, msg_cash = require_cash_open("registrar movimientos")
        if not ok_cash:
            show_popup(
                "Caja no abierta",
                msg_cash,
                height=290,
            )
            return

        tipo = "Egreso" if self.egreso.state == "down" else "Ingreso"
        valor = to_int(self.valor.text, 0)
        if valor <= 0:
            show_popup("Valor inválido", "Ingrese un valor mayor a cero.")
            return

        refresh_memory_from_db()
        saldo_caja = current_cash_balance()

        if tipo == "Egreso" and valor > saldo_caja:
            show_popup(
                "Saldo insuficiente",
                f"No se puede registrar el egreso.\n"
                f"Egreso: {money(valor)}\n"
                f"Saldo en caja: {money(saldo_caja)}"
            )
            return

        insert_movement_db({
            "tipo": tipo,
            "concepto": self.concepto.text,
            "valor": valor,
            "observaciones": self.obs.text,
            "fecha": today_text(),
            "synced": 0,
        })
        refresh_memory_from_db()
        App.get_running_app().request_auto_sync()
        self.valor.text = ""
        self.obs.text = ""
        self.concepto.text = "Seleccione concepto"
        show_popup("Movimiento guardado", f"{tipo} registrado por {money(valor)}.")



# ============================================================
# CAJA CENTRAL / ADMINISTRADOR
# ============================================================

class CajaCentralScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="caja_central", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        refresh_daily_cache()
        self.build()

    def label(self, text_value, color=TEXT, bold=False, size="11sp", height=dp(24), halign="left"):
        lbl = Label(
            text=str(text_value),
            color=color,
            bold=bold,
            font_size=size,
            halign=halign,
            valign="middle",
            size_hint_y=None,
            height=height,
        )
        lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        return lbl

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Caja Central", show_back=True, on_back=lambda: self.app_ref.go("resumen")))

        if not is_admin_role():
            self.root.add_widget(Label(text="Solo administrador", color=WHITE))
            return

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
        content = BoxLayout(orientation="vertical", padding=[dp(14), dp(14), dp(14), dp(90)], spacing=dp(14), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        balance = central_cash_balance()
        summary = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(150), padding=dp(14), spacing=dp(8))
        summary.bg_color = BLUE_DARK
        summary.add_widget(self.label("SALDO CAJA CENTRAL", WHITE, True, "15sp", dp(30), "center"))
        summary.add_widget(self.label(money(balance), GOLD if balance > 0 else WHITE, True, "25sp", dp(48), "center"))
        summary.add_widget(self.label("Aquí se controla el dinero que administra el negocio y las bases entregadas a cobradores.", (0.88,0.92,1,1), False, "10.5sp", dp(44), "center"))
        content.add_widget(summary)

        add_card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(205), padding=dp(14), spacing=dp(8))
        add_card.bg_color = (0.98,0.99,1,1)
        add_card.add_widget(self.label("Ingresar dinero a caja central", BLUE_DARK, True, "14sp", dp(28)))
        self.central_amount = MoneyTextInput(hint_text="Ej: 5.000.000")
        self.central_obs = AppTextInput(hint_text="Observación. Ej: capital inicial", multiline=True)
        self.central_obs.height = dp(58)
        add_card.add_widget(self.central_amount)
        add_card.add_widget(self.central_obs)
        btn_add = Button(text="Guardar ingreso central", background_normal="", background_color=SUCCESS, color=WHITE, bold=True, size_hint_y=None, height=dp(44))
        btn_add.bind(on_release=lambda *_: self.save_central_income())
        add_card.add_widget(btn_add)
        content.add_widget(add_card)

        hand_card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(275), padding=dp(14), spacing=dp(8))
        hand_card.bg_color = (0.98,0.99,1,1)
        hand_card.add_widget(self.label("Entregar base a cobrador", BLUE_DARK, True, "14sp", dp(28)))

        collectors = [u for u in load_app_users(active_only=True) if str(u.get("rol","")).lower() == "cobrador"]
        self.collector_map = {f"{u.get('nombre') or u.get('usuario')}": u for u in collectors}
        names = list(self.collector_map.keys()) or ["Sin cobradores"]
        self.collector_spinner = Spinner(text=names[0], values=names, size_hint_y=None, height=dp(44), background_normal="", background_color=WHITE, color=TEXT)
        self.base_amount = MoneyTextInput(hint_text="Base. Ej: 1.000.000")
        self.base_obs = AppTextInput(hint_text="Observación de entrega", multiline=True)
        self.base_obs.height = dp(58)
        hand_card.add_widget(self.collector_spinner)
        hand_card.add_widget(self.base_amount)
        hand_card.add_widget(self.base_obs)
        btn_hand = Button(text="Entregar base", background_normal="", background_color=GOLD, color=DARK, bold=True, size_hint_y=None, height=dp(44))
        btn_hand.bind(on_release=lambda *_: self.save_base_to_collector())
        hand_card.add_widget(btn_hand)
        content.add_widget(hand_card)

        liquidation_card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(335), padding=dp(14), spacing=dp(8))
        liquidation_card.bg_color = (0.98,0.99,1,1)
        liquidation_card.add_widget(self.label("Liquidar cobrador cerrado", BLUE_DARK, True, "14sp", dp(28)))
        self.liq_collector_spinner = Spinner(text=names[0], values=names, size_hint_y=None, height=dp(44), background_normal="", background_color=WHITE, color=TEXT)
        self.next_base = MoneyTextInput(hint_text="Base que conserva para próxima jornada")
        self.received_cash = MoneyTextInput(hint_text="Dinero que entrega al admin")
        self.liq_obs = AppTextInput(hint_text="Observación de liquidación", multiline=True)
        self.liq_obs.height = dp(58)
        liquidation_card.add_widget(self.liq_collector_spinner)
        liquidation_card.add_widget(self.next_base)
        liquidation_card.add_widget(self.received_cash)
        liquidation_card.add_widget(self.liq_obs)
        btn_liq = Button(text="Liquidar cobrador", background_normal="", background_color=BLUE, color=WHITE, bold=True, size_hint_y=None, height=dp(44))
        btn_liq.bind(on_release=lambda *_: self.save_liquidation())
        liquidation_card.add_widget(btn_liq)
        content.add_widget(liquidation_card)

        overview = RoundedBox(orientation="vertical", size_hint_y=None, padding=dp(14), spacing=dp(8))
        overview.bind(minimum_height=overview.setter("height"))
        overview.bg_color = (0.92,0.96,1,1)
        overview.add_widget(self.label("Control por cobrador", BLUE_DARK, True, "14sp", dp(28)))
        for item in cash_summary_by_collector():
            cid = item.get("cobrador_id")
            suggested = suggested_opening_base_for_collector(cid)
            close = last_closed_cash_by_collector(cid)
            counted = safe_int(close.get("efectivo_contado", 0)) if close else 0
            row_text = (
                f"{item.get('nombre')} · {str(item.get('estado')).upper()}\\n"
                f"Saldo esperado: {money(item.get('saldo_esperado', 0))} · "
                f"Último contado: {money(counted)} · "
                f"Base sugerida próxima: {money(suggested)}"
            )
            overview.add_widget(self.label(row_text, TEXT, False, "10.5sp", dp(54)))
        content.add_widget(overview)

        movements = central_cash_movements()[:8]
        mov_card = RoundedBox(orientation="vertical", size_hint_y=None, padding=dp(14), spacing=dp(8))
        mov_card.bind(minimum_height=mov_card.setter("height"))
        mov_card.bg_color = WHITE
        mov_card.add_widget(self.label("Últimos movimientos caja central", BLUE_DARK, True, "14sp", dp(28)))
        if not movements:
            mov_card.add_widget(self.label("No hay movimientos en caja central.", MUTED, False, "11sp", dp(40)))
        for mov in movements:
            mov_card.add_widget(self.label(f"{mov.get('fecha')} · {mov.get('tipo')} · {mov.get('concepto')} · {money(mov.get('valor',0))}", TEXT, False, "10sp", dp(34)))
        content.add_widget(mov_card)

        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def save_central_income(self):
        try:
            add_central_cash(to_int(self.central_amount.text, 0), self.central_obs.text)
            sync_movements_to_cloud()
            self.central_amount.text = ""
            self.central_obs.text = ""
            show_popup("Caja central", "Ingreso registrado correctamente.", height=240)
            self.build()
        except Exception as error:
            show_popup("No se pudo guardar", str(error), height=290)

    def selected_collector_id(self, spinner):
        user = self.collector_map.get(spinner.text)
        if not user:
            raise ValueError("Seleccione un cobrador válido.")
        return user.get("cobrador_id")

    def save_base_to_collector(self):
        try:
            cid = self.selected_collector_id(self.collector_spinner)
            hand_base_to_collector(cid, to_int(self.base_amount.text, 0), self.base_obs.text)
            sync_movements_to_cloud()
            self.base_amount.text = ""
            self.base_obs.text = ""
            show_popup("Base entregada", "La base quedó registrada y descontada de caja central.", height=280)
            self.build()
        except Exception as error:
            show_popup("No se pudo entregar base", str(error), height=320)

    def save_liquidation(self):
        try:
            cid = self.selected_collector_id(self.liq_collector_spinner)
            result = liquidate_collector_cash(
                cid,
                to_int(self.next_base.text, 0),
                to_int(self.received_cash.text, 0),
                self.liq_obs.text,
            )
            sync_movements_to_cloud()
            self.next_base.text = ""
            self.received_cash.text = ""
            self.liq_obs.text = ""
            show_popup(
                "Liquidación guardada",
                f"Debe entregar: {money(result['should_receive'])}\\n"
                f"Entregó: {money(result['received_cash'])}\\n"
                f"Base próxima: {money(result['next_base'])}\\n"
                f"Diferencia: {money(result['difference'])}",
                height=340,
            )
            self.build()
        except Exception as error:
            show_popup("No se pudo liquidar", str(error), height=340)



# ============================================================
# RESUMEN
# ============================================================

class MetricRow(BoxLayout):
    def __init__(self, left, right, highlight=False, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48) if not highlight else dp(56),
            padding=[dp(10), dp(4), dp(10), dp(4)],
            spacing=dp(8),
            **kwargs
        )
        bg_color = (0.98, 0.98, 1, 1) if not highlight else (1.0, 0.95, 0.78, 1)
        with self.canvas.before:
            Color(*bg_color)
            self.bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
        self.bind(pos=self._update_bg, size=self._update_bg)

        left_label = Label(
            text=str(left),
            color=TEXT if highlight else MUTED,
            bold=highlight,
            font_size="11.5sp",
            halign="left",
            valign="middle",
            size_hint_x=0.46,
        )
        right_label = Label(
            text=str(right),
            color=TEXT,
            bold=highlight,
            font_size="11.5sp",
            halign="right",
            valign="middle",
            size_hint_x=0.54,
        )
        left_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        right_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        self.add_widget(left_label)
        self.add_widget(right_label)

    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size



class ClientesPagaronHoyScreen(Screen):
    """
    Muestra únicamente los pagos realizados en la fecha actual.

    Los pagos no se eliminan de la base de datos: al cambiar el día dejan de
    aparecer aquí, pero permanecen en el historial completo del cliente.
    """

    def __init__(self, **kwargs):
        super().__init__(name="clientes_pagaron_hoy", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        refresh_daily_cache()
        self.build()

    def build(self):
        self.root.clear_widgets()

        self.root.add_widget(
            Header(
                "Clientes que Pagaron Hoy",
                show_back=True,
                on_back=lambda: self.app_ref.go("resumen"),
            )
        )

        metrics = daily_metrics()
        payments = metrics["payments"]

        # Cantidad real de clientes, evitando contar dos veces a quien pagó
        # más de una vez durante el mismo día.
        unique_clients = {
            str(payment.get("cliente", "")).strip().upper()
            for payment in payments
            if str(payment.get("cliente", "")).strip()
        }

        total_paid = sum(
            int(payment.get("valor", 0))
            for payment in payments
        )

        scroll = ScrollView(
            do_scroll_x=False,
            bar_width=dp(4),
            scroll_type=["bars", "content"],
        )

        content = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(14), dp(12), dp(32)],
            spacing=dp(12),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        summary = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(174),
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(8),
        )

        summary.add_widget(DetailRow("Fecha consultada", today_text()))
        summary.add_widget(
            DetailRow("Clientes que pagaron", str(len(unique_clients)))
        )
        summary.add_widget(
            DetailRow("Pagos registrados", str(len(payments)))
        )
        summary.add_widget(
            DetailRow("Total recaudado", money(total_paid))
        )
        summary.add_widget(
            DetailRow(
                "Estado jornada",
                {
                    "sin_abrir": "SIN ABRIR",
                    "abierta": "ABIERTA",
                    "cerrada": "CERRADA",
                }.get(get_journey_status(), "SIN ABRIR"),
            )
        )
        content.add_widget(summary)

        notice = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(72),
            padding=[dp(12), dp(8), dp(12), dp(8)],
            spacing=dp(2),
        )
        notice.bg_color = (0.92, 0.96, 1, 1)

        notice_title = Label(
            text="LISTADO SOLO DEL DÍA ACTUAL",
            color=BLUE,
            bold=True,
            font_size="12sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(22),
        )
        notice_title.bind(
            size=lambda instance, value: setattr(
                instance, "text_size", value
            )
        )

        notice_text = Label(
            text=(
                "Mañana esta lista comenzará vacía. "
                "Los pagos seguirán disponibles en el historial del cliente."
            ),
            color=MUTED,
            font_size="11sp",
            halign="left",
            valign="middle",
        )
        notice_text.bind(
            size=lambda instance, value: setattr(
                instance, "text_size", value
            )
        )

        notice.add_widget(notice_title)
        notice.add_widget(notice_text)
        content.add_widget(notice)

        if not payments:
            empty = RoundedBox(
                orientation="vertical",
                size_hint_y=None,
                height=dp(132),
                padding=dp(16),
                spacing=dp(8),
            )

            empty_title = Label(
                text="No hay pagos registrados hoy",
                color=TEXT,
                bold=True,
                font_size="15sp",
                halign="center",
                valign="middle",
                size_hint_y=None,
                height=dp(32),
            )
            empty_title.bind(
                size=lambda instance, value: setattr(
                    instance, "text_size", value
                )
            )

            empty_message = Label(
                text=(
                    "Los clientes aparecerán aquí después de registrar "
                    "una cuota o un aporte."
                ),
                color=MUTED,
                font_size="12sp",
                halign="center",
                valign="middle",
            )
            empty_message.bind(
                size=lambda instance, value: setattr(
                    instance, "text_size", value
                )
            )

            empty.add_widget(empty_title)
            empty.add_widget(empty_message)
            content.add_widget(empty)

        else:
            for payment in reversed(payments):
                content.add_widget(self.payment_card(payment))

        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def payment_card(self, payment):
        payment_type = str(payment.get("tipo", "Pago") or "Pago")
        accent = GOLD if payment_type.lower() == "aporte" else SUCCESS

        client_name = str(
            payment.get("cliente", "SIN NOMBRE") or "SIN NOMBRE"
        ).strip()

        amount = money(payment.get("valor", 0))
        payment_date = str(payment.get("fecha", "") or "")
        payment_time = (
            payment_date.split(" ")[1]
            if " " in payment_date
            else payment_date
        )

        card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(132),
            padding=[dp(14), dp(10), dp(14), dp(10)],
            spacing=dp(6),
        )

        header = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(34),
            spacing=dp(8),
        )

        name_label = Label(
            text=client_name,
            color=TEXT,
            bold=True,
            font_size="15sp",
            halign="left",
            valign="middle",
            size_hint_x=0.62,
        )
        name_label.bind(
            size=lambda instance, value: setattr(
                instance, "text_size", value
            )
        )

        amount_label = Label(
            text=amount,
            color=accent,
            bold=True,
            font_size="15sp",
            halign="right",
            valign="middle",
            size_hint_x=0.38,
        )
        amount_label.bind(
            size=lambda instance, value: setattr(
                instance, "text_size", value
            )
        )

        header.add_widget(name_label)
        header.add_widget(amount_label)
        card.add_widget(header)

        information = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(28),
            spacing=dp(8),
        )

        type_label = Label(
            text=f"{payment_type}",
            color=MUTED,
            font_size="12sp",
            halign="left",
            valign="middle",
            size_hint_x=0.5,
        )
        type_label.bind(
            size=lambda instance, value: setattr(
                instance, "text_size", value
            )
        )

        time_label = Label(
            text=f"Hora: {payment_time}",
            color=MUTED,
            font_size="12sp",
            halign="right",
            valign="middle",
            size_hint_x=0.5,
        )
        time_label.bind(
            size=lambda instance, value: setattr(
                instance, "text_size", value
            )
        )

        information.add_widget(type_label)
        information.add_widget(time_label)
        card.add_widget(information)

        view_button = SmallButton(
            "Ver comprobante de pago",
            bg_color=BLUE,
        )
        view_button.height = dp(42)
        view_button.bind(
            on_release=lambda *_: self.show_payment_receipt(payment)
        )
        card.add_widget(view_button)

        return card

    def show_payment_receipt(self, payment):
        client_name = str(
            payment.get("cliente", "SIN NOMBRE") or "SIN NOMBRE"
        )
        payment_type = str(payment.get("tipo", "Pago") or "Pago")
        payment_date = str(payment.get("fecha", "") or "")
        amount = money(payment.get("valor", 0))
        installments = str(payment.get("numero_cuotas", 0))
        balance_before = money(payment.get("saldo_anterior", 0))
        balance_after = money(payment.get("saldo_nuevo", 0))
        method = str(payment.get("metodo") or "No aplica")
        detail = str(
            payment.get("observacion")
            or payment.get("detalle")
            or "Pago registrado correctamente"
        )

        content = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(8),
        )

        title = Label(
            text=client_name,
            color=WHITE,
            bold=True,
            font_size="17sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(38),
        )
        title.bind(
            size=lambda instance, value: setattr(
                instance, "text_size", value
            )
        )
        content.add_widget(title)

        receipt = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(260),
            padding=dp(12),
            spacing=dp(6),
        )
        receipt.add_widget(DetailRow("Tipo de pago", payment_type))
        receipt.add_widget(DetailRow("Valor recibido", amount))
        receipt.add_widget(DetailRow("Fecha y hora", payment_date))
        receipt.add_widget(DetailRow("Cuotas acreditadas", installments))
        receipt.add_widget(DetailRow("Saldo anterior", balance_before))
        receipt.add_widget(DetailRow("Saldo después", balance_after))
        receipt.add_widget(DetailRow("Método", method))

        detail_box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(62),
            spacing=dp(2),
        )
        detail_title = Label(
            text="Detalle",
            color=MUTED,
            bold=True,
            font_size="12sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(20),
        )
        detail_title.bind(
            size=lambda instance, value: setattr(
                instance, "text_size", value
            )
        )
        detail_value = Label(
            text=detail,
            color=TEXT,
            font_size="12sp",
            halign="left",
            valign="top",
        )
        detail_value.bind(
            size=lambda instance, value: setattr(
                instance, "text_size", value
            )
        )
        detail_box.add_widget(detail_title)
        detail_box.add_widget(detail_value)
        receipt.add_widget(detail_box)
        content.add_widget(receipt)

        close_button = Button(
            text="Cerrar comprobante",
            background_normal="",
            background_color=BLUE,
            color=WHITE,
            bold=True,
            size_hint_y=None,
            height=dp(46),
        )
        content.add_widget(close_button)

        popup = Popup(
            title="Constancia del Pago",
            content=content,
            size_hint=(0.92, None),
            height=dp(470),
            auto_dismiss=False,
        )
        close_button.bind(on_release=popup.dismiss)
        popup.open()


class CierresSemanalesScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="cierres_semanales", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(
            Header(
                "Historial de Cierres Semanales",
                show_back=True,
                on_back=lambda: self.app_ref.go("resumen"),
            )
        )

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(14), dp(12), dp(30)],
            spacing=dp(12),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        closures = load_weekly_closures()
        if not closures:
            empty = RoundedBox(
                orientation="vertical", size_hint_y=None,
                height=dp(130), padding=dp(16), spacing=dp(8),
            )
            title = Label(
                text="Todavía no hay cierres semanales",
                color=TEXT, bold=True, font_size="15sp",
                halign="center", valign="middle",
            )
            title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            empty.add_widget(title)
            content.add_widget(empty)
        else:
            for closure in closures:
                content.add_widget(self.closure_card(closure))

        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def closure_card(self, closure):
        status = str(closure.get("estado", "sin_abrir"))
        difference = int(closure.get("diferencia_caja", 0) or 0)
        card = RoundedBox(
            orientation="vertical", size_hint_y=None,
            height=dp(340), padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(6),
        )

        start = display_date_from_iso(closure.get("periodo_inicio", ""))
        end = display_date_from_iso(closure.get("periodo_fin", ""))
        title = Label(
            text=f"Semana {start} al {end}",
            color=BLUE, bold=True, font_size="15sp",
            halign="left", valign="middle",
            size_hint_y=None, height=dp(30),
        )
        title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        card.add_widget(title)
        card.add_widget(DetailRow("Estado", "CERRADA" if status == "cerrada" else "ABIERTA"))
        card.add_widget(DetailRow("Caja inicial", money(closure.get("caja_inicial", 0))))
        card.add_widget(DetailRow("Recaudo semanal", money(closure.get("recaudo", 0))))
        card.add_widget(DetailRow("Ingresos", money(closure.get("ingresos", 0))))
        card.add_widget(DetailRow("Egresos", money(closure.get("egresos", 0))))
        card.add_widget(DetailRow("Desembolsos", money(closure.get("desembolsos", 0))))
        card.add_widget(DetailRow("Saldo final", money(closure.get("saldo_final", 0))))
        card.add_widget(DetailRow("Efectivo contado", money(closure.get("efectivo_contado", 0))))
        card.add_widget(DetailRow("Diferencia", money(difference)))
        card.add_widget(DetailRow("Pagos registrados", str(closure.get("pagos", 0))))
        card.add_widget(DetailRow("Clientes activos", str(closure.get("clientes_activos", 0))))
        card.add_widget(DetailRow("Cartera pendiente", money(closure.get("cartera_pendiente", 0))))
        return card


class CarteraCalleScreen(Screen):
    """Resumen visual y profesional de la cartera pendiente por recuperar."""

    def __init__(self, **kwargs):
        super().__init__(name="cartera_calle", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)
        self.current_filter = "todos"

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        refresh_clients_cache()
        self.build()

    def get_debtors_data(self):
        today = iso_today()
        debtors = [
            cliente for cliente in CLIENTES
            if (
                int(cliente.get("saldo", 0) or 0) > 0
                and int(cliente.get("pendientes", 0) or 0) > 0
                and cliente.get("estado") != "paz_y_salvo"
            )
        ]

        overdue = [
            cliente for cliente in debtors
            if (
                cliente.get("estado") == "no_pago"
                or (
                    cliente.get("proximo_cobro")
                    and cliente.get("proximo_cobro") < today
                )
            )
        ]
        due_today = [
            cliente for cliente in debtors
            if cliente.get("proximo_cobro") == today
        ]
        up_to_date = [
            cliente for cliente in debtors
            if cliente not in overdue and cliente not in due_today
        ]

        return {
            "today": today,
            "debtors": debtors,
            "overdue": overdue,
            "due_today": due_today,
            "up_to_date": up_to_date,
            "total_outstanding": sum(int(c.get("saldo", 0) or 0) for c in debtors),
            "overdue_amount": sum(int(c.get("saldo", 0) or 0) for c in overdue),
            "today_amount": sum(int(c.get("saldo", 0) or 0) for c in due_today),
            "up_to_date_amount": sum(int(c.get("saldo", 0) or 0) for c in up_to_date),
            "average_balance": (sum(int(c.get("saldo", 0) or 0) for c in debtors) // len(debtors)) if debtors else 0,
        }

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(
            Header(
                "Cartera en la Calle",
                show_back=True,
                on_back=lambda: self.app_ref.go("resumen"),
            )
        )

        data = self.get_debtors_data()
        debtors = data["debtors"]
        overdue = data["overdue"]
        due_today = data["due_today"]
        up_to_date = data["up_to_date"]
        total_outstanding = data["total_outstanding"]
        overdue_amount = data["overdue_amount"]
        today_amount = data["today_amount"]
        up_to_date_amount = data["up_to_date_amount"]
        average_balance = data["average_balance"]

        scroll = ScrollView(
            do_scroll_x=False,
            bar_width=dp(4),
            scroll_type=["bars", "content"],
        )
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(14), dp(12), dp(34)],
            spacing=dp(12),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        hero = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(150),
            padding=[dp(16), dp(14), dp(16), dp(14)],
            spacing=dp(6),
        )
        hero.bg_color = (0.93, 0.96, 1, 1)
        title = Label(
            text="CARTERA TOTAL PENDIENTE",
            color=BLUE,
            bold=True,
            font_size="12sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(24),
        )
        amount = Label(
            text=money(total_outstanding),
            color=DARK,
            bold=True,
            font_size="28sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(44),
        )
        subtitle = Label(
            text=(
                f"{len(debtors)} cliente(s) con saldo pendiente. "
                f"Promedio por cliente: {money(average_balance)}"
            ),
            color=MUTED,
            font_size="11sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(32),
        )
        note = Label(
            text="Este panel te muestra cuánto dinero tienes prestado actualmente en la calle.",
            color=TEXT,
            font_size="11sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(26),
        )
        for lbl in (title, amount, subtitle, note):
            lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        hero.add_widget(title)
        hero.add_widget(amount)
        hero.add_widget(subtitle)
        hero.add_widget(note)
        content.add_widget(hero)

        row_a = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(82))
        row_a.add_widget(self.metric_tile("Vencida", money(overdue_amount), f"{len(overdue)} cliente(s)", (1.00, 0.94, 0.94, 1), DANGER))
        row_a.add_widget(self.metric_tile("Para hoy", money(today_amount), f"{len(due_today)} cliente(s)", (1.00, 0.97, 0.88, 1), GOLD))
        content.add_widget(row_a)

        row_b = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(82))
        row_b.add_widget(self.metric_tile("Al día", money(up_to_date_amount), f"{len(up_to_date)} cliente(s)", (0.92, 0.98, 0.94, 1), SUCCESS))
        row_b.add_widget(self.metric_tile("Promedio", money(average_balance), "por cliente", (0.94, 0.95, 0.98, 1), BLUE))
        content.add_widget(row_b)

        filter_box = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(116),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(8),
        )
        filter_title = Label(
            text="Filtra y revisa la cartera",
            color=TEXT,
            bold=True,
            font_size="13sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(24),
        )
        filter_help = Label(
            text="Puedes ver toda la cartera o concentrarte en los clientes vencidos, para hoy o al día.",
            color=MUTED,
            font_size="10.5sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(22),
        )
        for lbl in (filter_title, filter_help):
            lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        filter_box.add_widget(filter_title)
        filter_box.add_widget(filter_help)

        row = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(42))
        for text_btn, key in [
            ("Todos", "todos"),
            ("Vencidos", "vencidos"),
            ("Hoy", "hoy"),
            ("Al día", "al_dia"),
        ]:
            row.add_widget(self.filter_button(text_btn, key))
        filter_box.add_widget(row)
        content.add_widget(filter_box)

        if self.current_filter == "vencidos":
            visible = overdue
            filter_name = "vencidos"
        elif self.current_filter == "hoy":
            visible = due_today
            filter_name = "para cobro hoy"
        elif self.current_filter == "al_dia":
            visible = up_to_date
            filter_name = "al día"
        else:
            visible = debtors
            filter_name = "en cartera"

        visible = sorted(visible, key=lambda c: int(c.get("saldo", 0) or 0), reverse=True)
        visible_amount = sum(int(c.get("saldo", 0) or 0) for c in visible)

        section_card = RoundedBox(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(76),
            padding=[dp(14), dp(10), dp(14), dp(10)],
            spacing=dp(12),
        )
        left_box = BoxLayout(
            orientation="vertical",
            spacing=dp(4),
            size_hint_x=0.66,
        )
        section_title = Label(
            text=f"Detalle de clientes {filter_name}",
            color=TEXT,
            bold=True,
            font_size="13sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(26),
        )
        section_sub = Label(
            text=f"Mostrando {len(visible)} cliente(s)",
            color=MUTED,
            font_size="10.5sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(22),
        )
        for lbl in (section_title, section_sub):
            lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        left_box.add_widget(section_title)
        left_box.add_widget(section_sub)

        right_value = Label(
            text=money(visible_amount),
            color=BLUE,
            bold=True,
            font_size="17sp",
            halign="right",
            valign="middle",
            size_hint_x=0.34,
            text_size=(None, None),
        )
        right_value.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        section_card.add_widget(left_box)
        section_card.add_widget(right_value)
        content.add_widget(section_card)

        if not visible:
            empty = RoundedBox(
                orientation="vertical",
                size_hint_y=None,
                height=dp(120),
                padding=[dp(16), dp(18), dp(16), dp(18)],
                spacing=dp(8),
            )
            empty.bg_color = (0.97, 0.98, 1, 1)
            empty_title = Label(
                text="No hay clientes en este filtro",
                color=TEXT,
                bold=True,
                font_size="14sp",
                halign="center",
                valign="middle",
            )
            empty_help = Label(
                text="Prueba otro filtro o vuelve a la lista principal para seguir gestionando clientes.",
                color=MUTED,
                font_size="11sp",
                halign="center",
                valign="middle",
            )
            for lbl in (empty_title, empty_help):
                lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            empty.add_widget(empty_title)
            empty.add_widget(empty_help)
            content.add_widget(empty)
        else:
            for cliente in visible:
                content.add_widget(self.debtor_card(cliente, data["today"]))

        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def metric_tile(self, title, value, subtitle, bg_color, accent_color):
        card = RoundedBox(
            orientation="vertical",
            size_hint_x=0.5,
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(4),
        )
        card.bg_color = bg_color

        lbl_title = Label(
            text=title,
            color=MUTED,
            bold=True,
            font_size="11sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(18),
        )
        lbl_value = Label(
            text=str(value),
            color=accent_color,
            bold=True,
            font_size="18sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(28),
        )
        lbl_sub = Label(
            text=subtitle,
            color=TEXT,
            font_size="10sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(18),
        )
        for lbl in (lbl_title, lbl_value, lbl_sub):
            lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        card.add_widget(lbl_title)
        card.add_widget(lbl_value)
        card.add_widget(lbl_sub)
        return card

    def filter_button(self, text_btn, key):
        active = self.current_filter == key
        if key == "vencidos":
            active_color = DANGER
        elif key == "hoy":
            active_color = GOLD
        elif key == "al_dia":
            active_color = SUCCESS
        else:
            active_color = BLUE
        button = Button(
            text=text_btn,
            background_normal="",
            background_color=active_color if active else (0.90, 0.92, 0.95, 1),
            color=WHITE if active else TEXT,
            bold=True,
            font_size="11sp",
        )
        button.bind(on_release=lambda _btn, selected=key: self.set_filter(selected))
        return button

    def status_meta(self, cliente, today):
        status = cliente.get("estado", "pendiente")
        due_date = cliente.get("proximo_cobro", "")
        is_overdue = status == "no_pago" or (due_date and due_date < today)
        is_today = due_date == today

        if is_overdue:
            return {
                "text": "VENCIDO",
                "accent": DANGER,
                "soft": (1.00, 0.94, 0.94, 1),
                "note": "Este cliente necesita seguimiento prioritario.",
            }
        if is_today:
            return {
                "text": "COBRAR HOY",
                "accent": GOLD,
                "soft": (1.00, 0.97, 0.88, 1),
                "note": "Está programado para cobro en la fecha actual.",
            }
        return {
            "text": "AL DÍA",
            "accent": SUCCESS,
            "soft": (0.92, 0.98, 0.94, 1),
            "note": "Va bien y todavía no está vencido.",
        }

    def debtor_card(self, cliente, today):
        meta = self.status_meta(cliente, today)
        name_text = str(cliente.get("nombre", "SIN NOMBRE"))
        phone_text = str(cliente.get("telefono", "")).strip() or "Sin teléfono"
        due_date = display_date_from_iso(cliente.get("proximo_cobro", ""))
        balance_text = money(cliente.get("saldo", 0))
        cuota_text = money(cliente.get("cuota", 0))
        pending_text = str(cliente.get("pendientes", 0) or 0)

        card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(316),
            padding=[dp(14), dp(14), dp(14), dp(14)],
            spacing=dp(10),
        )
        card.bg_color = WHITE

        # Encabezado: nombre y estado separados y legibles.
        top = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(54),
            spacing=dp(10),
            padding=[dp(10), dp(6), dp(10), dp(6)],
        )
        with top.canvas.before:
            Color(*BLUE)
            top.bg = RoundedRectangle(pos=top.pos, size=top.size, radius=[dp(12)])
        top.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
        top.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))

        name_box = BoxLayout(
            orientation="vertical",
            spacing=dp(2),
            size_hint_x=0.67,
        )
        name_lbl = Label(
            text=name_text,
            color=WHITE,
            bold=True,
            font_size="15sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(26),
        )
        phone_lbl = Label(
            text=phone_text,
            color=(0.90, 0.94, 1, 1),
            font_size="10.5sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(18),
        )
        for lbl in (name_lbl, phone_lbl):
            lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        name_box.add_widget(name_lbl)
        name_box.add_widget(phone_lbl)

        badge = Button(
            text=meta["text"],
            size_hint_x=0.33,
            size_hint_y=None,
            height=dp(38),
            background_normal="",
            background_color=meta["accent"],
            color=WHITE,
            bold=True,
            font_size="10.5sp",
            disabled=True,
        )
        top.add_widget(name_box)
        top.add_widget(badge)
        card.add_widget(top)

        line = Widget(size_hint_y=None, height=dp(2))
        with line.canvas.before:
            Color(*meta["accent"])
            line.rect = Rectangle(pos=line.pos, size=line.size)
        line.bind(
            pos=lambda inst, *_: setattr(inst.rect, "pos", inst.pos),
            size=lambda inst, *_: setattr(inst.rect, "size", inst.size),
        )
        card.add_widget(line)

        hint = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(42),
            padding=[dp(10), dp(7), dp(10), dp(7)],
        )
        hint.bg_color = meta["soft"]
        hint_lbl = Label(
            text=meta["note"],
            color=TEXT,
            font_size="10.5sp",
            halign="left",
            valign="middle",
        )
        hint_lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        hint.add_widget(hint_lbl)
        card.add_widget(hint)

        info_row1 = BoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(62),
        )
        info_row1.add_widget(
            self.metric_tile_inline(
                "Saldo pendiente",
                balance_text,
                meta["accent"],
                meta["soft"],
            )
        )
        info_row1.add_widget(
            self.metric_tile_inline(
                "Próximo cobro",
                due_date or "Sin fecha",
                BLUE,
                (0.94, 0.96, 1, 1),
            )
        )
        card.add_widget(info_row1)

        info_row2 = BoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(62),
        )
        info_row2.add_widget(
            self.metric_tile_inline(
                "Valor de la cuota",
                cuota_text,
                DARK,
                (0.95, 0.96, 0.98, 1),
            )
        )
        info_row2.add_widget(
            self.metric_tile_inline(
                "Cuotas pendientes",
                pending_text,
                GOLD,
                (1.00, 0.97, 0.88, 1),
            )
        )
        card.add_widget(info_row2)

        footer = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(10),
        )
        quick = Label(
            text="Consulta el préstamo, historial y próximos cobros.",
            color=MUTED,
            font_size="10sp",
            halign="left",
            valign="middle",
            size_hint_x=0.56,
        )
        quick.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        button = SmallButton("ABRIR CLIENTE", bg_color=BLUE)
        button.size_hint_x = 0.44
        button.height = dp(46)
        button.bind(on_release=lambda *_: self.open_client(cliente))
        footer.add_widget(quick)
        footer.add_widget(button)
        card.add_widget(footer)
        return card

    def metric_tile_inline(self, title, value, accent, bg_color):
        box = RoundedBox(
            orientation="vertical",
            size_hint_x=0.5,
            padding=[dp(10), dp(8), dp(10), dp(8)],
            spacing=dp(4),
        )
        box.bg_color = bg_color
        title_label = Label(
            text=title,
            color=MUTED,
            bold=True,
            font_size="10sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(18),
        )
        value_label = Label(
            text=str(value),
            color=accent,
            bold=True,
            font_size="13sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(24),
        )
        for lbl in (title_label, value_label):
            lbl.bind(
                size=lambda instance, value: setattr(
                    instance,
                    "text_size",
                    value,
                )
            )
        box.add_widget(title_label)
        box.add_widget(value_label)
        return box

    def set_filter(self, selected):
        self.current_filter = selected
        self.build()

    def open_client(self, cliente):
        self.app_ref.selected_client = cliente
        self.app_ref.go("gestion_cliente")


class ResumenScreen(Screen):
    sync_status = StringProperty("Pendiente")

    def __init__(self, **kwargs):
        super().__init__(name="resumen", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        refresh_daily_cache()
        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("::V12:: Caja / Resumen", show_back=True, on_back=lambda: self.app_ref.go("clientes")))

        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", padding=[dp(12), dp(12), dp(12), dp(22)], spacing=dp(12), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        metrics = daily_metrics()
        week_metrics = weekly_metrics()
        closure = get_cash_closure()
        journey_status = get_journey_status()

        weekly_opening_cash = (
            int(closure.get("caja_inicial", 0))
            if closure and journey_status in ("abierta", "cerrada")
            else week_metrics["opening_cash"]
        )
        weekly_closing_cash = (
            weekly_opening_cash
            + week_metrics["income"]
            + week_metrics["collected"]
            - week_metrics["expenses"]
        )
        weekly_managerial = weekly_managerial_metrics()

        total_clientes = len(CLIENTES)
        clientes_nuevos = len(metrics["new_clients"])
        pagos = len(metrics["payments"])
        no_pagos = len(metrics["no_payments"])
        aplazados = len(metrics["postponed"])
        recaudo_dia = metrics["collected"]
        ingresos = metrics["income"]
        egresos = metrics["expenses"]
        caja_inicial = weekly_opening_cash
        recaudo_esperado = metrics["expected"]
        saldo_caja = weekly_closing_cash
        recaudo_semana = week_metrics["collected"]
        pendientes_sync = count_pending_sync()
        productividad = productivity_metrics()
        backup_info = cloud_backup_status_info()
        money_alert = money_alert_info()

        money_card = RoundedBox(
            orientation="vertical",
            spacing=dp(7),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            size_hint_y=None,
        )
        money_card.bind(minimum_height=money_card.setter("height"))

        money_title = Label(
            text="ALERTA DE DINERO",
            color=money_alert["color"],
            bold=True,
            font_size="14sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(28),
        )
        money_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        money_card.add_widget(money_title)

        for left, right in [
            ("Hoy debías cobrar", money(money_alert["expected"])),
            ("Has cobrado", money(money_alert["collected"])),
            ("Faltan", money(money_alert["missing"])),
            ("Efectividad", f"{money_alert['effectiveness']}%"),
            ("Estado", money_alert["status"]),
        ]:
            money_card.add_widget(MetricRow(left, right))

        content.add_widget(money_card)

        backup_card = RoundedBox(
            orientation="vertical",
            spacing=dp(7),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            size_hint_y=None,
        )
        backup_card.bind(minimum_height=backup_card.setter("height"))

        backup_title = Label(
            text="COPIA DE SEGURIDAD EN NUBE",
            color=backup_info["color"],
            bold=True,
            font_size="14sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(28),
        )
        backup_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        backup_card.add_widget(backup_title)

        for left, right in [
            ("Última copia en nube", backup_info["last_backup"]),
            ("Estado", backup_info["status"]),
            ("Pendientes por subir", str(backup_info["pending"])),
            ("Detalle", backup_info["detail"]),
        ]:
            backup_card.add_widget(MetricRow(left, right))

        content.add_widget(backup_card)

        gerencial_card = RoundedBox(
            orientation="vertical",
            spacing=dp(7),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            size_hint_y=None,
        )
        gerencial_card.bind(minimum_height=gerencial_card.setter("height"))

        gerencial_title = Label(
            text="CIERRE SEMANAL GERENCIAL",
            color=BLUE,
            bold=True,
            font_size="14sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(28),
        )
        gerencial_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        gerencial_card.add_widget(gerencial_title)

        for left, right in [
            ("Semana actual", display_week_range()),
            ("Recaudo esperado", money(weekly_managerial["expected_week"])),
            ("Recaudo real", money(weekly_managerial["collected_week"])),
            ("Diferencia", money(weekly_managerial["difference"])),
            ("Cartera pendiente", money(weekly_managerial["outstanding_portfolio"])),
            ("No pagos acumulados", str(weekly_managerial["no_payments_count"])),
            ("Nuevos préstamos entregados", money(weekly_managerial["new_loans_delivered"])),
            ("Utilidad estimada", money(weekly_managerial["estimated_profit"])),
            ("Diagnóstico", weekly_managerial["diagnosis"]),
        ]:
            gerencial_card.add_widget(MetricRow(left, right))

        content.add_widget(gerencial_card)

        prod_card = RoundedBox(
            orientation="vertical",
            spacing=dp(7),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            size_hint_y=None,
        )
        prod_card.bind(minimum_height=prod_card.setter("height"))

        prod_title = Label(
            text="PRODUCTIVIDAD DE HOY",
            color=BLUE,
            bold=True,
            font_size="14sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(28),
        )
        prod_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        prod_card.add_widget(prod_title)

        for left, right in [
            ("Clientes visitados", str(productividad["visited"])),
            ("Pagaron", str(productividad["paid"])),
            ("No pagaron", str(productividad["no_paid"])),
            ("Reprogramados", str(productividad["rescheduled"])),
            ("Efectividad", f"{productividad['effectiveness']}%"),
            ("Recaudo real", money(productividad["collected"])),
            ("Recaudo estimado", money(productividad["expected"])),
            ("Diferencia", money(productividad["gap"])),
            ("Resultado", productividad["verdict"]),
        ]:
            prod_card.add_widget(MetricRow(left, right))

        content.add_widget(prod_card)

        report = RoundedBox(orientation="vertical", spacing=dp(7), padding=dp(10), size_hint_y=None)
        report.bind(minimum_height=report.setter("height"))

        for left, right in [
            ("Vendedor", "PACHO"),
            ("Fecha de Ruta", today_text()),
            ("Clientes Ausentes", str(no_pagos)),
            ("Aplazados Sig. Día", str(aplazados)),
            ("Número Clientes", str(total_clientes)),
            ("Clientes Nuevos", str(clientes_nuevos)),
            ("Pagos Registrados", f"{pagos} / {total_clientes}"),
            ("Caja inicial semana", money(caja_inicial)),
            ("Recaudo Esperado", money(recaudo_esperado)),
            ("Recaudo del día", money(recaudo_dia)),
            ("Recaudo de la semana", money(recaudo_semana)),
            ("Ingresos", money(ingresos)),
            ("Egresos", money(egresos)),
            ("Pendientes Nube", str(pendientes_sync)),
            (
                "Riesgo cartera",
                f"Alto {risk_distribution().get('alto', 0)} / Medio {risk_distribution().get('medio', 0)} / Bajo {risk_distribution().get('bajo', 0)}",
            ),
            (
                "Estado semana",
                {
                    "sin_abrir": "SIN ABRIR",
                    "abierta": "ABIERTA",
                    "cerrada": "CERRADA",
                }.get(journey_status, "SIN ABRIR"),
            ),
            ("Sincronización", cloud_backup_status_info()["status"]),
        ]:
            report.add_widget(MetricRow(left, right))

        cartera_total = sum(
            max(int(cliente.get("saldo", 0) or 0), 0)
            for cliente in CLIENTES
            if (
                int(cliente.get("saldo", 0) or 0) > 0
                and int(cliente.get("pendientes", 0) or 0) > 0
                and cliente.get("estado") != "paz_y_salvo"
            )
        )

        report.add_widget(MetricRow("Saldo semanal en caja", money(saldo_caja), highlight=True))
        report.add_widget(MetricRow("Cartera en la calle", money(cartera_total), highlight=True))
        content.add_widget(report)

        if is_admin_role():
            admin_cash = cash_summary_by_collector()
            admin_card = RoundedBox(
                orientation="vertical",
                spacing=dp(7),
                padding=[dp(12), dp(12), dp(12), dp(12)],
                size_hint_y=None,
            )
            admin_card.bind(minimum_height=admin_card.setter("height"))
            admin_title = Label(
                text="CONSOLIDADO DE CAJA POR COBRADOR",
                color=BLUE_DARK,
                bold=True,
                font_size="14sp",
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(28),
            )
            admin_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            admin_card.add_widget(admin_title)

            total_inicial = sum(safe_int(x.get("caja_inicial", 0)) for x in admin_cash)
            total_recaudo = sum(safe_int(x.get("recaudo", 0)) for x in admin_cash)
            total_ingresos = sum(safe_int(x.get("ingresos", 0)) for x in admin_cash)
            total_egresos = sum(safe_int(x.get("egresos", 0)) for x in admin_cash)
            total_saldo = sum(safe_int(x.get("saldo_esperado", 0)) for x in admin_cash)

            for left, right in [
                ("Caja inicial total", money(total_inicial)),
                ("Recaudo total", money(total_recaudo)),
                ("Ingresos total", money(total_ingresos)),
                ("Egresos total", money(total_egresos)),
                ("Saldo esperado total", money(total_saldo)),
            ]:
                admin_card.add_widget(MetricRow(left, right, highlight=(left == "Saldo esperado total")))

            for item in admin_cash:
                label = f"{item.get('nombre', 'Cobrador')} · {str(item.get('estado', 'sin_abrir')).upper()}"
                value = (
                    f"Base {money(item.get('caja_inicial', 0))} | "
                    f"Rec {money(item.get('recaudo', 0))} | "
                    f"Egr {money(item.get('egresos', 0))} | "
                    f"Saldo {money(item.get('saldo_esperado', 0))}"
                )
                admin_card.add_widget(MetricRow(label, value))

            content.add_widget(admin_card)

        actions = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(360),
            spacing=dp(10),
        )

        row1 = BoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(46),
        )

        paid_today_button = PillButton(
            "Pagaron Hoy",
            bg_color=SUCCESS,
        )
        paid_today_button.bind(
            on_release=lambda *_: self.app_ref.go(
                "clientes_pagaron_hoy"
            )
        )

        no_payments_button = PillButton("No Pagos")
        no_payments_button.bind(
            on_release=lambda *_: self.show_no_payments()
        )

        row1.add_widget(paid_today_button)
        row1.add_widget(no_payments_button)

        row2 = BoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(46),
        )

        settings_button = PillButton("Configuración")
        settings_button.bind(
            on_release=lambda *_: self.show_settings()
        )

        readjust_button = PillButton("Reajuste")
        readjust_button.bind(
            on_release=lambda *_: self.run_readjustment()
        )

        row2.add_widget(settings_button)
        row2.add_widget(readjust_button)

        row_cloud = BoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(46),
        )

        cloud = PillButton("Carga Completa", bg_color=BLUE)
        cloud.bind(
            on_release=lambda *_: self.simulate_cloud_upload()
        )
        history_week = PillButton("Cierres Semanales", bg_color=(0.36, 0.40, 0.48, 1))
        history_week.bind(
            on_release=lambda *_: self.app_ref.go("cierres_semanales")
        )
        row_cloud.add_widget(cloud)
        row_cloud.add_widget(history_week)

        row_pdf = BoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(46),
        )

        if is_admin_role():
            close_button = PillButton(
                "Admin: Consolidado",
                bg_color=(0.45, 0.48, 0.55, 1),
            )
            close_button.disabled = True

        elif journey_status == "sin_abrir":
            close_button = PillButton(
                "Abrir mi caja",
                bg_color=SUCCESS,
            )
            close_button.bind(
                on_release=lambda *_: self.confirm_open_day()
            )

        elif journey_status == "abierta":
            close_button = PillButton(
                "Cerrar mi caja",
                bg_color=GOLD,
            )
            close_button.bind(
                on_release=lambda *_: self.confirm_close_day()
            )

        else:
            close_button = PillButton(
                "Caja cerrada",
                bg_color=(0.45, 0.48, 0.55, 1),
            )
            close_button.disabled = True

        pdf_btn = PillButton(
            "Generar PDF",
            bg_color=SUCCESS,
        )
        pdf_btn.bind(
            on_release=lambda *_: self.generate_pdf()
        )

        row_pdf.add_widget(close_button)
        row_pdf.add_widget(pdf_btn)

        row_cartera = BoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(46),
        )
        cartera_button = PillButton(
            "Cartera en la Calle",
            bg_color=(0.22, 0.42, 0.72, 1),
        )
        cartera_button.bind(
            on_release=lambda *_: self.app_ref.go("cartera_calle")
        )
        auditoria_button = PillButton(
            "Auditoría",
            bg_color=(0.36, 0.40, 0.48, 1),
        )
        auditoria_button.bind(
            on_release=lambda *_: self.app_ref.go("auditoria")
        )
        riesgo_button = PillButton(
            "Riesgo",
            bg_color=DANGER,
        )
        riesgo_button.bind(
            on_release=lambda *_: self.app_ref.go("clientes_riesgo")
        )
        row_cartera.add_widget(cartera_button)
        row_cartera.add_widget(auditoria_button)
        row_cartera.add_widget(riesgo_button)

        row_ruta = BoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(46),
        )
        ruta_button = PillButton(
            "Ruta del Día",
            bg_color=BLUE_DARK,
        )
        ruta_button.bind(
            on_release=lambda *_: self.app_ref.go("ruta_dia")
        )
        row_ruta.add_widget(ruta_button)

        actions.add_widget(row1)
        actions.add_widget(row2)
        actions.add_widget(row_cartera)
        actions.add_widget(row_ruta)
        actions.add_widget(row_cloud)
        actions.add_widget(row_pdf)
        content.add_widget(actions)

        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def confirm_open_day(self):
        if is_admin_role() and not MODO_DUENO_UNICO:
            show_popup(
                "Consolidado administrativo",
                "El administrador no abre caja propia. Cada cobrador debe abrir su caja desde su usuario.",
                height=290,
            )
            return

        week_start, week_end = week_bounds()
        suggested_base = suggested_opening_base_for_collector(cash_owner_id())

        content = BoxLayout(
            orientation="vertical",
            padding=dp(14),
            spacing=dp(10),
        )

        info = Label(
            text=(
                f"Semana: {display_week_range()}\n"
                f"Base sugerida por sistema/admin: {money(suggested_base)}\n"
                "Confirma la base física con la que inicia el cobrador."
            ),
            color=WHITE,
            font_size="13sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(86),
        )
        info.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        base_label = FieldLabel("Caja inicial / base física recibida")
        base_input = MoneyTextInput(
            text=format_thousands(suggested_base),
            hint_text="Ej: 100.000",
        )

        motive_label = FieldLabel("Motivo si la base es diferente o no fue asignada")
        motive_input = AppTextInput(
            hint_text="Ej: el admin entregó una base distinta / base manual autorizada",
            multiline=True,
        )
        motive_input.height = dp(70)

        warning = Label(
            text=(
                "Regla: si la base digitada es diferente a la sugerida, o si no hay base sugerida, "
                "debes escribir un motivo. Quedará en auditoría."
            ),
            color=GOLD,
            bold=True,
            font_size="10.5sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(54),
        )
        warning.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        buttons = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(46),
            spacing=dp(8),
        )

        cancel = Button(
            text="Cancelar",
            background_normal="",
            background_color=(0.55, 0.58, 0.63, 1),
            color=WHITE,
            bold=True,
        )
        accept = Button(
            text="Abrir mi caja",
            background_normal="",
            background_color=SUCCESS,
            color=WHITE,
            bold=True,
        )

        buttons.add_widget(cancel)
        buttons.add_widget(accept)

        content.add_widget(info)
        content.add_widget(base_label)
        content.add_widget(base_input)
        content.add_widget(motive_label)
        content.add_widget(motive_input)
        content.add_widget(warning)
        content.add_widget(buttons)

        popup = Popup(
            title="Apertura de caja",
            content=content,
            size_hint=(0.92, None),
            height=dp(480),
            auto_dismiss=False,
        )

        cancel.bind(on_release=popup.dismiss)

        def validate_open(*_):
            base_value = to_int(base_input.text, 0)
            motive = str(motive_input.text or "").strip()

            if base_value <= 0:
                show_popup("Base inválida", "La base inicial debe ser mayor que cero.", height=240)
                return

            needs_motive = (suggested_base <= 0) or (base_value != suggested_base)

            if needs_motive and not motive:
                show_popup(
                    "Motivo obligatorio",
                    "La base digitada no coincide con la base sugerida, o no existe base asignada.\n\n"
                    "Escribe el motivo para abrir caja.",
                    height=330,
                )
                return

            self.open_day(
                popup,
                base_value,
                motive,
                suggested_base,
            )

        accept.bind(on_release=validate_open)
        popup.open()

    def open_day(self, popup=None, opening_cash=None, motive="", suggested_base=None):
        try:
            suggested_base = suggested_base if suggested_base is not None else suggested_opening_base_for_collector(cash_owner_id())
            opening_cash = safe_int(opening_cash)
            motive = str(motive or "").strip()

            if suggested_base <= 0 or opening_cash != suggested_base:
                insert_audit_log(
                    "Apertura con base diferente",
                    None,
                    cash_owner_label(),
                    f"Base sugerida: {money(suggested_base)}. Base digitada: {money(opening_cash)}. Motivo: {motive}"
                )

            journey = open_cash_journey(opening_cash=opening_cash, observation=motive)

            if popup is not None:
                popup.dismiss()

            show_popup(
                "Caja abierta",
                "La caja semanal del cobrador fue abierta correctamente.\n\n"
                f"Caja inicial: {money(journey['caja_inicial'])}",
                height=280,
            )

            self.build()

        except Exception as error:
            show_popup(
                "No se pudo abrir",
                str(error),
                height=260,
            )

    def confirm_close_day(self):
        if is_admin_role() and not MODO_DUENO_UNICO:
            show_popup(
                "Consolidado administrativo",
                "El administrador no cierra caja propia. Cada cobrador debe cerrar su caja desde su usuario.",
                height=290,
            )
            return

        status = get_journey_status()

        if status == "sin_abrir":
            show_popup(
                "Semana sin abrir",
                "Primero debes abrir la caja semanal.",
            )
            return

        if status == "cerrada":
            show_popup(
                "Semana cerrada",
                "El cierre de esta semana ya fue realizado.",
            )
            return

        closure = get_cash_closure()
        metrics = weekly_metrics()

        opening_cash = int(closure.get("caja_inicial", 0))
        expected_cash = (
            opening_cash
            + metrics["income"]
            + metrics["collected"]
            - metrics["expenses"]
        )

        pending_cloud = count_pending_sync()

        outer = BoxLayout(
            orientation="vertical",
            padding=[dp(10), dp(8), dp(10), dp(8)],
            spacing=dp(8),
        )

        # Encabezado fijo, compacto.
        header = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(82),
            padding=[dp(12), dp(8), dp(12), dp(8)],
            spacing=dp(3),
        )
        header.bg_color = (0.10, 0.18, 0.34, 1)

        title = Label(
            text="Cierre semanal de caja",
            color=WHITE,
            bold=True,
            font_size="17sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(28),
        )
        title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        subtitle = Label(
            text=f"{cash_owner_label()}  •  {display_week_range()}",
            color=(0.86, 0.92, 1, 1),
            font_size="11sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(22),
        )
        subtitle.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        status_line = Label(
            text="Cuenta el efectivo físico y confirma el resultado.",
            color=(0.76, 0.86, 1, 1),
            font_size="10.5sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(20),
        )
        status_line.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        header.add_widget(title)
        header.add_widget(subtitle)
        header.add_widget(status_line)
        outer.add_widget(header)

        scroll = ScrollView(
            do_scroll_x=False,
            bar_width=dp(4),
            scroll_type=["bars", "content"],
        )
        content = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            size_hint_y=None,
            padding=[dp(2), dp(2), dp(2), dp(18)],
        )
        content.bind(minimum_height=content.setter("height"))

        # Tarjeta principal: dinero esperado.
        expected_card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(110),
            padding=[dp(14), dp(10), dp(14), dp(10)],
            spacing=dp(4),
        )
        expected_card.bg_color = (0.96, 0.99, 1, 1)

        expected_label = Label(
            text="Saldo esperado en caja",
            color=MUTED,
            font_size="11sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(22),
        )
        expected_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        expected_value = Label(
            text=money(expected_cash),
            color=BLUE_DARK,
            bold=True,
            font_size="28sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(46),
        )
        expected_value.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        expected_help = Label(
            text="Caja inicial + recaudos + ingresos - egresos",
            color=MUTED,
            font_size="10sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(22),
        )
        expected_help.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        expected_card.add_widget(expected_label)
        expected_card.add_widget(expected_value)
        expected_card.add_widget(expected_help)
        content.add_widget(expected_card)

        # Resumen compacto.
        summary_box = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(178),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(4),
        )
        summary_box.bg_color = (0.98, 0.99, 1, 1)

        summary_title = Label(
            text="Resumen del periodo",
            color=DARK,
            bold=True,
            font_size="13sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(24),
        )
        summary_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        summary_box.add_widget(summary_title)

        summary_box.add_widget(DetailRow("Caja inicial", money(opening_cash)))
        summary_box.add_widget(DetailRow("Recaudo", money(metrics["collected"])))
        summary_box.add_widget(DetailRow("Ingresos", money(metrics["income"])))
        summary_box.add_widget(DetailRow("Egresos", money(metrics["expenses"])))
        summary_box.add_widget(DetailRow("Pendientes nube", str(pending_cloud)))
        content.add_widget(summary_box)

        # Campo de conteo.
        count_box = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(150),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(7),
        )
        count_box.bg_color = (1, 0.99, 0.94, 1)

        count_title = Label(
            text="Dinero físico contado",
            color=DARK,
            bold=True,
            font_size="14sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(25),
        )
        count_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        count_help = Label(
            text="Escribe el efectivo real que tienes en la mano.",
            color=MUTED,
            font_size="10.5sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(24),
        )
        count_help.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        physical_cash_input = MoneyTextInput(
            hint_text="Ej: 3.510.000",
            text=format_thousands(expected_cash),
        )
        physical_cash_input.font_size = "22sp"
        physical_cash_input.halign = "center"
        physical_cash_input.size_hint_y = None
        physical_cash_input.height = dp(54)

        count_box.add_widget(count_title)
        count_box.add_widget(count_help)
        count_box.add_widget(physical_cash_input)
        content.add_widget(count_box)

        # Resultado visual.
        result_box = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(160),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(6),
        )
        result_box.bg_color = (0.94, 0.98, 0.95, 1)

        result_title = Label(
            text="Resultado del arqueo",
            color=DARK,
            bold=True,
            font_size="13sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(24),
        )
        result_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        comparison_label = Label(
            text="CAJA CUADRADA",
            color=SUCCESS,
            bold=True,
            font_size="19sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(34),
        )
        comparison_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        difference_label = Label(
            text="Diferencia: $ 0",
            color=MUTED,
            bold=True,
            font_size="13sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(26),
        )
        difference_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        result_help = Label(
            text="El dinero físico coincide con el sistema.",
            color=SUCCESS,
            font_size="11sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(34),
        )
        result_help.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        result_box.add_widget(result_title)
        result_box.add_widget(comparison_label)
        result_box.add_widget(difference_label)
        result_box.add_widget(result_help)
        content.add_widget(result_box)

        # Observación opcional.
        obs_box = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(132),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(6),
        )
        obs_box.bg_color = (0.98, 0.98, 1, 1)

        obs_title = Label(
            text="Observación del cierre",
            color=DARK,
            bold=True,
            font_size="13sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(24),
        )
        obs_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        observation_input = AppTextInput(
            hint_text="Opcional. Ej: faltante justificado, sobrante, novedad del día...",
            multiline=True,
        )
        observation_input.size_hint_y = None
        observation_input.height = dp(78)

        obs_box.add_widget(obs_title)
        obs_box.add_widget(observation_input)
        content.add_widget(obs_box)

        scroll.add_widget(content)
        outer.add_widget(scroll)

        # Botones fijos inferiores. Siempre visibles.
        footer = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(104),
            spacing=dp(7),
        )

        footer_info = Label(
            text="Revisa el resultado antes de confirmar. Este cierre quedará guardado.",
            color=(0.86, 0.92, 1, 1),
            font_size="10.5sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(24),
        )
        footer_info.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        buttons = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(54),
            spacing=dp(9),
        )

        cancel_btn = Button(
            text="Cancelar",
            background_normal="",
            background_color=(0.55, 0.58, 0.63, 1),
            color=WHITE,
            bold=True,
        )
        close_btn = Button(
            text="Confirmar cierre",
            background_normal="",
            background_color=SUCCESS,
            color=WHITE,
            bold=True,
        )

        buttons.add_widget(cancel_btn)
        buttons.add_widget(close_btn)
        footer.add_widget(footer_info)
        footer.add_widget(buttons)
        outer.add_widget(footer)

        popup = Popup(
            title="",
            content=outer,
            size_hint=(0.96, 0.94),
            auto_dismiss=False,
        )

        def update_comparison(*_):
            counted = to_int(physical_cash_input.text, expected_cash)
            difference = counted - expected_cash

            if difference == 0:
                result_box.bg_color = (0.92, 0.98, 0.94, 1)
                comparison_label.text = "CAJA CUADRADA"
                comparison_label.color = SUCCESS
                difference_label.text = "Diferencia: $ 0"
                difference_label.color = MUTED
                result_help.text = "El dinero físico coincide con el sistema."
                result_help.color = SUCCESS
                close_btn.background_color = SUCCESS
            elif difference > 0:
                result_box.bg_color = (1, 0.97, 0.88, 1)
                comparison_label.text = "SOBRANTE EN CAJA"
                comparison_label.color = GOLD
                difference_label.text = f"Sobrante: {money(difference)}"
                difference_label.color = GOLD
                result_help.text = "Hay más dinero físico que el calculado por el sistema."
                result_help.color = GOLD
                close_btn.background_color = GOLD
            else:
                result_box.bg_color = (1, 0.94, 0.94, 1)
                comparison_label.text = "FALTANTE EN CAJA"
                comparison_label.color = DANGER
                difference_label.text = f"Faltante: {money(abs(difference))}"
                difference_label.color = DANGER
                result_help.text = "Hay menos dinero físico que el esperado."
                result_help.color = DANGER
                close_btn.background_color = DANGER

        def scroll_to_input(instance, focus):
            if focus:
                Clock.schedule_once(
                    lambda *_: scroll.scroll_to(count_box, padding=dp(90), animate=True),
                    0.25,
                )

        physical_cash_input.bind(text=update_comparison)
        physical_cash_input.bind(focus=scroll_to_input)

        cancel_btn.bind(on_release=popup.dismiss)
        close_btn.bind(
            on_release=lambda *_: self.close_day(
                to_int(physical_cash_input.text, expected_cash),
                observation_input.text,
                popup,
            )
        )

        update_comparison()
        popup.open()

    def close_day(self, physical_cash=None, observation=""):

        try:
            closure = save_cash_closure(
                physical_cash=physical_cash,
                observation=observation,
            )
            metrics = weekly_metrics()

            reconciliation_status = str(
                closure.get("estado_cuadre", "sin_arqueo")
            )
            difference = int(closure.get("diferencia_caja", 0))

            if reconciliation_status == "cuadrada":
                status_text = "CAJA CUADRADA"
                status_color = SUCCESS
            elif reconciliation_status == "sobrante":
                status_text = f"SOBRANTE: {money(difference)}"
                status_color = BLUE
            else:
                status_text = f"FALTANTE: {money(abs(difference))}"
                status_color = DANGER

            content = BoxLayout(
                orientation="vertical",
                padding=[dp(14), dp(12), dp(14), dp(12)],
                spacing=dp(10),
            )

            status_box = RoundedBox(
                orientation="vertical",
                size_hint_y=None,
                height=dp(94),
                padding=dp(12),
                spacing=dp(4),
            )
            status_box.bg_color = (0.93, 0.98, 0.93, 1) if difference == 0 else (1.0, 0.95, 0.92, 1)
            status_title = Label(
                text="Semana cerrada correctamente",
                color=SUCCESS,
                bold=True,
                font_size="16sp",
                halign="center",
                valign="middle",
                size_hint_y=None,
                height=dp(28),
            )
            status_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            reconciliation_label = Label(
                text=status_text,
                color=status_color,
                bold=True,
                font_size="15sp",
                halign="center",
                valign="middle",
            )
            reconciliation_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            status_box.add_widget(status_title)
            status_box.add_widget(reconciliation_label)
            content.add_widget(status_box)

            result_box = RoundedBox(
                orientation="vertical",
                size_hint_y=None,
                height=dp(236),
                padding=dp(12),
                spacing=dp(4),
            )
            result_box.add_widget(DetailRow("Periodo", display_week_range()))
            result_box.add_widget(DetailRow("Caja inicial", money(closure.get("caja_inicial", 0))))
            result_box.add_widget(DetailRow("Recaudo del día", money(metrics.get("collected", 0))))
            result_box.add_widget(DetailRow("Ingresos", money(metrics.get("income", 0))))
            result_box.add_widget(DetailRow("Egresos", money(metrics.get("expenses", 0))))
            result_box.add_widget(DetailRow("Saldo esperado", money(closure.get("saldo_final", 0))))
            result_box.add_widget(DetailRow("Efectivo contado", money(closure.get("efectivo_contado", 0))))
            result_box.add_widget(DetailRow("Diferencia", money(difference)))
            content.add_widget(result_box)

            close_btn = Button(
                text="Aceptar",
                background_normal="",
                background_color=BLUE,
                color=WHITE,
                bold=True,
                size_hint_y=None,
                height=dp(46),
            )
            content.add_widget(close_btn)

            popup = Popup(
                title="Cierre guardado",
                content=content,
                size_hint=(0.90, None),
                height=dp(440),
                auto_dismiss=False,
            )
            close_btn.bind(on_release=popup.dismiss)
            popup.open()
            self.build()

        except Exception as error:
            show_popup(
                "No se pudo cerrar",
                str(error),
                height=260,
            )

    def show_no_payments(self):
        refresh_memory_from_db()

        clients = [
            client
            for client in CLIENTES
            if client.get("estado") == "no_pago"
            or "no pag" in str(client.get("ultimo_tipo", "")).lower()
        ]

        if not clients:
            show_popup(
                "Clientes sin pago",
                "No hay clientes marcados como NO PAGO.",
            )
            return

        lines = []
        for client in clients[:12]:
            lines.append(
                f"{client.get('nombre', 'SIN NOMBRE')} - "
                f"{money(client.get('saldo', 0))}"
            )

        if len(clients) > 12:
            lines.append(
                f"... y {len(clients) - 12} cliente(s) más."
            )

        show_popup(
            f"Clientes sin pago ({len(clients)})",
            "\n".join(lines),
            height=min(520, 220 + len(lines) * 24),
        )

    def show_settings(self):
        cloud_state = (
            "Configurado"
            if supabase_configured()
            else "No configurado"
        )

        message = (
            f"Cobrador ID:\n{COBRADOR_ID}\n\n"
            f"Supabase: {cloud_state}\n"
            f"Sincronización automática: cada "
            f"{SYNC_INTERVAL_SECONDS} segundos\n"
            f"Tiempo máximo de conexión: "
            f"{SYNC_TIMEOUT_SECONDS} segundos"
        )

        show_popup(
            "Configuración actual",
            message,
            height=360,
        )

    def run_readjustment(self):
        """
        Recalcula estados vencidos y refresca la información.

        No modifica cuotas pagadas, saldo ni historial.
        """
        try:
            update_due_statuses()

            sync_message = "Reajuste local completado."

            if supabase_configured():
                ok, message = sync_all_to_cloud(silent=True)
                if ok:
                    sync_message = (
                        "Reajuste y sincronización completados."
                    )
                    self.sync_status = "Sincronizado correctamente"
                else:
                    sync_message = (
                        "Reajuste local completado, pero la nube "
                        f"quedó pendiente.\n{message}"
                    )
                    self.sync_status = "Pendiente"

            refresh_memory_from_db()
            self.build()

            show_popup(
                "Reajuste completado",
                sync_message,
                height=280,
            )

        except Exception as error:
            show_popup(
                "Error de reajuste",
                f"No se pudo completar el reajuste.\n{error}",
                height=280,
            )

    def confirm_clear(self):
        confirm_popup("Limpiar datos", "Esto borrará clientes, pagos y movimientos.\nLa app quedará vacía para uso personal.", self.clear_all)

    def clear_all(self):
        clear_all_data_db()
        self.sync_status = "Pendiente"
        self.build()
        show_popup("Datos limpiados", "La base local fue limpiada correctamente.")

    def generate_pdf(self):
        try:
            private_pdf_path = generate_daily_pdf_report()

            final_path, open_ok, open_message = (
                publish_pdf_to_downloads(
                    private_pdf_path,
                    open_after=True,
                )
            )

            if open_ok:
                # El visor ya fue abierto. No se coloca un popup encima
                # porque podría ocultar la aplicación que muestra el PDF.
                print(
                    "PDF generado y abierto:",
                    final_path,
                )
            else:
                show_popup(
                    "PDF generado",
                    "El reporte fue guardado correctamente, "
                    "pero no se pudo abrir automáticamente.\n\n"
                    f"Ubicación:\n{final_path}\n\n"
                    f"Detalle:\n{open_message}",
                    height=360,
                )

        except Exception as error:
            show_popup(
                "Error PDF",
                f"No se pudo generar el PDF.\n{error}",
                height=280,
            )

    def simulate_cloud_upload(self):
        """
        Inicia una sincronización manual sin bloquear la app.
        Si no hay internet, los datos quedan guardados localmente.
        """
        app = App.get_running_app()

        if not supabase_configured():
            self.sync_status = "Supabase no configurado"
            self.build()
            show_popup(
                "Supabase no configurado",
                "La app seguirá funcionando offline, pero falta configurar la nube.",
            )
            return

        self.sync_status = "Sincronizando en segundo plano..."
        self.build()

        app.request_auto_sync(force_pull=True)

        show_popup(
            "Sincronización iniciada",
            "La app seguirá funcionando mientras intenta sincronizar.\n"
            "Si no hay internet, volverá a intentarlo automáticamente.",
            height=280,
        )



class AuditoriaScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="auditoria", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(
            Header(
                "Historial de Cambios",
                show_back=True,
                on_back=lambda: self.app_ref.go("resumen"),
            )
        )

        scroll = ScrollView(do_scroll_x=False)
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(14), dp(12), dp(80)],
            spacing=dp(10),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        logs = load_audit_logs(120)

        if not logs:
            empty = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(110), padding=dp(14))
            lbl = Label(
                text="Todavía no hay acciones sensibles registradas.",
                color=MUTED,
                halign="center",
                valign="middle",
            )
            lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            empty.add_widget(lbl)
            content.add_widget(empty)
        else:
            for log in logs:
                card = RoundedBox(
                    orientation="vertical",
                    size_hint_y=None,
                    height=dp(190),
                    padding=[dp(14), dp(12), dp(14), dp(12)],
                    spacing=dp(6),
                )
                card.bg_color = (0.98, 0.99, 1, 1)

                title = Label(
                    text=str(log.get("accion", "")).upper(),
                    color=BLUE,
                    bold=True,
                    font_size="13sp",
                    halign="left",
                    valign="middle",
                    size_hint_y=None,
                    height=dp(24),
                )
                title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
                card.add_widget(title)

                card.add_widget(DetailRow("Fecha", log.get("fecha", "")))
                card.add_widget(DetailRow("Cliente", log.get("cliente", "") or "No aplica"))
                card.add_widget(DetailRow("Motivo", log.get("motivo", "")))
                card.add_widget(DetailRow("Detalle", log.get("detalle", "") or "Sin detalle"))
                card.add_widget(DetailRow("Cobrador", log.get("cobrador", "") or cobrador_nombre()))
                content.add_widget(card)

        scroll.add_widget(content)
        self.root.add_widget(scroll)





def route_today_clients(date_iso=None):
    """
    Clientes que deben trabajarse hoy o están vencidos.
    Orden profesional para reducir vueltas:
    zona -> barrio -> ruta -> orden de visita -> prioridad.
    """
    date_iso = date_iso or iso_today()
    clients = []

    for cliente in CLIENTES:
        if safe_int(cliente.get("saldo", 0)) <= 0:
            continue
        if safe_int(cliente.get("pendientes", 0)) <= 0:
            continue
        if str(cliente.get("estado", "") or "") == "paz_y_salvo":
            continue

        status = cobranza_estado_profesional(cliente, date_iso)
        proximo = str(cliente.get("proximo_cobro", "") or "")[:10]

        if not proximo or proximo <= date_iso:
            clients.append((cliente, status))

    clients.sort(
        key=lambda item: (
            str(item[0].get("zona", "") or "Sin zona").upper(),
            str(item[0].get("barrio", "") or "Sin barrio").upper(),
            str(item[0].get("ruta", "") or "Sin ruta").upper(),
            safe_int(item[0].get("orden_visita", 0)),
            cobranza_sort_key(item[0], item[1], date_iso),
        )
    )
    return clients


def route_group_summary(date_iso=None):
    pairs = route_today_clients(date_iso)
    grouped = {}
    for cliente, status in pairs:
        zona = str(cliente.get("zona", "") or "Sin zona").strip() or "Sin zona"
        barrio = str(cliente.get("barrio", "") or "Sin barrio").strip() or "Sin barrio"
        grouped.setdefault(zona, {})
        grouped[zona].setdefault(barrio, [])
        grouped[zona][barrio].append((cliente, status))

    total_expected = sum(safe_int(cliente.get("cuota", 0)) for cliente, _ in pairs)
    total_balance = sum(safe_int(cliente.get("saldo", 0)) for cliente, _ in pairs)
    barrios = sum(len(barrios) for barrios in grouped.values())

    return {
        "pairs": pairs,
        "grouped": grouped,
        "total_clients": len(pairs),
        "total_expected": total_expected,
        "total_balance": total_balance,
        "barrios": barrios,
    }


def open_address_in_maps(cliente):
    """
    Abre Google Maps con la dirección del cliente.
    No mete un mapa dentro de la app para mantener el APK estable.
    """
    direccion = str(cliente.get("direccion", "") or "").strip()
    barrio = str(cliente.get("barrio", "") or "").strip()
    zona = str(cliente.get("zona", "") or "").strip()

    query_parts = [part for part in [direccion, barrio, zona] if part]
    query = ", ".join(query_parts)

    if not query:
        return False, "Este cliente no tiene dirección, barrio o zona registrada."

    maps_url = "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(query)

    try:
        if platform == "android":
            from importlib import import_module

            autoclass = import_module("jnius").autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")

            activity = PythonActivity.mActivity
            intent = Intent(Intent.ACTION_VIEW, Uri.parse(maps_url))
            intent.setPackage("com.google.android.apps.maps")
            activity.startActivity(intent)
            return True, "Google Maps abierto."

        import webbrowser
        webbrowser.open(maps_url)
        return True, "Mapa abierto."

    except Exception as error:
        try:
            import webbrowser
            webbrowser.open(maps_url)
            return True, "Mapa abierto en navegador."
        except Exception:
            return False, str(error)




class RutaDiaScreen(Screen):
    """
    Ruta del día por zona y barrio.
    Diseño corregido para que ninguna tarjeta monte textos.
    """
    def __init__(self, **kwargs):
        super().__init__(name="ruta_dia", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        refresh_clients_cache()
        self.build()

    def make_info_label(self, text, color=TEXT, bold=False, size="11sp", height=dp(24), halign="left", valign="middle"):
        lbl = Label(
            text=str(text),
            color=color,
            bold=bold,
            font_size=size,
            halign=halign,
            valign=valign,
            size_hint_y=None,
            height=height,
        )
        lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        return lbl

    def metric_chip(self, title, value, color=TEXT):
        chip = RoundedBox(
            orientation="vertical",
            padding=[dp(8), dp(6), dp(8), dp(6)],
            spacing=dp(1),
        )
        chip.bg_color = WHITE
        chip.add_widget(self.make_info_label(title, MUTED, True, "8.8sp", dp(18), halign="center"))
        chip.add_widget(self.make_info_label(value, color, True, "12.5sp", dp(24), halign="center"))
        return chip

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(
            Header(
                "Ruta del Día",
                show_back=True,
                on_back=lambda: self.app_ref.go("inicio"),
            )
        )

        data = route_group_summary()
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(16), dp(12), dp(92)],
            spacing=dp(14),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        # ====================================================
        # RESUMEN SUPERIOR
        # ====================================================
        summary = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(230),
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(10),
        )
        summary.bg_color = (0.92, 0.97, 1, 1)

        summary.add_widget(
            self.make_info_label(
                "RUTA RECOMENDADA DE COBRO",
                color=BLUE,
                bold=True,
                size="14sp",
                height=dp(28),
            )
        )

        row_1 = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(62), spacing=dp(8))
        row_1.add_widget(self.metric_chip("Clientes", str(data["total_clients"]), BLUE))
        row_1.add_widget(self.metric_chip("Barrios", str(data["barrios"]), DARK))
        row_1.add_widget(self.metric_chip("Esperado", money(data["total_expected"]), SUCCESS))
        summary.add_widget(row_1)

        row_2 = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(62), spacing=dp(8))
        row_2.add_widget(self.metric_chip("Cartera", money(data["total_balance"]), DANGER))
        row_2.add_widget(self.metric_chip("Orden", "Zona → Barrio", BLUE_DARK))
        row_2.add_widget(self.metric_chip("Modo", "Ahorro ruta", GOLD))
        summary.add_widget(row_2)

        help_text = self.make_info_label(
            "Termina un barrio completo antes de pasar al siguiente. Así evitas devolverte y gastar más gasolina.",
            color=MUTED,
            size="10.3sp",
            height=dp(42),
            valign="top",
        )
        summary.add_widget(help_text)
        content.add_widget(summary)

        if data["total_clients"] <= 0:
            empty = RoundedBox(
                orientation="vertical",
                size_hint_y=None,
                height=dp(130),
                padding=dp(14),
            )
            empty.bg_color = (0.90, 0.98, 0.92, 1)
            empty.add_widget(
                self.make_info_label(
                    "No hay clientes vencidos ni programados para hoy.",
                    color=SUCCESS,
                    bold=True,
                    size="13sp",
                    height=dp(80),
                    halign="center",
                )
            )
            content.add_widget(empty)
        else:
            for zona, barrios in data["grouped"].items():
                zona_total = sum(len(items) for items in barrios.values())
                zona_expected = sum(
                    safe_int(cliente.get("cuota", 0))
                    for items in barrios.values()
                    for cliente, _status in items
                )

                zona_card = RoundedBox(
                    orientation="vertical",
                    size_hint_y=None,
                    height=dp(104),
                    padding=[dp(14), dp(12), dp(14), dp(12)],
                    spacing=dp(8),
                )
                zona_card.bg_color = BLUE_DARK
                zona_card.add_widget(
                    self.make_info_label(
                        f"ZONA: {str(zona).upper()}",
                        color=WHITE,
                        bold=True,
                        size="14sp",
                        height=dp(30),
                    )
                )
                zona_card.add_widget(
                    self.make_info_label(
                        f"{zona_total} cliente(s) por visitar",
                        color=(0.88, 0.92, 1, 1),
                        bold=True,
                        size="11sp",
                        height=dp(22),
                    )
                )
                zona_card.add_widget(
                    self.make_info_label(
                        f"Recaudo estimado de la zona: {money(zona_expected)}",
                        color=GOLD,
                        bold=True,
                        size="11sp",
                        height=dp(22),
                    )
                )
                content.add_widget(zona_card)

                for barrio, items in barrios.items():
                    barrio_expected = sum(safe_int(cliente.get("cuota", 0)) for cliente, _ in items)

                    barrio_card = RoundedBox(
                        orientation="vertical",
                        size_hint_y=None,
                        height=dp(128),
                        padding=[dp(14), dp(12), dp(14), dp(12)],
                        spacing=dp(8),
                    )
                    barrio_card.bg_color = (1.0, 0.98, 0.91, 1)
                    barrio_card.add_widget(
                        self.make_info_label(
                            f"BARRIO: {barrio}",
                            color=DARK,
                            bold=True,
                            size="13sp",
                            height=dp(28),
                        )
                    )

                    barrio_metrics = BoxLayout(
                        orientation="horizontal",
                        size_hint_y=None,
                        height=dp(62),
                        spacing=dp(8),
                    )
                    barrio_metrics.add_widget(self.metric_chip("Clientes", str(len(items)), BLUE))
                    barrio_metrics.add_widget(self.metric_chip("Esperado", money(barrio_expected), SUCCESS))
                    barrio_metrics.add_widget(self.metric_chip("Siguiente", "Completar barrio", GOLD))
                    barrio_card.add_widget(barrio_metrics)
                    content.add_widget(barrio_card)

                    for index, (cliente, status) in enumerate(items, start=1):
                        content.add_widget(self.client_route_card(cliente, status, index))

        scroll.add_widget(content)
        self.root.add_widget(scroll)

        bottom = BoxLayout(size_hint_y=None, height=dp(66))
        bottom.add_widget(BottomNav(self.app_ref, active="inicio"))
        self.root.add_widget(bottom)

    def client_route_card(self, cliente, status, index):
        light = client_traffic_light(cliente, status)
        border_color = status.get("border", light.get("color", BLUE))
        bg_status = status.get("bg", (0.98, 0.99, 1, 1))

        card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(330),
            padding=[dp(0), dp(0), dp(12), dp(0)],
            spacing=dp(0),
        )
        card.bg_color = bg_status

        main = BoxLayout(orientation="horizontal", spacing=dp(0))

        side = BoxLayout(size_hint_x=None, width=dp(8))
        with side.canvas.before:
            Color(*border_color)
            side.rect = RoundedRectangle(pos=side.pos, size=side.size, radius=[dp(14), 0, 0, dp(14)])
        side.bind(pos=lambda w, *_: setattr(w.rect, "pos", w.pos))
        side.bind(size=lambda w, *_: setattr(w.rect, "size", w.size))
        main.add_widget(side)

        body = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(12), dp(0), dp(12)],
            spacing=dp(8),
        )

        top = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42), spacing=dp(8))
        order_lbl = Label(
            text=str(cliente.get("orden_visita", "") or index),
            color=WHITE,
            bold=True,
            font_size="14sp",
            halign="center",
            valign="middle",
            size_hint_x=None,
            width=dp(36),
        )
        with order_lbl.canvas.before:
            Color(*border_color)
            order_lbl.bg = RoundedRectangle(pos=order_lbl.pos, size=order_lbl.size, radius=[dp(18)])
        order_lbl.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
        order_lbl.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))

        name = Label(
            text=cliente.get("nombre", "SIN NOMBRE"),
            color=TEXT,
            bold=True,
            font_size="13sp",
            halign="left",
            valign="middle",
        )
        badge = Label(
            text=status.get("label", "PENDIENTE"),
            color=status.get("badge_color", WHITE),
            bold=True,
            font_size="8.2sp",
            halign="center",
            valign="middle",
            size_hint_x=None,
            width=dp(112),
        )
        with badge.canvas.before:
            Color(*status.get("badge_bg", border_color))
            badge.bg = RoundedRectangle(pos=badge.pos, size=badge.size, radius=[dp(12)])
        badge.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
        badge.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))

        for lbl in (name, badge):
            lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        top.add_widget(order_lbl)
        top.add_widget(name)
        top.add_widget(badge)
        body.add_widget(top)

        row_money = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(32), spacing=dp(8))
        cuota = self.make_info_label(f"Cuota: {money(cliente.get('cuota', 0))}", color=TEXT, bold=True, height=dp(32))
        saldo = self.make_info_label(f"Saldo: {money(cliente.get('saldo', 0))}", color=TEXT, bold=True, height=dp(32), halign="right")
        row_money.add_widget(cuota)
        row_money.add_widget(saldo)
        body.add_widget(row_money)

        route_text = (
            f"Ruta: {cliente.get('ruta', '') or 'Sin ruta'} · "
            f"Barrio: {cliente.get('barrio', '') or 'Sin barrio'}"
        )
        body.add_widget(
            self.make_info_label(
                route_text,
                color=MUTED,
                size="10.2sp",
                height=dp(32),
                valign="top",
            )
        )

        address = cliente.get("direccion", "") or "Sin dirección registrada"
        body.add_widget(
            self.make_info_label(
                f"Dirección: {address}",
                color=TEXT,
                size="10.2sp",
                height=dp(48),
                valign="top",
            )
        )

        body.add_widget(
            self.make_info_label(
                f"{light['label']} · {status.get('detalle', '')}",
                color=light["color"],
                bold=True,
                size="9.8sp",
                height=dp(46),
                valign="top",
            )
        )

        actions = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
        )
        cobrar = SmallButton("Cobrar", bg_color=SUCCESS)
        maps = SmallButton("Abrir Maps", bg_color=BLUE)
        cobrar.bind(on_release=lambda *_: self.open_cobro(cliente))
        maps.bind(on_release=lambda *_: self.open_maps(cliente))
        actions.add_widget(cobrar)
        actions.add_widget(maps)
        body.add_widget(actions)

        main.add_widget(body)
        card.add_widget(main)
        return card

    def open_cobro(self, cliente):
        self.app_ref.selected_client = cliente
        self.app_ref.go("cuota")

    def open_maps(self, cliente):
        ok, msg = open_address_in_maps(cliente)
        if not ok:
            show_popup("No se pudo abrir Maps", msg, height=260)




class ClientesRiesgoScreen(Screen):
    """Control gerencial de clientes en riesgo con tarjetas amplias."""
    def __init__(self, **kwargs):
        super().__init__(name="clientes_riesgo", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        refresh_clients_cache()
        self.build()

    def make_label(self, text, color=TEXT, bold=False, size="11sp", height=dp(24), halign="left", valign="middle"):
        lbl = Label(
            text=str(text),
            color=color,
            bold=bold,
            font_size=size,
            halign=halign,
            valign=valign,
            size_hint_y=None,
            height=height,
        )
        lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        return lbl

    def risk_chip(self, title, value, color):
        box = RoundedBox(
            orientation="vertical",
            padding=[dp(8), dp(6), dp(8), dp(6)],
            spacing=dp(2),
        )
        box.bg_color = WHITE
        box.add_widget(self.make_label(title, MUTED, True, "8.8sp", dp(18), halign="center"))
        box.add_widget(self.make_label(str(value), color, True, "14sp", dp(26), halign="center"))
        return box

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(
            Header(
                "Clientes en Riesgo",
                show_back=True,
                on_back=lambda: self.app_ref.go("inicio"),
            )
        )

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4), scroll_type=["bars", "content"])
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(16), dp(12), dp(92)],
            spacing=dp(14),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        risky = risky_clients_control()
        dist = traffic_light_distribution()

        # ====================================================
        # RESUMEN SUPERIOR
        # ====================================================
        summary = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(230),
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(10),
        )
        summary.bg_color = (1.0, 0.95, 0.86, 1) if risky else (0.90, 0.98, 0.92, 1)

        summary.add_widget(
            self.make_label(
                "CONTROL DE CARTERA EN RIESGO",
                color=DANGER if risky else SUCCESS,
                bold=True,
                size="14sp",
                height=dp(30),
            )
        )

        row_1 = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(64), spacing=dp(8))
        row_1.add_widget(self.risk_chip("Críticos", len(risky), DANGER if risky else SUCCESS))
        row_1.add_widget(self.risk_chip("Verde", dist.get("verde", 0), SUCCESS))
        row_1.add_widget(self.risk_chip("Amarillo", dist.get("amarillo", 0), GOLD))
        summary.add_widget(row_1)

        row_2 = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(64), spacing=dp(8))
        row_2.add_widget(self.risk_chip("Rojo", dist.get("rojo", 0), DANGER))
        row_2.add_widget(self.risk_chip("No renovar", dist.get("no_renovar", 0), DARK))
        row_2.add_widget(self.risk_chip("Acción", "Revisar", BLUE))
        summary.add_widget(row_2)

        summary.add_widget(
            self.make_label(
                "Prioriza estos clientes antes de renovar o entregar más dinero.",
                color=MUTED,
                size="10.5sp",
                height=dp(34),
                valign="top",
            )
        )
        content.add_widget(summary)

        if not risky:
            empty = RoundedBox(
                orientation="vertical",
                size_hint_y=None,
                height=dp(130),
                padding=dp(14),
            )
            empty.bg_color = (0.90, 0.98, 0.92, 1)
            lbl = self.make_label(
                "No hay clientes en riesgo crítico en este momento.",
                color=SUCCESS,
                bold=True,
                size="13sp",
                height=dp(80),
                halign="center",
            )
            empty.add_widget(lbl)
            content.add_widget(empty)
        else:
            for item in risky:
                cliente = item["cliente"]
                status = item["status"]
                light = item["light"]
                reasons = " · ".join(item["reasons"])

                card = RoundedBox(
                    orientation="vertical",
                    size_hint_y=None,
                    height=dp(352),
                    padding=[dp(0), dp(0), dp(12), dp(0)],
                    spacing=dp(0),
                )
                card.bg_color = (1.0, 0.94, 0.94, 1) if light["grupo"] in ("rojo", "no_renovar") else (1.0, 0.98, 0.91, 1)

                main = BoxLayout(orientation="horizontal", spacing=dp(0))

                side = BoxLayout(size_hint_x=None, width=dp(8))
                with side.canvas.before:
                    Color(*light["color"])
                    side.rect = RoundedRectangle(pos=side.pos, size=side.size, radius=[dp(14), 0, 0, dp(14)])
                side.bind(pos=lambda w, *_: setattr(w.rect, "pos", w.pos))
                side.bind(size=lambda w, *_: setattr(w.rect, "size", w.size))
                main.add_widget(side)

                body = BoxLayout(
                    orientation="vertical",
                    padding=[dp(14), dp(12), dp(0), dp(12)],
                    spacing=dp(8),
                )

                top = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42), spacing=dp(8))
                name = Label(
                    text=cliente.get("nombre", "SIN NOMBRE"),
                    color=TEXT,
                    bold=True,
                    font_size="14sp",
                    halign="left",
                    valign="middle",
                )
                badge = Label(
                    text=light["label"],
                    color=light["color"],
                    bold=True,
                    font_size="9.2sp",
                    halign="right",
                    valign="middle",
                    size_hint_x=0.48,
                )
                for lbl in (name, badge):
                    lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
                top.add_widget(name)
                top.add_widget(badge)
                body.add_widget(top)

                motive_box = RoundedBox(
                    orientation="vertical",
                    size_hint_y=None,
                    height=dp(78),
                    padding=[dp(10), dp(8), dp(10), dp(8)],
                    spacing=dp(3),
                )
                motive_box.bg_color = WHITE
                motive_box.add_widget(self.make_label("Motivo principal", MUTED, True, "9sp", dp(18)))
                motive_box.add_widget(
                    self.make_label(
                        reasons,
                        DANGER if light["grupo"] in ("rojo", "no_renovar") else TEXT,
                        True,
                        "10sp",
                        dp(42),
                        valign="top",
                    )
                )
                body.add_widget(motive_box)

                metrics_1 = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(64), spacing=dp(8))
                metrics_1.add_widget(self.risk_chip("Saldo", money(cliente.get("saldo", 0)), DANGER))
                metrics_1.add_widget(self.risk_chip("No pagos", client_no_payment_count(cliente), GOLD))
                metrics_1.add_widget(self.risk_chip("Días venc.", status.get("dias_atraso", 0), DANGER))
                body.add_widget(metrics_1)

                route_box = RoundedBox(
                    orientation="vertical",
                    size_hint_y=None,
                    height=dp(62),
                    padding=[dp(10), dp(7), dp(10), dp(7)],
                    spacing=dp(2),
                )
                route_box.bg_color = WHITE
                route_box.add_widget(self.make_label("Ruta / ubicación", MUTED, True, "9sp", dp(18)))
                route_box.add_widget(
                    self.make_label(
                        f"Ruta: {cliente.get('ruta', '') or 'Sin ruta'} · Barrio: {cliente.get('barrio', '') or 'Sin barrio'}",
                        TEXT,
                        False,
                        "10sp",
                        dp(28),
                        valign="top",
                    )
                )
                body.add_widget(route_box)

                actions = BoxLayout(
                    orientation="horizontal",
                    size_hint_y=None,
                    height=dp(48),
                    spacing=dp(8),
                )
                btn = SmallButton("ABRIR CLIENTE", bg_color=BLUE)
                btn.bind(on_release=lambda *_btn, c=cliente: self.open_client(c))
                maps = SmallButton("MAPS", bg_color=BLUE_DARK)
                maps.bind(on_release=lambda *_btn, c=cliente: self.open_maps(c))
                actions.add_widget(btn)
                actions.add_widget(maps)
                body.add_widget(actions)

                main.add_widget(body)
                card.add_widget(main)
                content.add_widget(card)

        scroll.add_widget(content)
        self.root.add_widget(scroll)

        bottom = BoxLayout(size_hint_y=None, height=dp(66))
        bottom.add_widget(BottomNav(self.app_ref, active="inicio"))
        self.root.add_widget(bottom)

    def open_client(self, cliente):
        self.app_ref.selected_client = cliente
        self.app_ref.go("gestion_cliente")

    def open_maps(self, cliente):
        ok, msg = open_address_in_maps(cliente)
        if not ok:
            show_popup("No se pudo abrir Maps", msg, height=260)




# ============================================================
# APP PRINCIPAL
# ============================================================

class CobrosV12App(App):
    selected_client = None
    cloud_restore_done = False
    authenticated = False
    current_role = "Administrador"
    current_user = None
    current_username = ""
    current_user_name = ""
    current_cobrador_id = ""

    # Estado offline-first
    sync_in_progress = False
    last_sync_ok = False
    last_sync_message = "Pendiente"
    last_sync_request_at = 0.0
    minimum_sync_gap_seconds = 4.0
    last_route_notification_key = ""
    route_check_interval_seconds = 900

    def build(self):
        self.title = "Cobros V12 Pacho Admin"
        try:
            init_database()
            refresh_memory_from_db(normalize=True)
        except Exception as error:
            print("ERROR SQLITE:", error)

        self.shell = AnchorLayout(anchor_x="center", anchor_y="top")

        if platform in ("android", "ios"):
            size_hint = (1, 1)
            width = Window.width
        else:
            size_hint = (None, 1)
            width = min(Window.width, dp(430))

        self.sm = ScreenManager(transition=NoTransition(), size_hint=size_hint, width=width)

        self.sm.add_widget(LoginPinScreen())
        self.sm.add_widget(InicioDashboardScreen())
        self.sm.add_widget(ClientesScreen())
        self.sm.add_widget(TodosClientesScreen())
        self.sm.add_widget(GestionClienteScreen())
        self.sm.add_widget(HistorialClienteScreen())
        self.sm.add_widget(CuotaScreen())
        self.sm.add_widget(NuevoClienteScreen())
        self.sm.add_widget(RenovarPrestamoScreen())
        self.sm.add_widget(EditarClienteScreen())
        self.sm.add_widget(MovimientosScreen())
        self.sm.add_widget(ClientesPagaronHoyScreen())
        self.sm.add_widget(CierresSemanalesScreen())
        self.sm.add_widget(CarteraCalleScreen())
        self.sm.add_widget(ResumenScreen())
        self.sm.add_widget(CajaCentralScreen())
        self.sm.add_widget(AuditoriaScreen())
        self.sm.add_widget(ClientesRiesgoScreen())
        self.sm.add_widget(RutaDiaScreen())
        self.sm.add_widget(ConfiguracionScreen())
        self.sm.add_widget(AsignacionCobradoresScreen())
        self.sm.add_widget(UsuariosScreen())

        self.shell.add_widget(self.sm)
        self.sm.current = "login"
        Window.bind(size=self.update_mobile_width)

        return self.shell

    def update_mobile_width(self, *_):
        if hasattr(self, "sm") and platform not in ("android", "ios"):
            self.sm.width = min(Window.width, dp(430))

    def restore_from_cloud_once(self):
        """
        Intenta restaurar desde Supabase sin bloquear el inicio.

        Si no hay internet, NO marca la restauración como completada.
        Así volverá a intentarlo automáticamente cuando regrese la conexión.
        """
        if self.cloud_restore_done or self.sync_in_progress:
            return

        if not supabase_configured():
            print("RESTORE FROM CLOUD: Supabase no configurado")
            return

        self.request_auto_sync(force_pull=True)



    def on_start(self):
        configure_mobile_keyboard()

        # Android 13+ solicita autorización para mostrar notificaciones.
        # Se programa después del inicio para evitar bloquear la apertura.
        Clock.schedule_once(
            lambda *_: request_android_notification_permission(),
            1.5,
        )

        print("Cobros V12 iniciado correctamente.")
        print("Modo: OFFLINE-FIRST")
        print("Base de datos:", get_db_path())
        print("Supabase configurado:", supabase_configured())

        # La aplicación abre inmediatamente con SQLite.
        # La nube se consulta después, sin bloquear la interfaz.
        Clock.schedule_once(
            lambda *_: self.restore_from_cloud_once(),
            1.0,
        )

        # Aviso operativo: solo aparece si no hay apertura de caja.
        Clock.schedule_once(
            lambda *_: self.check_cash_opening_alert(),
            2.2,
        )

        # Primer reintento automático.
        Clock.schedule_once(
            lambda *_: self.request_auto_sync(),
            5.0,
        )

        # Reintentos periódicos. Si no hay internet, no interrumpe al usuario.
        Clock.schedule_interval(
            lambda *_: self.request_auto_sync(),
            SYNC_INTERVAL_SECONDS,
        )

        # Asistente automático de ruta: alerta inicial y revisión periódica.
        Clock.schedule_once(lambda *_: self.check_collection_route(force=True), 2.0)
        Clock.schedule_interval(
            lambda *_: self.check_collection_route(),
            self.route_check_interval_seconds,
        )

    def check_cash_opening_alert(self):
        """Muestra aviso después del login solo si el cobrador no tiene caja abierta."""
        try:
            if not getattr(self, "authenticated", False):
                return

            # En modo dueño único, el administrador también opera caja.
            # En modo multiusuario normal, el admin solo ve consolidado.
            if is_admin_role() and not MODO_DUENO_UNICO:
                return

            # Si ya abrió caja, no mostrar nada.
            if get_journey_status() == "abierta":
                return

            content = BoxLayout(
                orientation="vertical",
                padding=dp(14),
                spacing=dp(12),
            )

            msg = Label(
                text=(
                    "No se ha realizado apertura de caja para este cobrador.\n\n"
                    "Antes de cobrar, prestar, renovar o registrar movimientos, abre la caja."
                ),
                color=WHITE,
                font_size="13sp",
                halign="center",
                valign="middle",
            )
            msg.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            content.add_widget(msg)

            buttons = BoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(48),
                spacing=dp(10),
            )

            popup = Popup(
                title="Apertura de caja pendiente",
                content=content,
                size_hint=(0.92, None),
                height=dp(340),
                auto_dismiss=False,
            )

            later = Button(
                text="Más tarde",
                background_normal="",
                background_color=(0.55, 0.58, 0.63, 1),
                color=WHITE,
                bold=True,
            )
            open_now = Button(
                text="Abrir caja ahora",
                background_normal="",
                background_color=SUCCESS,
                color=WHITE,
                bold=True,
            )

            later.bind(on_release=popup.dismiss)

            def go_open_cash(*_):
                popup.dismiss()
                self.go("resumen")
                Clock.schedule_once(
                    lambda *_: self.sm.get_screen("resumen").confirm_open_day(),
                    0.35,
                )

            open_now.bind(on_release=go_open_cash)
            buttons.add_widget(later)
            buttons.add_widget(open_now)
            content.add_widget(buttons)
            popup.open()

        except Exception as error:
            print("CASH OPENING ALERT ERROR:", error)

    def on_resume(self):
        """Al volver a la app, actualiza agenda y notifica trabajo pendiente."""
        Clock.schedule_once(lambda *_: self.check_collection_route(force=True), 0.5)
        return True

    def check_collection_route(self, force=False):
        try:
            refresh_clients_cache()
            workload = collection_workload()
            today_key = iso_today()
            notification_key = (
                f"{today_key}:{len(workload['overdue'])}:"
                f"{len(workload['today'])}:{workload['expected_today']}"
            )

            if workload["count"] > 0 and (
                force or notification_key != self.last_route_notification_key
            ):
                send_collection_notification(workload)
                self.last_route_notification_key = notification_key

            if hasattr(self, "sm") and self.sm.current == "clientes":
                screen = self.sm.get_screen("clientes")
                screen.render_route_alert()
                screen.render_clients()
        except Exception as error:
            print("COLLECTION ROUTE CHECK ERROR:", error)

    def request_auto_sync(self, force_pull=False):
        """
        Solicita sincronización en segundo plano.

        La función retorna de inmediato, de modo que el usuario puede seguir
        registrando clientes, cuotas y movimientos aunque no haya internet.
        """
        if not supabase_configured():
            self.last_sync_ok = False
            self.last_sync_message = "Supabase no configurado"
            return

        if self.sync_in_progress:
            return

        now_monotonic = time.monotonic()
        if (
            not force_pull
            and now_monotonic - self.last_sync_request_at
            < self.minimum_sync_gap_seconds
        ):
            return

        self.last_sync_request_at = now_monotonic
        self.sync_in_progress = True

        worker = threading.Thread(
            target=self._do_auto_sync,
            kwargs={"force_pull": force_pull},
            daemon=True,
        )
        worker.start()

    def _do_auto_sync(self, force_pull=False):
        """
        Ejecuta la red fuera del hilo gráfico de Kivy.
        """
        try:
            # sync_all_to_cloud ya hace:
            # 1. subir pendientes locales;
            # 2. descargar datos de Supabase;
            # 3. reconciliar eliminaciones.
            ok, message = sync_all_to_cloud(silent=True)

            self.last_sync_ok = bool(ok)
            self.last_sync_message = (
                "Sincronizado correctamente"
                if ok
                else "Pendiente - sin conexión"
            )

            if ok:
                self.cloud_restore_done = True
                register_successful_cloud_backup()

            print("AUTO SYNC:", ok, message)

            Clock.schedule_once(
                lambda *_: self._after_background_sync(ok),
                0,
            )

        except Exception as error:
            self.last_sync_ok = False
            self.last_sync_message = "Pendiente - sin conexión"
            print("AUTO SYNC OFFLINE:", error)

        finally:
            self.sync_in_progress = False

    def _after_background_sync(self, ok):
        """
        Actualiza la caché después de sincronizar sin reconstruir formularios
        donde el usuario pueda estar escribiendo.
        """
        try:
            refresh_memory_from_db(normalize=True)

            if not hasattr(self, "sm"):
                return

            current_screen = self.sm.current_screen
            if not current_screen:
                return

            if hasattr(current_screen, "sync_status"):
                current_screen.sync_status = (
                    "Sincronizado correctamente"
                    if ok
                    else "Pendiente"
                )

            # Solo reconstruir pantallas de consulta. No tocar formularios.
            safe_to_rebuild = {
                "clientes",
                "todos_clientes",
                "resumen",
                "clientes_pagaron_hoy",
            }

            if (
                current_screen.name in safe_to_rebuild
                and hasattr(current_screen, "build")
            ):
                current_screen.build()

        except Exception as error:
            print("ERROR REFRESH POST SYNC:", error)


    def confirm_logout(self):
        confirm_popup(
            "Cerrar sesión",
            "¿Deseas salir de esta cuenta y volver al acceso con usuario y PIN?",
            self.logout,
        )

    def logout(self):
        """Cierra la sesión activa y vuelve a la pantalla de acceso."""
        self.authenticated = False
        self.selected_client = None
        self.current_user = None
        self.current_username = ""
        self.current_user_name = ""
        self.current_cobrador_id = ""
        self.current_role = ""

        try:
            refresh_memory_from_db(normalize=False)
        except Exception as error:
            print("LOGOUT REFRESH ERROR:", error)

        if hasattr(self, "sm"):
            self.sm.current = "login"

    def go(self, screen_name):
        if screen_name != "login" and not getattr(self, "authenticated", False):
            self.sm.current = "login"
            return

        admin_only = {
            "configuracion",
            "auditoria",
            "cierres_semanales",
            "cartera_calle",
            "clientes_riesgo",
            "caja_central",
            "usuarios",
            "asignar_cobradores",
        }

        if screen_name in admin_only and getattr(self, "current_role", "Administrador") != "Administrador":
            show_popup(
                "Acceso restringido",
                "Esta sección requiere rol Administrador.",
                height=240,
            )
            return

        self.sm.current = screen_name


if __name__ == "__main__":
    CobrosV12App().run()
