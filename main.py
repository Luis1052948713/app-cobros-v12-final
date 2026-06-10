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
    Publica el PDF en Descargas/CobrosV12.

    Android 10+:
    usa MediaStore para respetar el almacenamiento restringido.

    Retorna:
        display_path
        open_ok
        open_message
    """
    source = Path(pdf_path)

    if platform != "android":
        open_ok = False
        open_message = "PDF guardado."

        if open_after:
            open_ok, open_message = open_pdf_file(str(source))

        return str(source), open_ok, open_message

    try:
        from importlib import import_module

        jnius_module = import_module("jnius")
        autoclass = jnius_module.autoclass
        jarray = jnius_module.jarray

        PythonActivity = autoclass(
            "org.kivy.android.PythonActivity"
        )
        MediaStore = autoclass("android.provider.MediaStore")
        ContentValues = autoclass(
            "android.content.ContentValues"
        )
        BuildVersion = autoclass("android.os.Build$VERSION")
        Environment = autoclass("android.os.Environment")

        activity = PythonActivity.mActivity
        resolver = activity.getContentResolver()

        values = ContentValues()
        values.put(
            MediaStore.MediaColumns.DISPLAY_NAME,
            source.name,
        )
        values.put(
            MediaStore.MediaColumns.MIME_TYPE,
            "application/pdf",
        )

        if BuildVersion.SDK_INT >= 29:
            values.put(
                MediaStore.MediaColumns.RELATIVE_PATH,
                Environment.DIRECTORY_DOWNLOADS + "/CobrosV12",
            )
            values.put(
                MediaStore.MediaColumns.IS_PENDING,
                1,
            )

        uri = resolver.insert(
            MediaStore.Downloads.EXTERNAL_CONTENT_URI,
            values,
        )

        if uri is None:
            raise RuntimeError(
                "Android no permitió crear el archivo en Descargas."
            )

        output_stream = resolver.openOutputStream(uri)

        if output_stream is None:
            raise RuntimeError(
                "No se pudo abrir el archivo de destino."
            )

        # Android OutputStream.write() exige un byte[] de Java.
        # Se convierten los bytes de Python a enteros con signo (-128 a 127)
        # y luego a un arreglo Java compatible mediante jarray('b').
        raw_pdf_bytes = source.read_bytes()
        signed_pdf_bytes = [
            value if value < 128 else value - 256
            for value in raw_pdf_bytes
        ]
        java_pdf_bytes = jarray("b")(signed_pdf_bytes)

        output_stream.write(java_pdf_bytes)
        output_stream.flush()
        output_stream.close()

        if BuildVersion.SDK_INT >= 29:
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

        display_path = (
            "Descargas/CobrosV12/" + source.name
        )

        if open_after:
            open_ok, open_message = open_pdf_file(uri)
        else:
            open_ok = False
            open_message = "PDF guardado sin abrir."

        return display_path, open_ok, open_message

    except Exception as error:
        error_detail = (
            f"{type(error).__name__}: {error!r}"
        )
        print(
            "ERROR EXPORTANDO PDF A DESCARGAS:",
            error_detail,
        )

        return (
            str(source),
            False,
            "El PDF se generó en el almacenamiento privado, "
            "pero no pudo copiarse a Descargas. "
            f"Detalle: {error_detail}",
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
                return str(db_dir / "cobros_v12.db")
        except Exception:
            pass

    return str(Path(__file__).resolve().parent / "cobros_v12.db")


def get_connection():
    conn = sqlite3.connect(get_db_path())
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return column_name in [row[1] for row in cursor.fetchall()]


def ensure_column(cursor, table_name, column_name, column_definition):
    if not column_exists(cursor, table_name, column_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def init_database():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento TEXT,
            nombre TEXT NOT NULL,
            telefono TEXT,
            direccion TEXT,
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

    closure_columns = [
        ("observacion_apertura", "TEXT"),
        ("observacion_cierre", "TEXT"),
        ("efectivo_contado", "INTEGER NOT NULL DEFAULT 0"),
        ("diferencia_caja", "INTEGER NOT NULL DEFAULT 0"),
        ("estado_cuadre", "TEXT NOT NULL DEFAULT 'sin_arqueo'"),
        ("opened_at", "TEXT"),
        ("closed_at", "TEXT"),
    ]

    existing_closure_columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(cierres_caja)"
        ).fetchall()
    }

    for column_name, column_type in closure_columns:
        if column_name not in existing_closure_columns:
            cursor.execute(
                f"ALTER TABLE cierres_caja "
                f"ADD COLUMN {column_name} {column_type}"
            )

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
            opened_at TEXT,
            closed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

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

    conn.commit()
    conn.close()


def load_clients_from_db():
    global CLIENTES
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, documento, nombre, telefono, direccion, producto,
               valor_credito, interes, total_credito, cuota, numero_cuotas,
               saldo, pagadas, pendientes, cobro, estado, ultimo_tipo,
               codeudor_documento, codeudor_nombre, codeudor_movil,
               valor_seguro, beneficiario, obs_seguro, created_at, updated_at,
               proximo_cobro, ultima_fecha_pago, aporte_acumulado, synced
        FROM clientes
        ORDER BY nombre ASC
    """)

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
               observacion, synced
        FROM transacciones
        ORDER BY id ASC
    """)

    TRANSACCIONES = [dict(row) for row in cursor.fetchall()]
    conn.close()


def load_movimientos_from_db():
    global MOVIMIENTOS_CAJA
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, tipo, concepto, valor, observaciones, fecha, synced
        FROM movimientos_caja
        ORDER BY id ASC
    """)

    MOVIMIENTOS_CAJA = [dict(row) for row in cursor.fetchall()]
    conn.close()


def refresh_memory_from_db():
    update_due_statuses()
    load_clients_from_db()
    load_transacciones_from_db()
    load_movimientos_from_db()


def insert_client_db(cliente):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO clientes (
            documento, nombre, telefono, direccion, producto,
            valor_credito, interes, total_credito, cuota, numero_cuotas,
            saldo, pagadas, pendientes, cobro, estado, ultimo_tipo,
            codeudor_documento, codeudor_nombre, codeudor_movil,
            valor_seguro, beneficiario, obs_seguro, created_at, updated_at,
            proximo_cobro, ultima_fecha_pago, aporte_acumulado, synced
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        cliente.get("documento", ""),
        cliente.get("nombre", "SIN NOMBRE"),
        cliente.get("telefono", ""),
        cliente.get("direccion", ""),
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
    ))

    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_client_db(cliente):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE clientes
        SET documento = ?, nombre = ?, telefono = ?, direccion = ?, producto = ?,
            valor_credito = ?, interes = ?, total_credito = ?, cuota = ?, numero_cuotas = ?,
            saldo = ?, pagadas = ?, pendientes = ?, cobro = ?, estado = ?, ultimo_tipo = ?,
            codeudor_documento = ?, codeudor_nombre = ?, codeudor_movil = ?,
            valor_seguro = ?, beneficiario = ?, obs_seguro = ?, updated_at = ?,
            proximo_cobro = ?, ultima_fecha_pago = ?,
            aporte_acumulado = ?, synced = ?
        WHERE id = ?
    """, (
        cliente.get("documento", ""),
        cliente.get("nombre", "SIN NOMBRE"),
        cliente.get("telefono", ""),
        cliente.get("direccion", ""),
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
        SELECT id, documento, nombre, telefono, direccion, producto,
               valor_credito, interes, total_credito, cuota, numero_cuotas,
               saldo, pagadas, pendientes, cobro, estado, ultimo_tipo,
               codeudor_documento, codeudor_nombre, codeudor_movil,
               valor_seguro, beneficiario, obs_seguro, created_at, updated_at,
               proximo_cobro, ultima_fecha_pago, aporte_acumulado, synced
        FROM clientes
        WHERE id = ?
    """, (int(cliente_id),))

    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def reset_client_status_db(cliente_id):
    cliente = get_client_by_id(cliente_id)
    if cliente:
        cliente["estado"] = "pendiente"
        cliente["ultimo_tipo"] = "Pendiente por cobrar"
        update_client_db(cliente)


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

    conn.commit()
    conn.close()


def insert_movement_db(movimiento):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO movimientos_caja
        (tipo, concepto, valor, observaciones, fecha, synced)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        movimiento.get("tipo", ""),
        movimiento.get("concepto", ""),
        int(movimiento.get("valor", 0)),
        movimiento.get("observaciones", ""),
        movimiento.get("fecha", today_text()),
        int(movimiento.get("synced", 0)),
    ))

    conn.commit()
    conn.close()


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


def get_cash_closure(date_iso=None):
    date_iso = date_iso or iso_today()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM cierres_caja WHERE fecha_iso = ?",
        (date_iso,),
    )

    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def get_journey_status(date_iso=None):
    closure = get_cash_closure(date_iso)

    if not closure:
        return "sin_abrir"

    return closure.get("estado", "sin_abrir")


def open_cash_journey(
    date_iso=None,
    opening_cash=None,
    observation="",
):
    date_iso = date_iso or iso_today()
    existing = get_cash_closure(date_iso)

    if existing and existing.get("estado") in (
        "abierta",
        "cerrada",
    ):
        raise ValueError(
            "La jornada de esta fecha ya fue abierta."
        )

    calculated_opening = cash_balance_before_date(date_iso)

    if opening_cash is None:
        opening_cash = calculated_opening

    opening_cash = int(opening_cash)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO cierres_caja (
            fecha_iso,
            caja_inicial,
            recaudo,
            ingresos,
            egresos,
            saldo_final,
            pagos,
            no_pagos,
            aplazados,
            estado,
            observacion_apertura,
            observacion_cierre,
            opened_at,
            closed_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, 0, 0, 0, ?, 0, 0, 0, ?, ?, '', ?, '', ?, ?)
        ON CONFLICT(fecha_iso) DO UPDATE SET
            caja_inicial = excluded.caja_inicial,
            saldo_final = excluded.saldo_final,
            estado = excluded.estado,
            observacion_apertura = excluded.observacion_apertura,
            opened_at = excluded.opened_at,
            updated_at = excluded.updated_at
    """, (
        date_iso,
        opening_cash,
        opening_cash,
        "abierta",
        observation.strip(),
        now_text(),
        now_text(),
        now_text(),
    ))

    conn.commit()
    conn.close()

    return get_cash_closure(date_iso)


def save_cash_closure(
    date_iso=None,
    observation="",
    physical_cash=None,
):
    date_iso = date_iso or iso_today()
    existing = get_cash_closure(date_iso)

    if not existing:
        raise ValueError(
            "La jornada debe abrirse antes de cerrarla."
        )

    if existing.get("estado") != "abierta":
        raise ValueError(
            "La jornada ya se encuentra cerrada."
        )

    metrics = daily_metrics(date_iso)
    opening_cash = int(existing.get("caja_inicial", 0))
    closing_cash = (
        opening_cash
        + metrics["income"]
        + metrics["collected"]
        - metrics["expenses"]
    )

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
        SET recaudo = ?,
            ingresos = ?,
            egresos = ?,
            saldo_final = ?,
            pagos = ?,
            no_pagos = ?,
            aplazados = ?,
            estado = ?,
            observacion_cierre = ?,
            efectivo_contado = ?,
            diferencia_caja = ?,
            estado_cuadre = ?,
            closed_at = ?,
            updated_at = ?
        WHERE fecha_iso = ?
    """, (
        metrics["collected"],
        metrics["income"],
        metrics["expenses"],
        closing_cash,
        len(metrics["payments"]),
        len(metrics["no_payments"]),
        len(metrics["postponed"]),
        "cerrada",
        observation.strip(),
        physical_cash,
        cash_difference,
        reconciliation_status,
        now_text(),
        now_text(),
        date_iso,
    ))

    conn.commit()
    conn.close()

    return get_cash_closure(date_iso)



def mark_all_as_synced():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE clientes SET synced = 1")
    cursor.execute("UPDATE transacciones SET synced = 1")
    cursor.execute("UPDATE movimientos_caja SET synced = 1")
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
    conn.close()
    return clientes + tx + mv



def current_cash_balance():
    """
    Calcula saldo disponible en caja:
    ingresos + recaudos de clientes - egresos.
    """
    try:
        ingresos = sum(int(m.get("valor", 0)) for m in MOVIMIENTOS_CAJA if m.get("tipo") == "Ingreso")
        egresos = sum(int(m.get("valor", 0)) for m in MOVIMIENTOS_CAJA if m.get("tipo") == "Egreso")
        recaudos = sum(int(t.get("valor", 0)) for t in TRANSACCIONES if t.get("tipo") in ("Cuota", "Aporte"))
        return ingresos + recaudos - egresos
    except Exception:
        return 0


def update_due_statuses():
    """
    Si el cliente pagó y ya llegó su próxima fecha de cobro,
    vuelve automáticamente a pendiente para que aparezca amarillo.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        today = iso_today()

        cursor.execute("""
            UPDATE clientes
            SET estado = 'pendiente',
                ultimo_tipo = 'Pendiente por cobrar',
                updated_at = ?
            WHERE estado IN ('pagado', 'aporte')
              AND proximo_cobro IS NOT NULL
              AND proximo_cobro <> ''
              AND proximo_cobro <= ?
              AND pendientes > 0
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


def supabase_request(table_name, payload, method="POST"):
    if not supabase_configured():
        return False, "Supabase no configurado"

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table_name}"
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



def supabase_get(table_name):
    """
    Descarga datos desde Supabase filtrando por cobrador_id.
    Sirve para restaurar datos en un celular nuevo.
    """
    if not supabase_configured():
        return False, "Supabase no configurado", []

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table_name}?select=*&cobrador_id=eq.{COBRADOR_ID}"

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
    Descarga clientes de Supabase y reconcilia eliminados remotos.

    Si un cliente fue eliminado en Supabase, también se elimina localmente
    si ya estaba sincronizado. Los clientes locales pendientes synced=0
    se conservan.
    """
    ok, msg, rows = supabase_get("clientes")
    if not ok:
        return False, msg

    # Solo las eliminaciones pendientes de subir deben bloquear
    # temporalmente la restauración desde la nube.
    pending_deleted_client_ids = get_deleted_ids(
        "cliente",
        only_pending=True,
    )

    all_remote_ids = {
        int(row.get("id"))
        for row in rows
        if row.get("id") is not None
    }

    obsolete_marks_removed = clear_obsolete_deleted_marks(
        "cliente",
        all_remote_ids,
    )

    rows = [
        row
        for row in rows
        if int(row.get("id"))
        not in pending_deleted_client_ids
    ]

    conn = get_connection()
    cursor = conn.cursor()

    remote_ids = set()

    for r in rows:
        client_id = int(r.get("id"))
        remote_ids.add(client_id)

        cursor.execute("""
            INSERT OR REPLACE INTO clientes (
                id, documento, nombre, telefono, direccion, producto,
                valor_credito, interes, total_credito, cuota, numero_cuotas,
                saldo, pagadas, pendientes, cobro, estado, ultimo_tipo,
                codeudor_documento, codeudor_nombre, codeudor_movil,
                valor_seguro, beneficiario, obs_seguro, created_at, updated_at,
                proximo_cobro, ultima_fecha_pago, aporte_acumulado, synced
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            client_id,
            r.get("documento", ""),
            r.get("nombre", "SIN NOMBRE"),
            r.get("telefono", ""),
            r.get("direccion", ""),
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
            1,
        ))

    cursor.execute("SELECT id FROM clientes WHERE synced = 1")
    local_synced_ids = {int(row[0]) for row in cursor.fetchall()}

    ids_to_delete = (
        local_synced_ids
        - remote_ids
        - pending_deleted_client_ids
    )

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
    Descarga transacciones desde Supabase y reconcilia eliminados remotos.
    """
    ok, msg, rows = supabase_get("transacciones")
    if not ok:
        return False, msg

    deleted_client_ids = get_deleted_ids("cliente")
    rows = [r for r in rows if not r.get("cliente_id") or int(r.get("cliente_id")) not in deleted_client_ids]

    conn = get_connection()
    cursor = conn.cursor()

    remote_ids = set()

    for r in rows:
        tx_id = int(r.get("id"))
        remote_ids.add(tx_id)

        cursor.execute("""
            INSERT OR REPLACE INTO transacciones (
                id, cliente_id, cliente, tipo, valor, metodo, fecha,
                numero_cuotas, saldo_anterior, saldo_nuevo,
                cuotas_pagadas_total, cuotas_pendientes_total,
                observacion, synced
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tx_id,
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
            1,
        ))

    cursor.execute("SELECT id FROM transacciones WHERE synced = 1")
    local_synced_ids = {int(row[0]) for row in cursor.fetchall()}

    ids_to_delete = local_synced_ids - remote_ids

    for tx_id in ids_to_delete:
        cursor.execute("DELETE FROM transacciones WHERE id = ? AND synced = 1", (tx_id,))

    conn.commit()
    conn.close()

    return True, f"Transacciones descargadas: {len(rows)} | Eliminadas locales: {len(ids_to_delete)}"



def pull_movements_from_cloud():
    """
    Descarga movimientos de caja desde Supabase y reconcilia eliminados.

    Si un movimiento fue eliminado directamente en Supabase, también se elimina
    de SQLite local, siempre que ya estuviera sincronizado (synced=1).
    Los movimientos locales pendientes (synced=0) se conservan para no perder
    registros hechos sin internet.
    """
    ok, msg, rows = supabase_get("movimientos_caja")
    if not ok:
        return False, msg

    conn = get_connection()
    cursor = conn.cursor()

    remote_ids = set()

    for r in rows:
        movement_id = int(r.get("id"))
        remote_ids.add(movement_id)

        cursor.execute("""
            INSERT OR REPLACE INTO movimientos_caja (
                id, tipo, concepto, valor, observaciones, fecha, synced
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            movement_id,
            r.get("tipo", ""),
            r.get("concepto", ""),
            int(r.get("valor") or 0),
            r.get("observaciones", ""),
            r.get("fecha", today_text()),
            1,
        ))

    # Reconciliación de eliminados remotos:
    # si el registro local estaba sincronizado y ya no existe en Supabase,
    # se elimina localmente.
    cursor.execute("SELECT id FROM movimientos_caja WHERE synced = 1")
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
        SELECT id, documento, nombre, telefono, direccion, producto,
               valor_credito, interes, total_credito, cuota, numero_cuotas,
               saldo, pagadas, pendientes, cobro, estado, ultimo_tipo,
               codeudor_documento, codeudor_nombre, codeudor_movil,
               valor_seguro, beneficiario, obs_seguro, created_at, updated_at,
               proximo_cobro, ultima_fecha_pago, aporte_acumulado
        FROM clientes
        WHERE synced = 0
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    if not rows:
        conn.close()
        return True, "Sin clientes pendientes"
    payload = []
    for row in rows:
        row["cobrador_id"] = COBRADOR_ID
        payload.append(row)
    ok, msg = supabase_request("clientes", payload)
    if ok:
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(f"UPDATE clientes SET synced = 1 WHERE id IN ({placeholders})", ids)
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
        SELECT id, cliente_id, cliente, tipo, valor, metodo, fecha,
               numero_cuotas, saldo_anterior, saldo_nuevo,
               cuotas_pagadas_total, cuotas_pendientes_total, observacion
        FROM transacciones
        WHERE synced = 0
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    if not rows:
        conn.close()
        return True, "Sin transacciones pendientes"
    for row in rows:
        row["cobrador_id"] = COBRADOR_ID
    ok, msg = supabase_request("transacciones", rows)
    if ok:
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(f"UPDATE transacciones SET synced = 1 WHERE id IN ({placeholders})", ids)
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
        SELECT id, tipo, concepto, valor, observaciones, fecha
        FROM movimientos_caja
        WHERE synced = 0
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    if not rows:
        conn.close()
        return True, "Sin movimientos pendientes"
    for row in rows:
        row["cobrador_id"] = COBRADOR_ID
    ok, msg = supabase_request("movimientos_caja", rows)
    if ok:
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(f"UPDATE movimientos_caja SET synced = 1 WHERE id IN ({placeholders})", ids)
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
    def __init__(self, title, show_back=False, on_back=None, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(66), **kwargs)
        self.padding = [dp(12), dp(8), dp(12), dp(8)]
        self.spacing = dp(8)

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

        label = Label(text=title, color=WHITE, bold=True, font_size="17sp", halign="left", valign="middle")
        label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        self.add_widget(label)

    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size


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
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(30), spacing=dp(6), **kwargs)

        left = Label(text=label, color=MUTED, bold=True, font_size="12sp", halign="left", valign="middle", size_hint_x=0.42)
        right = Label(text=str(value), color=TEXT, font_size="12sp", halign="right", valign="middle", size_hint_x=0.58)
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
            ("clientes", "Clientes", "clientes", "clientes.png"),
            ("nuevo", "Nuevo", "nuevo_cliente", "nuevo.png"),
            ("caja", "Caja", "movimientos", "caja.png"),
        ]:
            self.add_widget(NavItem(self.app, label, screen, icon_name, active=(key == active)))

    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size


# ============================================================
# CLIENTES
# ============================================================

class ClienteCard(RoundedBox):
    def __init__(self, cliente, on_click, **kwargs):
        estado = cliente.get("estado", "pendiente")
        bg_status, border_color, badge_text = estado_colores(estado)

        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(116),
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

        body = BoxLayout(orientation="vertical", padding=[dp(12), dp(9), dp(0), dp(9)], spacing=dp(5))

        top = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(32), spacing=dp(8))
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
            width=dp(84),
            color=WHITE if badge_text != "PENDIENTE" else DARK,
            bold=True,
            font_size="9sp",
            halign="center",
            valign="middle",
        )
        badge_bg = border_color if badge_text != "PENDIENTE" else GOLD
        with badge.canvas.before:
            Color(*badge_bg)
            badge.bg = RoundedRectangle(pos=badge.pos, size=badge.size, radius=[dp(12)])
        badge.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos))
        badge.bind(size=lambda w, *_: setattr(w.bg, "size", w.size))

        top.add_widget(avatar)
        top.add_widget(name)
        top.add_widget(badge)

        amounts = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(28), spacing=dp(8))
        cuota = Label(text=f"Cuota: [b]{money(cliente.get('cuota', 0))}[/b]", markup=True, color=TEXT, font_size="12sp", halign="left")
        saldo = Label(text=f"Saldo: [b]{money(cliente.get('saldo', 0))}[/b]", markup=True, color=TEXT, font_size="12sp", halign="right")
        cuota.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        saldo.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        amounts.add_widget(cuota)
        amounts.add_widget(saldo)

        extra = Label(text=f"Tel: {cliente.get('telefono', '')} | Pendientes: {cliente.get('pendientes', 0)}", color=MUTED, font_size="10sp", halign="left", size_hint_y=None, height=dp(18))
        hint = Label(text="Tocar para gestionar", color=BLUE, bold=True, font_size="10sp", halign="left", size_hint_y=None, height=dp(18))
        extra.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        hint.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        body.add_widget(top)
        body.add_widget(amounts)
        body.add_widget(extra)
        body.add_widget(hint)

        self.add_widget(side)
        self.add_widget(body)
        self.bind(on_touch_down=self._pressed)

    def _pressed(self, widget, touch):
        if self.collide_point(*touch.pos):
            self.on_click(self.cliente)
            return True
        return False


class ClientesScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="clientes", **kwargs)
        self.app_ref = None

        root = BoxLayout(orientation="vertical")
        root.add_widget(Header("::V12:: Lista de Clientes"))

        tools = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(72), padding=[dp(12), dp(9), dp(12), dp(9)])
        row = BoxLayout(orientation="horizontal", spacing=dp(8))

        self.search = TextInput(
            hint_text="Buscar cliente...",
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
        root.add_widget(tools)

        self.scroll = ScrollView()
        self.client_list = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(10), dp(12), dp(80)],
            spacing=dp(10),
            size_hint_y=None,
        )
        self.client_list.bind(minimum_height=self.client_list.setter("height"))
        self.scroll.add_widget(self.client_list)
        root.add_widget(self.scroll)

        self.nav_container = BoxLayout(size_hint_y=None, height=dp(66))
        root.add_widget(self.nav_container)

        self.add_widget(root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        refresh_memory_from_db()

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
            refresh_memory_from_db()

        self.nav_container.clear_widgets()
        self.nav_container.add_widget(BottomNav(self.app_ref, active="clientes"))
        self.render_clients()

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
        self.client_list.clear_widgets()

        if query:
            # Cuando el usuario busca, se muestran todos los clientes,
            # incluso pagados, finalizados o con aporte.
            filtered = [
                cliente for cliente in CLIENTES
                if query in cliente.get("nombre", "").lower()
                or query in cliente.get("telefono", "").lower()
                or query in cliente.get("documento", "").lower()
            ]
        else:
            # En la lista principal solo se muestran clientes pendientes,
            # no pago o aplazados. Los verdes desaparecen hasta su próxima fecha.
            filtered = [
                cliente for cliente in CLIENTES
                if cliente.get("estado") not in ("pagado", "aporte")
                and int(cliente.get("pendientes", 0)) > 0
                and int(cliente.get("saldo", 0)) > 0
            ]

        if not filtered:
            empty_box = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(160), padding=dp(14), spacing=dp(8))
            empty_title = (
                "No se encontraron coincidencias"
                if query
                else "No hay clientes pendientes por cobrar"
            )
            empty_message = (
                "Prueba buscando por nombre, documento o teléfono."
                if query
                else "Los clientes pagados se ocultan aquí, pero aparecen al buscarlos."
            )

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
            height=dp(222),
            padding=[dp(12), dp(10), dp(12), dp(8)],
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
        metrics_wrap = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, height=dp(88))
        self.metrics_row_1 = BoxLayout(orientation="horizontal", spacing=dp(8))
        self.metrics_row_2 = BoxLayout(orientation="horizontal", spacing=dp(8))
        metrics_wrap.add_widget(self.metrics_row_1)
        metrics_wrap.add_widget(self.metrics_row_2)
        top.add_widget(metrics_wrap)

        filters = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, height=dp(62))
        self.filter_row_1 = BoxLayout(orientation="horizontal", spacing=dp(6))
        self.filter_row_2 = BoxLayout(orientation="horizontal", spacing=dp(6))
        filters.add_widget(self.filter_row_1)
        filters.add_widget(self.filter_row_2)
        top.add_widget(filters)

        actions = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(42),
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
        refresh_memory_from_db()
        self.build_filters()
        self.render_metrics()
        self.render_clients()

    def refresh_local_list(self):
        refresh_memory_from_db()
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
        box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(40), padding=[dp(8), dp(4), dp(8), dp(4)])
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
        verdes = len([c for c in CLIENTES if c.get("estado") in ("pagado", "aporte")])
        no_pago = len([c for c in CLIENTES if c.get("estado") == "no_pago"])
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
            return estado in ("pagado", "aporte")
        if self.current_filter == "no_pago":
            return estado == "no_pago"
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
        self.cliente = get_client_by_id(self.app_ref.selected_client.get("id")) if self.app_ref.selected_client else None
        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Gestión del Cliente", show_back=True, on_back=lambda: self.app_ref.go("clientes")))

        if not self.cliente:
            self.root.add_widget(Label(text="Cliente no encontrado", color=WHITE))
            return

        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", padding=[dp(14), dp(14), dp(14), dp(20)], spacing=dp(12), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        bg_status, border_color, badge_text = estado_colores(self.cliente.get("estado", "pendiente"))
        card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(390), padding=[dp(14), dp(12), dp(14), dp(12)], spacing=dp(8))
        card.bg_color = bg_status

        title = Label(text=self.cliente.get("nombre", "SIN NOMBRE"), color=TEXT, bold=True, font_size="17sp", halign="left", size_hint_y=None, height=dp(30))
        title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        card.add_widget(title)
        card.add_widget(DetailRow("Estado", badge_text))
        card.add_widget(DetailRow("Documento", self.cliente.get("documento") or "No registrado"))
        card.add_widget(DetailRow("Teléfono", self.cliente.get("telefono") or "No registrado"))
        card.add_widget(DetailRow("Producto", self.cliente.get("producto") or "Crédito"))
        card.add_widget(DetailRow("Valor Crédito", money(self.cliente.get("valor_credito", 0))))
        card.add_widget(DetailRow("Total Crédito", money(self.cliente.get("total_credito", 0))))
        card.add_widget(DetailRow("Cuota", money(self.cliente.get("cuota", 0))))
        card.add_widget(DetailRow("Tipo Cobro", self.cliente.get("cobro", "Diario")))
        card.add_widget(DetailRow("Saldo", money(self.cliente.get("saldo", 0))))
        card.add_widget(DetailRow("Pendientes", str(self.cliente.get("pendientes", 0))))
        card.add_widget(DetailRow("Próx. cobro", display_date_from_iso(self.cliente.get("proximo_cobro", ""))))

        content.add_widget(card)

        credito_finalizado = (
            int(self.cliente.get("saldo", 0)) <= 0
            or int(self.cliente.get("pendientes", 0)) <= 0
        )

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
            btn_renovar = SmallButton(
                "RENOVAR PRÉSTAMO",
                bg_color=SUCCESS,
            )
            btn_renovar.bind(
                on_release=lambda *_: self.go_renovar()
            )
            content.add_widget(btn_renovar)
        else:
            content.add_widget(btn_cobrar)

        content.add_widget(btn_historial)
        content.add_widget(btn_editar)

        if not credito_finalizado:
            content.add_widget(btn_reset)

        content.add_widget(btn_borrar)

        help_card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(154), padding=[dp(14), dp(12), dp(14), dp(12)])
        help_card.add_widget(Label(text="Regla del sistema", color=TEXT, bold=True, font_size="14sp", halign="center", size_hint_y=None, height=dp(24)))
        for label, value in [
            ("Verde", "Pagó cuota o realizó aporte."),
            ("Amarillo", "Pendiente o siguiente día."),
            ("Rojo", "Cliente marcado como no pago."),
            ("Bloqueo", "Si ya está verde, solo permite aporte."),
        ]:
            help_card.add_widget(DetailRow(label, value))

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
        self.app_ref.selected_client = self.cliente
        self.app_ref.go("renovar_prestamo")

    def go_editar(self):
        self.app_ref.selected_client = self.cliente
        self.app_ref.go("editar_cliente")

    def reset_estado(self):
        reset_client_status_db(self.cliente.get("id"))
        refresh_memory_from_db()
        show_popup("Estado reiniciado", "El cliente quedó pendiente por cobrar.")
        Clock.schedule_once(lambda *_: self.app_ref.go("clientes"), 0.7)

    def confirm_delete(self):
        confirm_popup("Eliminar cliente", f"¿Eliminar a {self.cliente.get('nombre', 'este cliente')}?\nTambién se borrarán sus transacciones.", self.delete_client)

    def delete_client(self):
        cliente_eliminado = dict(self.cliente) if self.cliente else None

        # 1. Intentar eliminar primero en Supabase para que no se restaure.
        try:
            if cliente_eliminado and supabase_configured():
                ok, msg = delete_remote_client_bundle(cliente_eliminado)
                print("DELETE REMOTE:", ok, msg)
        except Exception as error:
            print("ERROR DELETE REMOTE:", error)

        # 2. Eliminar en SQLite local y corregir caja.
        delete_client_db(self.cliente.get("id"))
        refresh_memory_from_db()

        # 3. Limpiar selección y volver a la lista.
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
        self.cliente = (
            get_client_by_id(self.app_ref.selected_client.get("id"))
            if self.app_ref.selected_client else None
        )
        refresh_memory_from_db()
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

        scroll = ScrollView(
            do_scroll_x=False,
            bar_width=dp(4),
            scroll_type=["bars", "content"],
        )

        content = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(18), dp(14), dp(40)],
            spacing=dp(22),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        # ---------------- RESUMEN DEL CRÉDITO ----------------
        summary = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(420),
            padding=[dp(16), dp(16), dp(16), dp(16)],
            spacing=dp(10),
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
        summary.add_widget(DetailRow("Cuotas pagadas", str(self.cliente.get("pagadas", 0))))
        summary.add_widget(DetailRow("Cuotas pendientes", str(self.cliente.get("pendientes", 0))))
        summary.add_widget(DetailRow("Saldo actual", money(self.cliente.get("saldo", 0))))
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

    def transaction_card(self, tx):
        tipo = tx.get("tipo", "Movimiento")

        if tipo == "Cuota":
            accent = SUCCESS
        elif tipo == "Aporte":
            accent = GOLD
        elif tipo == "No Pago":
            accent = DANGER
        elif tipo in ("Renovación", "Migración"):
            accent = BLUE
        else:
            accent = (0.45, 0.48, 0.55, 1)

        card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(315),
            padding=[dp(16), dp(14), dp(16), dp(14)],
            spacing=dp(10),
        )

        header = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(34),
            spacing=dp(8),
        )

        type_badge = Label(
            text=tipo,
            color=accent if tipo != "Aporte" else DARK,
            bold=True,
            font_size="14sp",
            halign="left",
            valign="middle",
            size_hint_x=0.45,
        )
        type_badge.bind(
            size=lambda instance, value: setattr(instance, "text_size", value)
        )

        label_date = Label(
            text=str(tx.get("fecha", "")),
            color=MUTED,
            font_size="11sp",
            halign="right",
            valign="middle",
            size_hint_x=0.55,
        )
        label_date.bind(
            size=lambda instance, value: setattr(instance, "text_size", value)
        )

        header.add_widget(type_badge)
        header.add_widget(label_date)
        card.add_widget(header)

        line = Widget(size_hint_y=None, height=dp(2))
        with line.canvas:
            Color(accent[0], accent[1], accent[2], 0.75)
            rect = Rectangle(pos=line.pos, size=line.size)
        line.bind(
            pos=lambda instance, value: setattr(rect, "pos", value),
            size=lambda instance, value: setattr(rect, "size", value),
        )
        card.add_widget(line)

        card.add_widget(DetailRow("Valor", money(tx.get("valor", 0))))
        card.add_widget(DetailRow("Cuotas acreditadas", str(tx.get("numero_cuotas", 0))))
        card.add_widget(
            DetailRow(
                "Estado de cuotas",
                f"Pagadas {tx.get('cuotas_pagadas_total', 0)}  |  "
                f"Pendientes {tx.get('cuotas_pendientes_total', 0)}",
            )
        )
        card.add_widget(
            DetailRow(
                "Cambio de saldo",
                f"{money(tx.get('saldo_anterior', 0))}  ->  "
                f"{money(tx.get('saldo_nuevo', 0))}",
            )
        )
        card.add_widget(DetailRow("Método", tx.get("metodo") or "No aplica"))
        card.add_widget(DetailRow("Detalle", tx.get("observacion") or tipo))

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
        self.cliente = get_client_by_id(self.app_ref.selected_client.get("id")) if self.app_ref.selected_client else None
        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Cuota Cliente / Ingreso Cuota", show_back=True, on_back=lambda: self.app_ref.go("gestion_cliente")))

        if not self.cliente:
            self.root.add_widget(Label(text="Cliente no encontrado", color=WHITE))
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
            height=dp(268),
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

        summary.add_widget(DetailRow("Teléfono", self.cliente.get("telefono", "") or "No registrado"))
        summary.add_widget(DetailRow("Pagadas", str(self.cliente.get("pagadas", 0))))
        summary.add_widget(DetailRow("Pendientes", str(self.cliente.get("pendientes", 0))))
        summary.add_widget(DetailRow("Tipo Cobro", self.cliente.get("cobro", "Diario")))
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
            height=dp(586),
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

        for label, widget in [
            ("Valor Cuota", self.valor_cuota),
            ("Saldo Actual", self.saldo_actual),
            ("Valor a Pagar", self.valor_pagar),
            ("Número de Cuotas", self.numero_cuotas),
            ("Nuevo Saldo", self.nuevo_saldo),
            ("Método de Pago", self.metodo_pago),
        ]:
            form.add_widget(self.field_container(label, widget, highlight=(label == "Nuevo Saldo")))

        self._updating_installment_amount = False
        for input_widget in [
            self.valor_pagar,
            self.numero_cuotas,
            self.metodo_pago,
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

        elif estado == "no_pago":
            self.warning.text = "Cliente en rojo. Si entrega dinero, registre Aporte."
            self.warning.color = DANGER

            for btn in self.tipo_buttons:
                if btn.text == "Aporte":
                    btn.disabled = False
                    btn.state = "down"
                    btn.background_color = GOLD
                    btn.color = DARK
                elif btn.text == "Cuota":
                    btn.disabled = True
                    btn.state = "normal"
                    btn.background_color = (0.78, 0.80, 0.84, 1)
                    btn.color = (0.40, 0.40, 0.40, 1)
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
                    self.warning.text = "El cliente quedará marcado en rojo como no pago."
                    self.warning.color = DANGER
                else:
                    btn.background_color = (0.45, 0.48, 0.55, 1)
                    btn.color = WHITE
                    self.warning.text = "El cliente quedará pendiente para el siguiente día."
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
        if estado in ("pagado", "aporte", "no_pago"):
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

    def register_transaction(self):
        if get_journey_status() != "abierta":
            show_popup(
                "Jornada no abierta",
                "Debes abrir la jornada antes de registrar cobros.",
                height=260,
            )
            return

        tipo = self.selected_tipo()
        pago = to_int(self.valor_pagar.text, 0)
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

        elif tipo == "No Pago":
            pago = 0
            cantidad_cuotas = 0
            self.cliente["estado"] = "no_pago"
            self.cliente["ultimo_tipo"] = "No pago"

        elif tipo == "Siguiente Día":
            pago = 0
            cantidad_cuotas = 0
            self.cliente["estado"] = "siguiente"
            self.cliente["ultimo_tipo"] = "Siguiente día"
            self.cliente["proximo_cobro"] = next_due_from_anchor(
                self.cliente.get("proximo_cobro", ""),
                "Diario",
                1,
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
                self.cliente["proximo_cobro"] = next_due_from_anchor(
                    self.cliente.get("proximo_cobro", ""),
                    self.cliente.get("cobro", "Diario"),
                    cantidad_cuotas,
                )

        self.cliente["synced"] = 0
        update_client_db(self.cliente)

        insert_transaction_db({
            "cliente_id": self.cliente.get("id"),
            "cliente": self.cliente.get("nombre", ""),
            "tipo": tipo,
            "valor": pago,
            "metodo": self.metodo_pago.text,
            "fecha": now_text(),
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

        refresh_memory_from_db()
        App.get_running_app().request_auto_sync()

        if tipo == "Aporte":
            faltante = max(
                cuota_unitaria
                - int(self.cliente.get("aporte_acumulado", 0)),
                0,
            )

            show_popup(
                "Aporte registrado",
                f"Valor recibido: {money(pago)}.\n"
                f"Cuotas acreditadas: {cantidad_cuotas}.\n"
                f"Aporte acumulado: "
                f"{money(self.cliente.get('aporte_acumulado', 0))}.\n"
                f"Faltante próxima cuota: {money(faltante)}.\n"
                f"Nuevo saldo: {money(self.cliente.get('saldo', 0))}.",
                height=360,
            )

        elif tipo == "Cuota":
            show_popup(
                "Transacción registrada",
                f"Cuotas acreditadas: {cantidad_cuotas}.\n"
                f"Pendientes: "
                f"{self.cliente.get('pendientes', 0)}.\n"
                f"Nuevo saldo: "
                f"{money(self.cliente.get('saldo', 0))}.",
            )

        else:
            show_popup(
                "Transacción registrada",
                "La novedad fue guardada correctamente.",
            )

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
        Calcula automáticamente el estado económico del cartón viejo.

        Cuotas pendientes:
            cuotas totales - cuotas pagadas

        Total pagado acumulado:
            cuotas pagadas * valor de cuota + aporte parcial

        Saldo actual:
            total del crédito - total pagado acumulado
        """
        total_installments = max(
            to_int(self.numero_cuotas.text, 0),
            0,
        )
        paid_installments = max(
            to_int(self.cuotas_pagadas_existente.text, 0),
            0,
        )
        installment_value = max(
            to_int(self.valor_cuota.text, 0),
            0,
        )
        total_credit = max(
            to_int(self.total_credito.text, 0),
            0,
        )
        partial_contribution = max(
            to_int(self.aporte_existente.text, 0),
            0,
        )

        # Evitar mostrar valores incoherentes mientras se escribe.
        paid_installments_for_calculation = min(
            paid_installments,
            total_installments,
        )

        pending_installments = max(
            total_installments - paid_installments,
            0,
        )

        paid_by_installments = (
            paid_installments_for_calculation
            * installment_value
        )

        total_paid = min(
            paid_by_installments + partial_contribution,
            total_credit,
        )

        current_balance = max(
            total_credit - total_paid,
            0,
        )

        self.cuotas_pendientes_existente.text = str(
            pending_installments
        )
        self.total_pagado_existente.text = format_thousands(
            total_paid
        )
        self.saldo_existente.text = format_thousands(
            current_balance
        )


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
        if get_journey_status() != "abierta":
            show_popup(
                "Jornada no abierta",
                "Debes abrir la jornada antes de crear un préstamo.",
                height=260,
            )
            return

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

        if existing_loan:
            fecha_inicio_iso = normalize_date_input(
                self.fecha_inicio_existente.text
            )
            proximo_cobro_iso = normalize_date_input(
                self.proximo_cobro_existente.text
            )
            pagadas = max(
                to_int(self.cuotas_pagadas_existente.text, 0),
                0,
            )
            pendientes = max(numero_cuotas - pagadas, 0)
            self.calculate_existing_status()

            saldo_actual = to_int(self.saldo_existente.text, 0)
            total_pagado_acumulado = to_int(
                self.total_pagado_existente.text,
                0,
            )
            aporte_acumulado = max(
                to_int(self.aporte_existente.text, 0),
                0,
            )

            if not fecha_inicio_iso:
                show_popup(
                    "Fecha requerida",
                    "Seleccione la fecha original de inicio.",
                )
                return

            if not proximo_cobro_iso and pendientes > 0:
                show_popup(
                    "Próxima fecha requerida",
                    "Seleccione la próxima fecha real de cobro.",
                )
                return

            if pagadas > numero_cuotas:
                show_popup(
                    "Cuotas inválidas",
                    "Las cuotas pagadas no pueden superar el total.",
                )
                return

            if saldo_actual < 0 or saldo_actual > total_credito:
                show_popup(
                    "Saldo inválido",
                    "El saldo actual debe estar entre cero y el total del crédito.",
                )
                return

            if aporte_acumulado >= cuota and cuota > 0:
                show_popup(
                    "Aporte acumulado inválido",
                    "El aporte parcial debe ser menor que una cuota. "
                    "Las cuotas completas deben registrarse como pagadas.",
                    height=290,
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

                # Si la fecha ya llegó, aparece amarillo.
                # Si es futura, queda oculto hasta ese día.
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
            saldo_caja = current_cash_balance()

            if valor_credito > saldo_caja:
                show_popup(
                    "Saldo insuficiente",
                    f"No se puede crear el préstamo.\n"
                    f"Valor a prestar: {money(valor_credito)}\n"
                    f"Saldo en caja: {money(saldo_caja)}\n\n"
                    f"Primero registre un INGRESO o CAJA INICIAL.",
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

        if existing_loan:
            # Registro inicial para que el historial explique cómo entró.
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
                    "Préstamo existente cargado al sistema. "
                    f"Fecha original: "
                    f"{self.fecha_inicio_existente.text}. "
                    f"Total pagado acumulado: "
                    f"{money(total_pagado_acumulado)}. "
                    "No generó egreso de caja."
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

        refresh_memory_from_db()
        App.get_running_app().request_auto_sync()

        self.reset_on_next_entry = True

        if existing_loan:
            message = (
                "Préstamo existente cargado correctamente.\n"
                "No se descontó dinero de la caja."
            )
        else:
            message = (
                "Cliente y crédito activados correctamente.\n"
                "El desembolso fue descontado de caja."
            )

        show_popup(
            "Registro completado",
            message,
            height=280,
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

        summary = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(152),
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
        content.add_widget(summary)

        self.valor_credito = MoneyTextInput()
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
            height=dp(530),
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
        self.cliente = get_client_by_id(self.app_ref.selected_client.get("id")) if self.app_ref.selected_client else None
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

        card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(820), padding=[dp(12), dp(12), dp(12), dp(12)], spacing=dp(8))

        self.documento = AppTextInput(text=str(self.cliente.get("documento", "")))
        self.nombre = AppTextInput(text=str(self.cliente.get("nombre", "")))
        telefono = str(self.cliente.get("telefono", "")).replace("+57", "").strip()
        self.movil = AppTextInput(text=telefono)
        self.direccion = AppTextInput(text=str(self.cliente.get("direccion", "")))
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
        if get_journey_status() != "abierta":
            show_popup(
                "Jornada no abierta",
                "Debes abrir la jornada antes de registrar movimientos.",
                height=260,
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
# RESUMEN
# ============================================================

class MetricRow(BoxLayout):
    def __init__(self, left, right, highlight=False, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(38) if not highlight else dp(46), padding=[dp(10), 0, dp(10), 0], **kwargs)
        bg_color = (0.98, 0.98, 1, 1) if not highlight else (1.0, 0.95, 0.78, 1)
        with self.canvas.before:
            Color(*bg_color)
            self.bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
        self.bind(pos=self._update_bg, size=self._update_bg)

        left_label = Label(text=left, color=TEXT if highlight else MUTED, bold=highlight, font_size="12sp", halign="left", valign="middle")
        right_label = Label(text=right, color=TEXT, bold=highlight, font_size="12sp", halign="right", valign="middle")
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
        refresh_memory_from_db()
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


class ResumenScreen(Screen):
    sync_status = StringProperty("Pendiente")

    def __init__(self, **kwargs):
        super().__init__(name="resumen", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        refresh_memory_from_db()
        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("::V12:: Resumen del Día", show_back=True, on_back=lambda: self.app_ref.go("clientes")))

        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", padding=[dp(12), dp(12), dp(12), dp(18)], spacing=dp(10), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        metrics = daily_metrics()
        closure = get_cash_closure()
        journey_status = get_journey_status()

        if closure and journey_status in ("abierta", "cerrada"):
            metrics["opening_cash"] = int(
                closure.get("caja_inicial", 0)
            )
            metrics["closing_cash"] = (
                metrics["opening_cash"]
                + metrics["income"]
                + metrics["collected"]
                - metrics["expenses"]
            )

        total_clientes = len(CLIENTES)
        clientes_nuevos = len(metrics["new_clients"])
        pagos = len(metrics["payments"])
        no_pagos = len(metrics["no_payments"])
        aplazados = len(metrics["postponed"])
        recaudo_dia = metrics["collected"]
        ingresos = metrics["income"]
        egresos = metrics["expenses"]
        caja_inicial = metrics["opening_cash"]
        recaudo_esperado = metrics["expected"]
        saldo_caja = metrics["closing_cash"]
        pendientes_sync = count_pending_sync()

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
            ("Caja Inicial", money(caja_inicial)),
            ("Recaudo Esperado", money(recaudo_esperado)),
            ("Recaudo del día", money(recaudo_dia)),
            ("Ingresos", money(ingresos)),
            ("Egresos", money(egresos)),
            ("Pendientes Nube", str(pendientes_sync)),
            (
                "Estado Jornada",
                {
                    "sin_abrir": "SIN ABRIR",
                    "abierta": "ABIERTA",
                    "cerrada": "CERRADA",
                }.get(journey_status, "SIN ABRIR"),
            ),
            ("Sincronización", self.sync_status),
        ]:
            report.add_widget(MetricRow(left, right))

        report.add_widget(MetricRow("Saldo en Caja", money(saldo_caja), highlight=True))
        content.add_widget(report)

        actions = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(230),
            spacing=dp(8),
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
        row_cloud.add_widget(cloud)

        row_pdf = BoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(46),
        )

        if journey_status == "sin_abrir":
            close_button = PillButton(
                "Abrir Jornada",
                bg_color=SUCCESS,
            )
            close_button.bind(
                on_release=lambda *_: self.confirm_open_day()
            )

        elif journey_status == "abierta":
            close_button = PillButton(
                "Cerrar Jornada",
                bg_color=GOLD,
            )
            close_button.bind(
                on_release=lambda *_: self.confirm_close_day()
            )

        else:
            close_button = PillButton(
                "Jornada Cerrada",
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

        actions.add_widget(row1)
        actions.add_widget(row2)
        actions.add_widget(row_cloud)
        actions.add_widget(row_pdf)
        content.add_widget(actions)

        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def confirm_open_day(self):
        calculated_opening = cash_balance_before_date()

        content = BoxLayout(
            orientation="vertical",
            padding=dp(14),
            spacing=dp(12),
        )

        info = Label(
            text=(
                f"Fecha: {today_text()}\n"
                "Escribe la base con la que empieza el día.\n"
                f"Sugerencia automática: {money(calculated_opening)}"
            ),
            color=WHITE,
            font_size="14sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(78),
        )
        info.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        base_label = FieldLabel("Caja inicial / base del día")
        base_input = MoneyTextInput(
            text=format_thousands(calculated_opening),
            hint_text="Ej: 100.000",
        )

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
            text="Abrir Jornada",
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
        content.add_widget(buttons)

        popup = Popup(
            title="Abrir Jornada",
            content=content,
            size_hint=(0.90, None),
            height=dp(310),
            auto_dismiss=False,
        )

        cancel.bind(on_release=popup.dismiss)
        accept.bind(
            on_release=lambda *_: self.open_day(
                popup,
                to_int(base_input.text, calculated_opening),
            )
        )
        popup.open()

    def open_day(self, popup=None, opening_cash=None):
        try:
            journey = open_cash_journey(opening_cash=opening_cash)

            if popup is not None:
                popup.dismiss()

            show_popup(
                "Jornada abierta",
                "La jornada fue abierta correctamente.\n\n"
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
        status = get_journey_status()

        if status == "sin_abrir":
            show_popup(
                "Jornada sin abrir",
                "Primero debes abrir la jornada.",
            )
            return

        if status == "cerrada":
            show_popup(
                "Jornada cerrada",
                "La jornada de hoy ya fue cerrada.",
            )
            return

        closure = get_cash_closure()
        metrics = daily_metrics()

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
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(8),
        )

        scroll = ScrollView(
            do_scroll_x=False,
            bar_width=dp(4),
            scroll_type=["bars", "content"],
        )
        content = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            size_hint_y=None,
            padding=[dp(2), dp(2), dp(2), dp(8)],
        )
        content.bind(minimum_height=content.setter("height"))

        # Encabezado
        header = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(90),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(4),
        )
        header.bg_color = (0.94, 0.97, 1, 1)
        header_title = Label(
            text="Arqueo y cierre de caja",
            color=BLUE,
            bold=True,
            font_size="17sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(28),
        )
        header_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        header_text = Label(
            text=(
                "Sigue estos 3 pasos: 1) revisa el resumen, 2) escribe el dinero en mano, "
                "3) confirma si la caja cuadra."
            ),
            color=MUTED,
            font_size="11sp",
            halign="left",
            valign="middle",
        )
        header_text.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        header.add_widget(header_title)
        header.add_widget(header_text)
        content.add_widget(header)

        # Paso 1: Resumen del sistema
        system_box = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(300),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(6),
        )

        step1_title = Label(
            text="Paso 1. Resumen que calcula el sistema",
            color=DARK,
            bold=True,
            font_size="14sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(24),
        )
        step1_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        system_box.add_widget(step1_title)

        system_box.add_widget(DetailRow("Fecha", today_text()))
        system_box.add_widget(DetailRow("Caja inicial", money(opening_cash)))
        system_box.add_widget(DetailRow("Recaudo del día", money(metrics["collected"])))
        system_box.add_widget(DetailRow("Ingresos adicionales", money(metrics["income"])))
        system_box.add_widget(DetailRow("Egresos del día", money(metrics["expenses"])))
        system_box.add_widget(DetailRow("Pendientes de nube", str(pending_cloud)))

        expected_card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(76),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(2),
        )
        expected_card.bg_color = (0.99, 0.97, 0.88, 1)
        expected_lbl_1 = Label(
            text="Saldo esperado por el sistema",
            color=MUTED,
            font_size="11sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(20),
        )
        expected_lbl_1.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        expected_lbl_2 = Label(
            text=money(expected_cash),
            color=DARK,
            bold=True,
            font_size="22sp",
            halign="center",
            valign="middle",
        )
        expected_lbl_2.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        expected_card.add_widget(expected_lbl_1)
        expected_card.add_widget(expected_lbl_2)
        system_box.add_widget(expected_card)
        content.add_widget(system_box)

        # Paso 2: Arqueo físico
        count_box = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(168),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(6),
        )
        count_box.bg_color = (0.99, 0.98, 0.94, 1)

        step2_title = Label(
            text="Paso 2. Escribe el dinero que tienes en mano",
            color=DARK,
            bold=True,
            font_size="14sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(24),
        )
        step2_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        step2_help = Label(
            text="Cuenta el efectivo físico y escríbelo aquí. Puedes editar el valor libremente.",
            color=MUTED,
            font_size="11sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(32),
        )
        step2_help.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        count_box.add_widget(step2_title)
        count_box.add_widget(step2_help)

        physical_cash_input = MoneyTextInput(
            hint_text="Ej: 2.080.000",
            text=format_thousands(expected_cash),
        )
        count_box.add_widget(physical_cash_input)
        content.add_widget(count_box)

        # Paso 3: Resultado de comparación
        result_box = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(222),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(6),
        )

        step3_title = Label(
            text="Paso 3. Resultado del arqueo",
            color=DARK,
            bold=True,
            font_size="14sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(24),
        )
        step3_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        result_box.add_widget(step3_title)

        comparison_card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(76),
            padding=[dp(10), dp(8), dp(10), dp(8)],
            spacing=dp(4),
        )
        comparison_card.bg_color = (0.94, 0.97, 1, 1)
        comparison_label = Label(
            text="",
            color=TEXT,
            bold=True,
            font_size="16sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(26),
        )
        comparison_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        difference_label = Label(
            text="",
            color=MUTED,
            font_size="12sp",
            halign="center",
            valign="middle",
        )
        difference_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        comparison_card.add_widget(comparison_label)
        comparison_card.add_widget(difference_label)
        result_box.add_widget(comparison_card)

        recap_box = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(82),
            padding=[dp(10), dp(8), dp(10), dp(8)],
            spacing=dp(2),
        )
        recap_box.bg_color = (0.97, 0.98, 1, 1)
        recap_expected = Label(text="", color=TEXT, font_size="11sp", halign="left", valign="middle", size_hint_y=None, height=dp(20))
        recap_counted = Label(text="", color=TEXT, font_size="11sp", halign="left", valign="middle", size_hint_y=None, height=dp(20))
        recap_diff = Label(text="", color=TEXT, font_size="11sp", halign="left", valign="middle", size_hint_y=None, height=dp(20))
        for lbl in (recap_expected, recap_counted, recap_diff):
            lbl.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            recap_box.add_widget(lbl)
        result_box.add_widget(recap_box)

        observation_label = FieldLabel(
            "Observación (solo si hay sobrante o faltante)"
        )
        observation_input = AppTextInput(
            hint_text="Ej: faltante pendiente de verificar",
            multiline=True,
        )
        observation_input.height = dp(56)
        result_box.add_widget(observation_label)
        result_box.add_widget(observation_input)
        content.add_widget(result_box)

        def refresh_comparison(*_):
            physical = to_int(physical_cash_input.text, 0)
            difference = physical - expected_cash

            recap_expected.text = f"Sistema espera: {money(expected_cash)}"
            recap_counted.text = f"Dinero contado: {money(physical)}"
            recap_diff.text = f"Diferencia: {money(abs(difference)) if difference != 0 else money(0)}"

            if difference == 0:
                comparison_label.text = "CAJA CUADRADA"
                comparison_label.color = SUCCESS
                difference_label.text = "El dinero físico coincide con el sistema."
                difference_label.color = SUCCESS
                comparison_card.bg_color = (0.93, 0.98, 0.93, 1)
            elif difference > 0:
                comparison_label.text = "HAY SOBRANTE"
                comparison_label.color = BLUE
                difference_label.text = f"Sobran {money(difference)} frente al sistema."
                difference_label.color = BLUE
                comparison_card.bg_color = (0.92, 0.97, 1, 1)
            else:
                comparison_label.text = "HAY FALTANTE"
                comparison_label.color = DANGER
                difference_label.text = f"Faltan {money(abs(difference))} frente al sistema."
                difference_label.color = DANGER
                comparison_card.bg_color = (1.0, 0.94, 0.94, 1)

        physical_cash_input.bind(text=refresh_comparison)
        Clock.schedule_once(refresh_comparison, 0)

        # Aviso de sincronización
        notice = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(70),
            padding=dp(10),
        )
        notice.bg_color = (1.0, 0.95, 0.95, 1) if pending_cloud > 0 else (0.93, 0.98, 0.93, 1)
        notice_text = (
            "Hay registros pendientes de sincronizar. Recomendación: ejecuta Carga Completa antes del cierre."
            if pending_cloud > 0
            else "Todo está sincronizado. Si el efectivo cuadra, puedes confirmar el cierre."
        )
        notice_label = Label(
            text=notice_text,
            color=TEXT,
            font_size="11sp",
            halign="left",
            valign="middle",
        )
        notice_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        notice.add_widget(notice_label)
        content.add_widget(notice)

        scroll.add_widget(content)
        outer.add_widget(scroll)

        buttons = BoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(48),
        )
        cancel = Button(
            text="Seguir revisando",
            background_normal="",
            background_color=(0.56, 0.60, 0.66, 1),
            color=WHITE,
            bold=True,
        )
        confirm = Button(
            text="Confirmar cierre",
            background_normal="",
            background_color=DANGER,
            color=WHITE,
            bold=True,
        )
        buttons.add_widget(cancel)
        buttons.add_widget(confirm)
        outer.add_widget(buttons)

        popup = Popup(
            title="Cierre de Caja",
            content=outer,
            size_hint=(0.94, 0.94),
            auto_dismiss=False,
        )
        cancel.bind(on_release=popup.dismiss)

        def validate_and_close(*_):
            physical = to_int(physical_cash_input.text, -1)
            difference = physical - expected_cash
            observation = observation_input.text.strip()

            if physical < 0:
                show_popup(
                    "Monto requerido",
                    "Escribe cuánto dinero tienes físicamente en mano.",
                )
                return

            if difference != 0 and not observation:
                show_popup(
                    "Observación requerida",
                    "La caja presenta una diferencia. Escribe una observación antes de cerrar.",
                    height=270,
                )
                return

            popup.dismiss()
            self.close_day(physical, observation)

        confirm.bind(on_release=validate_and_close)
        popup.open()

    def close_day(self, physical_cash=None, observation=""):

        try:
            closure = save_cash_closure(
                physical_cash=physical_cash,
                observation=observation,
            )
            metrics = daily_metrics()

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
                text="Jornada cerrada correctamente",
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
            result_box.add_widget(DetailRow("Fecha", today_text()))
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


# ============================================================
# APP PRINCIPAL
# ============================================================

class CobrosV12App(App):
    selected_client = None
    cloud_restore_done = False

    # Estado offline-first
    sync_in_progress = False
    last_sync_ok = False
    last_sync_message = "Pendiente"

    def build(self):
        self.title = "Cobros V12 Mobile"
        try:
            init_database()
            refresh_memory_from_db()
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
        self.sm.add_widget(ResumenScreen())

        self.shell.add_widget(self.sm)
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
        Actualiza memoria y pantalla después de una sincronización exitosa.
        No muestra ventanas emergentes en sincronización automática.
        """
        try:
            refresh_memory_from_db()

            if hasattr(self, "sm"):
                current_screen = self.sm.current_screen

                if current_screen and hasattr(
                    current_screen,
                    "sync_status",
                ):
                    current_screen.sync_status = (
                        "Sincronizado correctamente"
                        if ok
                        else "Pendiente"
                    )

                if current_screen and hasattr(
                    current_screen,
                    "build",
                ):
                    current_screen.build()

        except Exception as error:
            print("ERROR REFRESH POST SYNC:", error)


    def go(self, screen_name):
        self.sm.current = screen_name


if __name__ == "__main__":
    CobrosV12App().run()
