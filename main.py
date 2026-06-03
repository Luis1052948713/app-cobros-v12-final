# ============================================================
# Cobros V12 Mobile
# App móvil Python Offline/Online - Gestión de Créditos y Cobros
# Proyecto: app-cobros-v12-final
# Framework: Kivy
#
# Instalación:
#   pip install kivy
#
# Ejecución:
#   python main.py
# ============================================================

from datetime import datetime, timedelta
from pathlib import Path
import os
import sqlite3

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import NumericProperty, ObjectProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
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
BG = (0.95, 0.96, 0.98, 1)
WHITE = (1, 1, 1, 1)
TEXT = (0.10, 0.12, 0.16, 1)
MUTED = (0.43, 0.47, 0.54, 1)
DARK = (0.12, 0.14, 0.18, 1)
SUCCESS = (0.12, 0.62, 0.32, 1)
DANGER = (0.83, 0.18, 0.18, 1)

STATUS_GREEN = (0.86, 0.98, 0.89, 1)
STATUS_YELLOW = (1.00, 0.96, 0.78, 1)
STATUS_RED = (1.00, 0.88, 0.88, 1)
STATUS_BORDER_GREEN = (0.12, 0.62, 0.32, 1)
STATUS_BORDER_YELLOW = (0.93, 0.69, 0.13, 1)
STATUS_BORDER_RED = (0.83, 0.18, 0.18, 1)

# Caja base del cobrador al iniciar la ruta.
CAJA_INICIAL_BASE = 350000


# ============================================================
# DATOS DEMO
# ============================================================

CLIENTES_DEMO = [
    {
        "nombre": "MARISOL CARDOZO",
        "telefono": "+57 300 456 1122",
        "cuota": 20000,
        "saldo": 480000,
        "pagadas": 6,
        "pendientes": 24,
        "estado": "pendiente",
        "ultimo_tipo": "Pendiente por cobrar",
        "documento": "100000001",
        "direccion": "Sin dirección",
    },
    {
        "nombre": "JORGE ALFONSO PEREZ",
        "telefono": "+57 301 778 2211",
        "cuota": 15000,
        "saldo": 315000,
        "pagadas": 9,
        "pendientes": 21,
        "estado": "pendiente",
        "ultimo_tipo": "Pendiente por cobrar",
        "documento": "100000002",
        "direccion": "Sin dirección",
    },
    {
        "nombre": "KAREN JULIANA TORRES",
        "telefono": "+57 310 998 4433",
        "cuota": 25000,
        "saldo": 625000,
        "pagadas": 5,
        "pendientes": 25,
        "estado": "pendiente",
        "ultimo_tipo": "Pendiente por cobrar",
        "documento": "100000003",
        "direccion": "Sin dirección",
    },
    {
        "nombre": "LUIS MIGUEL BARRIOS",
        "telefono": "+57 320 111 9090",
        "cuota": 18000,
        "saldo": 396000,
        "pagadas": 8,
        "pendientes": 22,
        "estado": "pendiente",
        "ultimo_tipo": "Pendiente por cobrar",
        "documento": "100000004",
        "direccion": "Sin dirección",
    },
    {
        "nombre": "ANA MILENA GOMEZ",
        "telefono": "+57 315 555 1212",
        "cuota": 30000,
        "saldo": 720000,
        "pagadas": 6,
        "pendientes": 24,
        "estado": "pendiente",
        "ultimo_tipo": "Pendiente por cobrar",
        "documento": "100000005",
        "direccion": "Sin dirección",
    },
    {
        "nombre": "CARLOS EDUARDO DIAZ",
        "telefono": "+57 300 999 4444",
        "cuota": 12000,
        "saldo": 240000,
        "pagadas": 10,
        "pendientes": 20,
        "estado": "pendiente",
        "ultimo_tipo": "Pendiente por cobrar",
        "documento": "100000006",
        "direccion": "Sin dirección",
    },
]

CLIENTES = []
TRANSACCIONES = []
MOVIMIENTOS_CAJA = []


# ============================================================
# UTILIDADES
# ============================================================

def today_text():
    return datetime.now().strftime("%d/%m/%Y")


def today_iso():
    """
    Fecha estándar para filtrar registros diarios.
    """
    return datetime.now().strftime("%Y-%m-%d")


def frequency_days(frecuencia):
    """Convierte frecuencia de cobro a días."""
    value = str(frecuencia or "Diario").strip().lower()
    if value == "semanal":
        return 7
    if value == "quincenal":
        return 15
    if value == "mensual":
        return 30
    return 1


def next_due_date(frecuencia, base_date=None):
    """Calcula próxima fecha de cobro en formato YYYY-MM-DD."""
    if base_date is None:
        base = datetime.now()
    elif isinstance(base_date, datetime):
        base = base_date
    else:
        base = datetime.strptime(str(base_date), "%Y-%m-%d")
    return (base + timedelta(days=frequency_days(frecuencia))).strftime("%Y-%m-%d")


def format_date_for_user(iso_date):
    """Convierte YYYY-MM-DD a DD/MM/YYYY para mostrar."""
    try:
        return datetime.strptime(str(iso_date), "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return str(iso_date or "")


def is_due_today_or_before(iso_date):
    """True si la fecha ya llegó o está vencida."""
    if not iso_date:
        return True
    try:
        return str(iso_date) <= today_iso()
    except Exception:
        return True


def is_client_due(cliente):
    return is_due_today_or_before(cliente.get("fecha_proximo_cobro", today_iso()))


def money(value):
    try:
        return "$ {:,.0f}".format(float(value)).replace(",", ".")
    except Exception:
        return "$ 0"


def parse_money_value(text):
    if text is None:
        return 0

    clean = str(text)
    clean = clean.replace("$", "")
    clean = clean.replace(" ", "")
    clean = clean.replace(".", "")
    clean = clean.replace(",", ".")

    try:
        return int(float(clean))
    except Exception:
        return 0


def format_miles(value):
    try:
        return f"{int(float(value)):,}".replace(",", ".")
    except Exception:
        return "0"


def parse_percent_value(text):
    if text is None:
        return 0.0

    clean = str(text).replace("%", "").replace(" ", "").replace(",", ".")

    try:
        return float(clean)
    except Exception:
        return 0.0


def asset_path(filename):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "assets", filename),
        os.path.join(os.getcwd(), "assets", filename),
    ]

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return ""


def is_today_record(item):
    """
    Permite filtrar registros del día.
    Soporta fecha nueva YYYY-MM-DD y fecha anterior DD/MM/YYYY.
    """
    value = str(item.get("fecha", "")).strip()
    return value in [today_iso(), today_text()]


def get_estado_cliente(cliente):
    return cliente.get("estado", "pendiente")


def estado_texto(cliente):
    estado = get_estado_cliente(cliente)

    if estado == "pagado":
        return "PAGADO"
    if estado == "aporte":
        return "APORTE"
    if estado == "no_pago":
        return "NO PAGO"
    if estado == "siguiente":
        return "SIGUIENTE DIA"

    return "PENDIENTE"


def estado_colores(cliente):
    estado = get_estado_cliente(cliente)

    if estado == "pagado":
        return STATUS_GREEN, STATUS_BORDER_GREEN, "PAGADO"

    if estado == "aporte":
        return STATUS_GREEN, STATUS_BORDER_GREEN, "APORTE"

    if estado == "no_pago":
        return STATUS_RED, STATUS_BORDER_RED, "NO PAGO"

    if estado == "siguiente":
        return STATUS_YELLOW, STATUS_BORDER_YELLOW, "SIG. DIA"

    return STATUS_YELLOW, STATUS_BORDER_YELLOW, "PENDIENTE"


def make_popup(title, message):
    content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))

    label = Label(
        text=message,
        color=TEXT,
        font_size="15sp",
        halign="center",
        valign="middle",
    )
    label.bind(size=lambda instance, value: setattr(instance, "text_size", value))

    button = Button(
        text="Aceptar",
        size_hint_y=None,
        height=dp(46),
        background_normal="",
        background_color=BLUE,
        color=WHITE,
        bold=True,
    )

    content.add_widget(label)
    content.add_widget(button)

    popup = Popup(
        title=title,
        content=content,
        size_hint=(0.88, None),
        height=dp(230),
        auto_dismiss=False,
    )
    button.bind(on_release=popup.dismiss)
    popup.open()


# ============================================================
# SQLITE
# ============================================================

def get_db_path():
    try:
        app = App.get_running_app()
        if app and getattr(app, "user_data_dir", None):
            db_dir = Path(app.user_data_dir)
            db_dir.mkdir(parents=True, exist_ok=True)
            return str(db_dir / "cobros_v12.db")
    except Exception:
        pass

    return "cobros_v12.db"


def get_connection():
    return sqlite3.connect(get_db_path())


def init_database():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            telefono TEXT,
            cuota INTEGER NOT NULL DEFAULT 0,
            saldo INTEGER NOT NULL DEFAULT 0,
            pagadas INTEGER NOT NULL DEFAULT 0,
            pendientes INTEGER NOT NULL DEFAULT 0,
            estado TEXT NOT NULL DEFAULT 'pendiente',
            ultimo_tipo TEXT NOT NULL DEFAULT 'Pendiente',
            documento TEXT,
            direccion TEXT,
            frecuencia_cobro TEXT NOT NULL DEFAULT 'Diario',
            fecha_proximo_cobro TEXT,
            created_at TEXT NOT NULL
        )
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
            synced INTEGER NOT NULL DEFAULT 0
        )
    """)

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

    conn.commit()
    conn.close()


def ensure_client_schedule_columns():
    """Migra bases existentes agregando programación de cobro."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(clientes)")
    columns = {row[1] for row in cursor.fetchall()}

    if "frecuencia_cobro" not in columns:
        cursor.execute("ALTER TABLE clientes ADD COLUMN frecuencia_cobro TEXT NOT NULL DEFAULT 'Diario'")

    if "fecha_proximo_cobro" not in columns:
        cursor.execute("ALTER TABLE clientes ADD COLUMN fecha_proximo_cobro TEXT")

    cursor.execute("""
        UPDATE clientes
        SET frecuencia_cobro = COALESCE(NULLIF(frecuencia_cobro, ''), 'Diario'),
            fecha_proximo_cobro = COALESCE(NULLIF(fecha_proximo_cobro, ''), ?)
    """, (today_iso(),))

    conn.commit()
    conn.close()


def seed_database_if_empty():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM clientes")
    total = cursor.fetchone()[0]

    if total == 0:
        for cliente in CLIENTES_DEMO:
            cursor.execute("""
                INSERT INTO clientes
                (nombre, telefono, cuota, saldo, pagadas, pendientes, estado, ultimo_tipo, documento, direccion, frecuencia_cobro, fecha_proximo_cobro, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cliente.get("nombre", ""),
                cliente.get("telefono", ""),
                int(cliente.get("cuota", 0)),
                int(cliente.get("saldo", 0)),
                int(cliente.get("pagadas", 0)),
                int(cliente.get("pendientes", 0)),
                cliente.get("estado", "pendiente"),
                cliente.get("ultimo_tipo", "Pendiente por cobrar"),
                cliente.get("documento", ""),
                cliente.get("direccion", ""),
                cliente.get("frecuencia_cobro", "Diario"),
                cliente.get("fecha_proximo_cobro", today_iso()),
                today_text(),
            ))

    conn.commit()
    conn.close()


def load_clients_from_db():
    global CLIENTES

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nombre, telefono, cuota, saldo, pagadas, pendientes, estado, ultimo_tipo, documento, direccion, frecuencia_cobro, fecha_proximo_cobro
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
        SELECT cliente_id, cliente, tipo, valor, metodo, fecha, synced
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
        SELECT tipo, concepto, valor, observaciones, fecha, synced
        FROM movimientos_caja
        ORDER BY id ASC
    """)

    MOVIMIENTOS_CAJA = [dict(row) for row in cursor.fetchall()]
    conn.close()


def update_due_clients_from_db():
    """
    Si llega la fecha de próximo cobro, vuelve el cliente a pendiente.
    Diario: mañana, semanal: 7 días, quincenal: 15, mensual: 30.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE clientes
        SET estado = 'pendiente',
            ultimo_tipo = 'Pendiente por cobrar'
        WHERE estado IN ('pagado', 'aporte', 'siguiente', 'no_pago')
          AND fecha_proximo_cobro IS NOT NULL
          AND fecha_proximo_cobro <= ?
    """, (today_iso(),))
    conn.commit()
    conn.close()


def refresh_memory_from_db():
    load_transacciones_from_db()
    load_movimientos_from_db()
    update_due_clients_from_db()
    load_clients_from_db()


def get_client_by_id(cliente_id):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nombre, telefono, cuota, saldo, pagadas, pendientes, estado, ultimo_tipo, documento, direccion, frecuencia_cobro, fecha_proximo_cobro
        FROM clientes
        WHERE id = ?
    """, (cliente_id,))

    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def insert_client_db(cliente):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO clientes
        (nombre, telefono, cuota, saldo, pagadas, pendientes, estado, ultimo_tipo, documento, direccion, frecuencia_cobro, fecha_proximo_cobro, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        cliente.get("nombre", ""),
        cliente.get("telefono", ""),
        int(cliente.get("cuota", 0)),
        int(cliente.get("saldo", 0)),
        int(cliente.get("pagadas", 0)),
        int(cliente.get("pendientes", 0)),
        cliente.get("estado", "pendiente"),
        cliente.get("ultimo_tipo", "Pendiente por cobrar"),
        cliente.get("documento", ""),
        cliente.get("direccion", ""),
        cliente.get("frecuencia_cobro", "Diario"),
        cliente.get("fecha_proximo_cobro", today_iso()),
        today_text(),
    ))

    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    refresh_financial_state()

    return new_id


def update_client_in_db(cliente):
    if not cliente.get("id"):
        return

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE clientes
        SET nombre = ?,
            telefono = ?,
            cuota = ?,
            saldo = ?,
            pagadas = ?,
            pendientes = ?,
            estado = ?,
            ultimo_tipo = ?,
            documento = ?,
            direccion = ?,
            frecuencia_cobro = ?,
            fecha_proximo_cobro = ?
        WHERE id = ?
    """, (
        cliente.get("nombre", ""),
        cliente.get("telefono", ""),
        int(cliente.get("cuota", 0)),
        int(cliente.get("saldo", 0)),
        int(cliente.get("pagadas", 0)),
        int(cliente.get("pendientes", 0)),
        cliente.get("estado", "pendiente"),
        cliente.get("ultimo_tipo", "Pendiente por cobrar"),
        cliente.get("documento", ""),
        cliente.get("direccion", ""),
        cliente.get("frecuencia_cobro", "Diario"),
        cliente.get("fecha_proximo_cobro", today_iso()),
        int(cliente.get("id")),
    ))

    conn.commit()
    conn.close()

    refresh_financial_state()


def delete_client_db(cliente_id):
    """
    Elimina completamente un cliente/prestamo y sus transacciones asociadas.
    Esto impacta el Resumen del Día porque:
    - Reduce Número Clientes.
    - Reduce Recaudo Esperado.
    - Quita pagos/no pagos/aplazados asociados al cliente eliminado.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM transacciones WHERE cliente_id = ?", (cliente_id,))
    cursor.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))

    conn.commit()
    conn.close()

    refresh_financial_state()


def reset_client_status_db(cliente_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE clientes
        SET estado = 'pendiente',
            ultimo_tipo = 'Pendiente por cobrar',
            fecha_proximo_cobro = ?
        WHERE id = ?
    """, (today_iso(), cliente_id,))

    conn.commit()
    conn.close()

    refresh_financial_state()


def insert_transaction_db(transaccion):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO transacciones
        (cliente_id, cliente, tipo, valor, metodo, fecha, synced)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        transaccion.get("cliente_id"),
        transaccion.get("cliente", ""),
        transaccion.get("tipo", ""),
        int(transaccion.get("valor", 0)),
        transaccion.get("metodo", ""),
        transaccion.get("fecha", today_iso()),
        int(transaccion.get("synced", 0)),
    ))

    conn.commit()
    conn.close()

    refresh_financial_state()


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
        movimiento.get("fecha", today_iso()),
        int(movimiento.get("synced", 0)),
    ))

    conn.commit()
    conn.close()

    refresh_financial_state()


def mark_all_as_synced():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE transacciones SET synced = 1")
    cursor.execute("UPDATE movimientos_caja SET synced = 1")

    conn.commit()
    conn.close()

    refresh_financial_state()


def calculate_cash_balance():
    """
    Calcula el saldo disponible en caja para el día actual.

    Fórmula diaria:
    saldo = caja inicial
            + recaudos de hoy por cuotas/aportes
            + ingresos de caja de hoy
            - egresos/gastos de caja de hoy

    Los préstamos creados se registran como egresos,
    porque son dinero entregado al cliente.
    """
    recaudos = sum(
        item.get("valor", 0)
        for item in TRANSACCIONES
        if item.get("tipo") in ["Cuota", "Aporte"] and is_today_record(item)
    )

    ingresos = sum(
        item.get("valor", 0)
        for item in MOVIMIENTOS_CAJA
        if item.get("tipo") == "Ingreso" and is_today_record(item)
    )

    egresos = sum(
        item.get("valor", 0)
        for item in MOVIMIENTOS_CAJA
        if item.get("tipo") == "Egreso" and is_today_record(item)
    )

    saldo = CAJA_INICIAL_BASE + recaudos + ingresos - egresos

    return max(saldo, 0)


def calculate_cash_balance_raw():
    """
    Saldo matemático sin forzar mínimo de cero.
    Útil para auditoría y depuración.
    """
    recaudos = sum(
        item.get("valor", 0)
        for item in TRANSACCIONES
        if item.get("tipo") in ["Cuota", "Aporte"] and is_today_record(item)
    )

    ingresos = sum(
        item.get("valor", 0)
        for item in MOVIMIENTOS_CAJA
        if item.get("tipo") == "Ingreso" and is_today_record(item)
    )

    egresos = sum(
        item.get("valor", 0)
        for item in MOVIMIENTOS_CAJA
        if item.get("tipo") == "Egreso" and is_today_record(item)
    )

    return CAJA_INICIAL_BASE + recaudos + ingresos - egresos


def refresh_financial_state():
    """
    Refresca los datos críticos que alimentan el resumen del día.
    Esta función se llama después de crear, editar o eliminar clientes/prestamos,
    registrar pagos, movimientos y sincronización.
    """
    refresh_memory_from_db()


def count_pending_sync():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM transacciones WHERE synced = 0")
    tx = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM movimientos_caja WHERE synced = 0")
    mv = cursor.fetchone()[0]

    conn.close()

    return tx + mv


# ============================================================
# COMPONENTES BASE
# ============================================================

class RoundedBox(BoxLayout):
    bg_color = ObjectProperty(WHITE)
    radius = NumericProperty(14)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.padding = kwargs.get("padding", dp(12))
        self.spacing = kwargs.get("spacing", dp(8))

        with self.canvas.before:
            Color(*self.bg_color)
            self.rect = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[self.radius],
            )

        self.bind(pos=self._update_rect, size=self._update_rect, bg_color=self._update_rect)

    def _update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class Header(BoxLayout):
    def __init__(self, title, show_back=False, on_back=None, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, height=dp(64), **kwargs)

        with self.canvas.before:
            Color(*BLUE)
            self.bg = Rectangle(pos=self.pos, size=self.size)

        self.bind(pos=self._update_bg, size=self._update_bg)

        row = BoxLayout(
            orientation="horizontal",
            padding=[dp(14), dp(8), dp(14), dp(8)],
            spacing=dp(8),
        )

        if show_back:
            back = Button(
                text="<",
                size_hint_x=None,
                width=dp(42),
                background_normal="",
                background_color=BLUE_DARK,
                color=WHITE,
                font_size="22sp",
                bold=True,
            )
            if on_back:
                back.bind(on_release=lambda *_: on_back())
            row.add_widget(back)

        label = Label(
            text=title,
            color=WHITE,
            bold=True,
            font_size="17sp",
            halign="left",
            valign="middle",
        )
        label.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        row.add_widget(label)
        self.add_widget(row)

    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size


class SmallButton(Button):
    def __init__(self, text, bg_color=BLUE, **kwargs):
        super().__init__(
            text=text,
            size_hint_y=None,
            height=dp(44),
            background_normal="",
            background_color=bg_color,
            color=WHITE,
            bold=True,
            font_size="13sp",
            **kwargs,
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
            font_size="13sp",
            **kwargs,
        )


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
            **kwargs,
        )
        self.bind(size=lambda instance, value: setattr(instance, "text_size", value))


class AppTextInput(TextInput):
    def __init__(self, hint_text="", text="", multiline=False, **kwargs):
        super().__init__(
            hint_text=hint_text,
            text=text,
            multiline=multiline,
            size_hint_y=None,
            height=dp(44) if not multiline else dp(88),
            background_normal="",
            background_color=WHITE,
            foreground_color=TEXT,
            cursor_color=BLUE,
            padding=[dp(10), dp(10), dp(10), dp(10)],
            font_size="14sp",
            **kwargs,
        )


class AutoMoneyInput(AppTextInput):
    def __init__(self, hint_text="", text="", **kwargs):
        super().__init__(hint_text=hint_text, text=text, multiline=False, **kwargs)
        self.bind(focus=self._format_on_blur)

    def _format_on_blur(self, instance, focused):
        if not focused:
            value = parse_money_value(self.text)
            if value > 0:
                self.text = format_miles(value)


class AutoNumberInput(AppTextInput):
    def __init__(self, hint_text="", text="", **kwargs):
        super().__init__(hint_text=hint_text, text=text, multiline=False, **kwargs)


class NavItem(BoxLayout):
    def __init__(self, app, label, screen, icon_name, active=False, **kwargs):
        super().__init__(
            orientation="vertical",
            padding=[dp(6), dp(5), dp(6), dp(5)],
            spacing=dp(2),
            **kwargs,
        )

        self.app = app
        self.screen = screen
        self.bg_color = GOLD if active else (0.91, 0.93, 0.96, 1)

        with self.canvas.before:
            Color(*self.bg_color)
            self.bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])

        self.bind(pos=self._update_bg, size=self._update_bg)

        icon_source = asset_path(icon_name)

        if icon_source:
            icon = Image(
                source=icon_source,
                size_hint_y=None,
                height=dp(30),
                allow_stretch=True,
                keep_ratio=True,
            )
        else:
            icon = Label(
                text=label[:2].upper(),
                color=DARK,
                bold=True,
                font_size="14sp",
                size_hint_y=None,
                height=dp(30),
                halign="center",
                valign="middle",
            )

        text = Label(
            text=label,
            color=DARK if active else (0.20, 0.24, 0.30, 1),
            bold=active,
            font_size="12sp",
            size_hint_y=None,
            height=dp(24),
            halign="center",
            valign="middle",
        )
        text.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        self.add_widget(icon)
        self.add_widget(text)

    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.app.go(self.screen, remember=False)
            return True
        return super().on_touch_down(touch)


class BottomNav(BoxLayout):
    def __init__(self, app, active="clientes", **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(76),
            padding=[dp(8), dp(7), dp(8), dp(7)],
            spacing=dp(8),
            **kwargs,
        )

        with self.canvas.before:
            Color(*WHITE)
            self.bg = Rectangle(pos=self.pos, size=self.size)

        self.bind(pos=self._update_bg, size=self._update_bg)

        items = [
            ("clientes", "Clientes", "clientes", "clientes.png"),
            ("nuevo", "Nuevo", "nuevo_cliente", "nuevo.png"),
            ("caja", "Caja", "movimientos", "caja.png"),
        ]

        for key, label, screen, icon_name in items:
            self.add_widget(
                NavItem(
                    app=app,
                    label=label,
                    screen=screen,
                    icon_name=icon_name,
                    active=(key == active),
                )
            )

    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size


# ============================================================
# PANTALLA: CLIENTES
# ============================================================

class ClienteCard(RoundedBox):
    def __init__(self, cliente, on_click, **kwargs):
        bg_status, border_color, badge_text = estado_colores(cliente)

        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(118),
            padding=[dp(0), dp(0), dp(12), dp(0)],
            spacing=dp(0),
            **kwargs,
        )
        self.bg_color = bg_status
        self.cliente = cliente
        self.on_click = on_click

        side = BoxLayout(size_hint_x=None, width=dp(8))
        with side.canvas.before:
            Color(*border_color)
            side.rect = RoundedRectangle(pos=side.pos, size=side.size, radius=[dp(14), 0, 0, dp(14)])
        side.bind(pos=lambda widget, *_: setattr(widget.rect, "pos", widget.pos))
        side.bind(size=lambda widget, *_: setattr(widget.rect, "size", widget.size))

        body = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(9), dp(0), dp(9)],
            spacing=dp(5),
        )

        top = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(34), spacing=dp(8))

        name_value = cliente.get("nombre", "SIN NOMBRE")
        initial = name_value[0].upper() if name_value else "C"

        avatar = Label(
            text=initial,
            size_hint_x=None,
            width=dp(34),
            color=WHITE,
            bold=True,
            font_size="16sp",
            halign="center",
            valign="middle",
        )
        with avatar.canvas.before:
            Color(*border_color)
            avatar.bg = RoundedRectangle(pos=avatar.pos, size=avatar.size, radius=[dp(17)])
        avatar.bind(pos=lambda widget, *_: setattr(widget.bg, "pos", widget.pos))
        avatar.bind(size=lambda widget, *_: setattr(widget.bg, "size", widget.size))

        name = Label(
            text=name_value,
            color=TEXT,
            bold=True,
            font_size="13sp",
            halign="left",
            valign="middle",
        )
        name.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        badge = Label(
            text=badge_text,
            size_hint_x=None,
            width=dp(88),
            color=WHITE if badge_text != "PENDIENTE" else DARK,
            bold=True,
            font_size="9sp",
            halign="center",
            valign="middle",
        )
        badge_bg = GOLD if badge_text == "PENDIENTE" else border_color
        with badge.canvas.before:
            Color(*badge_bg)
            badge.bg = RoundedRectangle(pos=badge.pos, size=badge.size, radius=[dp(12)])
        badge.bind(pos=lambda widget, *_: setattr(widget.bg, "pos", widget.pos))
        badge.bind(size=lambda widget, *_: setattr(widget.bg, "size", widget.size))

        top.add_widget(avatar)
        top.add_widget(name)
        top.add_widget(badge)

        amounts = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(26))

        cuota = Label(
            text=f"Cuota: [b]{money(cliente.get('cuota', 0))}[/b]",
            markup=True,
            color=TEXT,
            font_size="12sp",
            halign="left",
        )
        cuota.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        saldo = Label(
            text=f"Saldo: [b]{money(cliente.get('saldo', 0))}[/b]",
            markup=True,
            color=TEXT,
            font_size="12sp",
            halign="right",
        )
        saldo.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        amounts.add_widget(cuota)
        amounts.add_widget(saldo)

        detail = Label(
            text=f"Tel: {cliente.get('telefono', '')} | Pend: {cliente.get('pendientes', 0)} | Próx: {format_date_for_user(cliente.get('fecha_proximo_cobro', ''))}",
            color=MUTED,
            font_size="10sp",
            halign="left",
            size_hint_y=None,
            height=dp(18),
        )
        detail.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        hint = Label(
            text="Tocar para gestionar",
            color=BLUE,
            bold=True,
            font_size="10sp",
            halign="left",
            size_hint_y=None,
            height=dp(18),
        )
        hint.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        body.add_widget(top)
        body.add_widget(amounts)
        body.add_widget(detail)
        body.add_widget(hint)

        self.add_widget(side)
        self.add_widget(body)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.on_click(self.cliente)
            return True
        return super().on_touch_down(touch)


class ClientesScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="clientes", **kwargs)
        self.app_ref = None

        root = BoxLayout(orientation="vertical", spacing=0)

        header_area = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(140))
        header_area.add_widget(Header("::V12:: Lista de Clientes"))

        tools = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(8), dp(12), dp(8)],
            spacing=dp(8),
            size_hint_y=None,
            height=dp(76),
        )

        row = BoxLayout(orientation="horizontal", spacing=dp(8))

        self.search = TextInput(
            hint_text="Buscar cliente por nombre, documento o telefono...",
            multiline=False,
            background_normal="",
            background_color=WHITE,
            foreground_color=TEXT,
            cursor_color=BLUE,
            padding=[dp(10), dp(10), dp(10), dp(10)],
            font_size="14sp",
        )
        self.search.bind(text=lambda *_: self.render_clients())

        self.summary_btn = Button(
            text="RES",
            size_hint_x=None,
            width=dp(56),
            background_normal="",
            background_color=GOLD,
            color=DARK,
            bold=True,
            font_size="12sp",
        )
        self.summary_btn.bind(on_release=lambda *_: self.app_ref.go("resumen", remember=True))

        self.exit_btn = Button(
            text="SALIR",
            size_hint_x=None,
            width=dp(64),
            background_normal="",
            background_color=DANGER,
            color=WHITE,
            bold=True,
            font_size="11sp",
        )
        self.exit_btn.bind(on_release=lambda *_: self.app_ref.confirm_exit())

        row.add_widget(self.search)
        row.add_widget(self.summary_btn)
        row.add_widget(self.exit_btn)

        tools.add_widget(row)
        header_area.add_widget(tools)

        root.add_widget(header_area)

        self.scroll = ScrollView()
        self.client_list = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(10), dp(12), dp(88)],
            spacing=dp(10),
            size_hint_y=None,
        )
        self.client_list.bind(minimum_height=self.client_list.setter("height"))

        self.scroll.add_widget(self.client_list)
        root.add_widget(self.scroll)

        self.nav_container = BoxLayout(size_hint_y=None, height=dp(76))
        root.add_widget(self.nav_container)

        self.add_widget(root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        try:
            refresh_memory_from_db()
        except Exception as error:
            print("ERROR refresh clientes:", error)

        self.nav_container.clear_widgets()
        self.nav_container.add_widget(BottomNav(self.app_ref, active="clientes"))
        self.render_clients()

    def render_clients(self):
        if not self.app_ref:
            return

        self.client_list.clear_widgets()
        query = self.search.text.strip().lower() if hasattr(self, "search") else ""

        filtered = [
            cliente for cliente in CLIENTES
            if query in cliente.get("nombre", "").lower()
            or query in cliente.get("telefono", "").lower()
            or query in cliente.get("documento", "").lower()
        ]

        if not filtered:
            self.client_list.add_widget(Label(
                text="No se encontraron clientes.",
                color=MUTED,
                size_hint_y=None,
                height=dp(60),
            ))
            return

        for cliente in filtered:
            self.client_list.add_widget(ClienteCard(cliente, self.open_client))

    def open_client(self, cliente):
        self.app_ref.selected_client = cliente
        self.app_ref.go("gestion_cliente", remember=True)


# ============================================================
# PANTALLA: GESTION CLIENTE
# ============================================================

class GestionClienteScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="gestion_cliente", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.cliente = self.app_ref.selected_client

        if not self.cliente:
            self.app_ref.go("clientes", remember=False)
            return

        self.build()

    def info_row(self, label, value):
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(30), spacing=dp(8))

        left = Label(
            text=label,
            color=MUTED,
            font_size="12sp",
            halign="left",
            valign="middle",
            size_hint_x=0.45,
        )
        left.bind(size=lambda instance, value_size: setattr(instance, "text_size", value_size))

        right = Label(
            text=str(value),
            color=TEXT,
            bold=True,
            font_size="12sp",
            halign="right",
            valign="middle",
            size_hint_x=0.55,
        )
        right.bind(size=lambda instance, value_size: setattr(instance, "text_size", value_size))

        row.add_widget(left)
        row.add_widget(right)

        return row

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Gestion del Cliente", show_back=True, on_back=lambda: self.app_ref.safe_back()))

        scroll = ScrollView()
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(14), dp(14), dp(24)],
            spacing=dp(12),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        bg_status, border_color, badge_text = estado_colores(self.cliente)

        card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(370),
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(7),
        )
        card.bg_color = bg_status

        top = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(46), spacing=dp(8))

        initial = self.cliente.get("nombre", "C")[0].upper()
        avatar = Label(
            text=initial,
            size_hint_x=None,
            width=dp(44),
            color=WHITE,
            bold=True,
            font_size="18sp",
            halign="center",
            valign="middle",
        )
        with avatar.canvas.before:
            Color(*border_color)
            avatar.bg = RoundedRectangle(pos=avatar.pos, size=avatar.size, radius=[dp(22)])
        avatar.bind(pos=lambda widget, *_: setattr(widget.bg, "pos", widget.pos))
        avatar.bind(size=lambda widget, *_: setattr(widget.bg, "size", widget.size))

        name_box = BoxLayout(orientation="vertical")

        title = Label(
            text=self.cliente.get("nombre", "SIN NOMBRE"),
            color=TEXT,
            bold=True,
            font_size="16sp",
            halign="left",
            valign="bottom",
        )
        title.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        status = Label(
            text=f"Estado: {badge_text}",
            color=TEXT,
            bold=True,
            font_size="12sp",
            halign="left",
            valign="top",
        )
        status.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        name_box.add_widget(title)
        name_box.add_widget(status)

        top.add_widget(avatar)
        top.add_widget(name_box)

        card.add_widget(top)
        card.add_widget(self.info_row("Documento", self.cliente.get("documento", "Sin documento")))
        card.add_widget(self.info_row("Telefono", self.cliente.get("telefono", "")))
        card.add_widget(self.info_row("Direccion", self.cliente.get("direccion", "Sin direccion")))
        card.add_widget(self.info_row("Cuota", money(self.cliente.get("cuota", 0))))
        card.add_widget(self.info_row("Saldo", money(self.cliente.get("saldo", 0))))
        card.add_widget(self.info_row("Pendientes", self.cliente.get("pendientes", 0)))
        card.add_widget(self.info_row("Frecuencia", self.cliente.get("frecuencia_cobro", "Diario")))
        card.add_widget(self.info_row("Proximo cobro", format_date_for_user(self.cliente.get("fecha_proximo_cobro", ""))))
        card.add_widget(self.info_row("Ultimo", self.cliente.get("ultimo_tipo", "Pendiente")))

        content.add_widget(card)

        cobrar = SmallButton("COBRAR CUOTA / APORTE", bg_color=BLUE)
        cobrar.bind(on_release=lambda *_: self.go_cobrar())

        editar = SmallButton("EDITAR CLIENTE Y PRESTAMO", bg_color=GOLD)
        editar.color = DARK
        editar.bind(on_release=lambda *_: self.go_editar())

        reiniciar = SmallButton("REINICIAR ESTADO A PENDIENTE", bg_color=(0.45, 0.48, 0.55, 1))
        reiniciar.bind(on_release=lambda *_: self.reset_estado())

        eliminar = SmallButton("ELIMINAR CLIENTE", bg_color=DANGER)
        eliminar.bind(on_release=lambda *_: self.confirm_delete())

        content.add_widget(cobrar)
        content.add_widget(editar)
        content.add_widget(reiniciar)
        content.add_widget(eliminar)

        help_card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(145),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(6),
        )

        help_title = Label(
            text="Regla del sistema",
            color=TEXT,
            bold=True,
            font_size="14sp",
            halign="left",
            size_hint_y=None,
            height=dp(24),
        )
        help_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        help_text = Label(
            text=(
                "Verde: cliente pagado o con aporte.\n"
                "Amarillo: pendiente o siguiente dia.\n"
                "Rojo: no pago.\n"
                "Si esta en verde, no se cobra otra cuota; solo aporte."
            ),
            color=MUTED,
            font_size="12sp",
            halign="left",
            valign="top",
        )
        help_text.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        help_card.add_widget(help_title)
        help_card.add_widget(help_text)

        content.add_widget(help_card)
        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def go_cobrar(self):
        self.app_ref.selected_client = self.cliente
        self.app_ref.go("cuota", remember=True)

    def go_editar(self):
        self.app_ref.selected_client = self.cliente
        self.app_ref.go("editar_cliente", remember=True)

    def reset_estado(self):
        reset_client_status_db(self.cliente.get("id"))
        refresh_memory_from_db()

        updated = get_client_by_id(self.cliente.get("id"))
        if updated:
            self.cliente = updated
            self.app_ref.selected_client = updated

        make_popup("Estado reiniciado", "El cliente quedo pendiente por cobrar.")
        Clock.schedule_once(lambda *_: self.app_ref.go("clientes", remember=False), 0.5)

    def confirm_delete(self):
        content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))

        msg = Label(
            text=f"Eliminar a {self.cliente.get('nombre', 'este cliente')}?\nTambien se borraran sus transacciones.",
            color=TEXT,
            font_size="14sp",
            halign="center",
            valign="middle",
        )
        msg.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        buttons = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(46))

        cancel = Button(
            text="Cancelar",
            background_normal="",
            background_color=(0.55, 0.58, 0.63, 1),
            color=WHITE,
            bold=True,
        )

        accept = Button(
            text="Eliminar",
            background_normal="",
            background_color=DANGER,
            color=WHITE,
            bold=True,
        )

        buttons.add_widget(cancel)
        buttons.add_widget(accept)
        content.add_widget(msg)
        content.add_widget(buttons)

        popup = Popup(
            title="Eliminar cliente",
            content=content,
            size_hint=(0.88, None),
            height=dp(240),
            auto_dismiss=False,
        )

        cancel.bind(on_release=popup.dismiss)

        def do_delete(*_):
            popup.dismiss()
            delete_client_db(self.cliente.get("id"))
            refresh_financial_state()
            self.app_ref.selected_client = None
            make_popup(
                "Cliente eliminado",
                "El cliente fue eliminado correctamente.\n"
                "El resumen del dia fue recalculado."
            )
            Clock.schedule_once(lambda *_: self.app_ref.go("clientes", remember=False), 0.5)

        accept.bind(on_release=do_delete)
        popup.open()


# ============================================================
# PANTALLA: COBRO
# ============================================================

class CuotaScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="cuota", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.cliente = self.app_ref.selected_client

        if not self.cliente:
            self.app_ref.go("clientes", remember=False)
            return

        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Cuota Cliente / Ingreso Cuota", show_back=True, on_back=lambda: self.app_ref.safe_back()))

        scroll = ScrollView()
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(12), dp(12), dp(20)],
            spacing=dp(12),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        summary = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(158))
        summary.add_widget(Label(
            text=self.cliente.get("nombre", "").lower(),
            color=TEXT,
            bold=True,
            font_size="18sp",
            halign="left",
            size_hint_y=None,
            height=dp(28),
        ))
        summary.add_widget(Label(
            text=f"Telefono: {self.cliente.get('telefono', '')}",
            color=MUTED,
            font_size="13sp",
            halign="left",
            size_hint_y=None,
            height=dp(24),
        ))
        summary.add_widget(Label(
            text=f"Pagadas: {self.cliente.get('pagadas', 0)} | Pendientes: {self.cliente.get('pendientes', 0)}",
            color=MUTED,
            font_size="13sp",
            halign="left",
            size_hint_y=None,
            height=dp(24),
        ))
        summary.add_widget(Label(
            text=f"Saldo actual: [b]{money(self.cliente.get('saldo', 0))}[/b] | Estado: [b]{estado_texto(self.cliente)}[/b]",
            markup=True,
            color=TEXT,
            font_size="14sp",
            halign="left",
            size_hint_y=None,
            height=dp(28),
        ))
        summary.add_widget(Label(
            text=f"Frecuencia: {self.cliente.get('frecuencia_cobro', 'Diario')} | Proximo cobro: {format_date_for_user(self.cliente.get('fecha_proximo_cobro', ''))}",
            color=MUTED,
            font_size="12sp",
            halign="left",
            size_hint_y=None,
            height=dp(24),
        ))
        content.add_widget(summary)

        action_box = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(132))
        action_box.add_widget(FieldLabel("Tipo de transaccion"))

        row = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(44))
        self.tipo_buttons = []

        tipos = ["Cuota", "Aporte", "No Pago", "Siguiente Dia"]

        for index, tipo in enumerate(tipos):
            button = ToggleButton(
                text=tipo,
                group="tipo_cuota",
                state="down" if index == 0 else "normal",
                background_normal="",
                background_color=GOLD if index == 0 else (0.88, 0.90, 0.94, 1),
                color=DARK,
                font_size="10sp",
                bold=True,
            )
            button.bind(on_release=self.update_tipo_colors)
            self.tipo_buttons.append(button)
            row.add_widget(button)

        action_box.add_widget(row)

        warning = self.get_warning_text()
        self.warning_label = Label(
            text=warning,
            color=DANGER if get_estado_cliente(self.cliente) in ["pagado", "aporte", "no_pago"] else MUTED,
            font_size="11sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(30),
        )
        self.warning_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))
        action_box.add_widget(self.warning_label)

        self.apply_payment_rules()

        content.add_widget(action_box)

        form = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(350))
        grid = GridLayout(cols=2, spacing=dp(10), size_hint_y=None, height=dp(258))

        self.valor_cuota = AutoMoneyInput(text=format_miles(self.cliente.get("cuota", 0)))
        self.saldo_actual = AutoMoneyInput(text=format_miles(self.cliente.get("saldo", 0)))
        self.valor_pagar = AutoMoneyInput(text=format_miles(self.cliente.get("cuota", 0)))
        self.numero_cuotas = AutoNumberInput(text="1")
        self.nuevo_saldo = AutoMoneyInput(text=format_miles(max(self.cliente.get("saldo", 0) - self.cliente.get("cuota", 0), 0)))
        self.metodo_pago = Spinner(
            text="Efectivo",
            values=["Efectivo", "Transferencia"],
            size_hint_y=None,
            height=dp(44),
            background_normal="",
            background_color=WHITE,
            color=TEXT,
        )

        fields = [
            ("Valor Cuota", self.valor_cuota),
            ("Saldo Actual", self.saldo_actual),
            ("Valor a Pagar", self.valor_pagar),
            ("No. Cuotas", self.numero_cuotas),
            ("Nuevo Saldo", self.nuevo_saldo),
            ("Metodo Pago", self.metodo_pago),
        ]

        for label, widget in fields:
            box = BoxLayout(orientation="vertical", spacing=dp(3))
            box.add_widget(FieldLabel(label))
            box.add_widget(widget)
            grid.add_widget(box)

        self.valor_pagar.bind(text=lambda *_: self.recalculate_balance())

        form.add_widget(grid)

        registrar = SmallButton("Registrar Transaccion", bg_color=BLUE)
        registrar.bind(on_release=lambda *_: self.register_transaction())
        form.add_widget(registrar)

        content.add_widget(form)
        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def get_warning_text(self):
        estado = get_estado_cliente(self.cliente)

        if not is_client_due(self.cliente):
            return f"No corresponde cobrar hasta {format_date_for_user(self.cliente.get('fecha_proximo_cobro', ''))}. Solo aporte voluntario."

        if estado in ["pagado", "aporte"]:
            return "Cliente en verde. No se permite otra cuota; solo aporte."

        if estado == "no_pago":
            return "Cliente en rojo. Si entrega dinero, registre aporte."

        return "Seleccione el resultado del cobro."

    def apply_payment_rules(self):
        estado = get_estado_cliente(self.cliente)

        if not is_client_due(self.cliente):
            for button in self.tipo_buttons:
                if button.text == "Aporte":
                    button.disabled = False
                    button.state = "down"
                    button.background_color = GOLD
                else:
                    button.disabled = True
                    button.state = "normal"
                    button.background_color = (0.75, 0.75, 0.78, 1)
            return

        if estado in ["pagado", "aporte"]:
            for button in self.tipo_buttons:
                if button.text == "Aporte":
                    button.disabled = False
                    button.state = "down"
                    button.background_color = GOLD
                else:
                    button.disabled = True
                    button.state = "normal"
                    button.background_color = (0.75, 0.75, 0.78, 1)

        elif estado == "no_pago":
            for button in self.tipo_buttons:
                if button.text == "Cuota":
                    button.disabled = True
                    button.state = "normal"
                    button.background_color = (0.75, 0.75, 0.78, 1)
                elif button.text == "Aporte":
                    button.disabled = False
                    button.state = "down"
                    button.background_color = GOLD
                else:
                    button.disabled = False

    def update_tipo_colors(self, *_):
        for button in self.tipo_buttons:
            if button.disabled:
                continue
            button.background_color = GOLD if button.state == "down" else (0.88, 0.90, 0.94, 1)

    def recalculate_balance(self):
        saldo = parse_money_value(self.saldo_actual.text)
        pago = parse_money_value(self.valor_pagar.text)
        self.nuevo_saldo.text = format_miles(max(saldo - pago, 0))

    def get_selected_tipo(self):
        for button in self.tipo_buttons:
            if button.state == "down":
                return button.text
        return "Cuota"

    def register_transaction(self):
        tipo = self.get_selected_tipo()
        pago = parse_money_value(self.valor_pagar.text)
        estado_actual = get_estado_cliente(self.cliente)

        if estado_actual in ["pagado", "aporte"] and tipo != "Aporte":
            make_popup("Cobro bloqueado", "Este cliente ya pago. Solo se permite registrar aporte.")
            return

        if estado_actual == "no_pago" and tipo == "Cuota":
            make_popup("Cobro bloqueado", "Este cliente esta en no pago. Si entrega dinero, registre aporte.")
            return

        nuevo_saldo = max(int(self.cliente.get("saldo", 0)) - pago, 0)
        frecuencia = self.cliente.get("frecuencia_cobro", "Diario")
        proximo_cobro = next_due_date(frecuencia)

        if tipo == "Cuota":
            self.cliente["saldo"] = nuevo_saldo
            self.cliente["pagadas"] = int(self.cliente.get("pagadas", 0)) + 1
            self.cliente["pendientes"] = max(int(self.cliente.get("pendientes", 0)) - 1, 0)
            self.cliente["estado"] = "pagado"
            self.cliente["fecha_proximo_cobro"] = proximo_cobro
            self.cliente["ultimo_tipo"] = f"Cuota pagada. Proximo cobro: {format_date_for_user(proximo_cobro)}"

        elif tipo == "Aporte":
            self.cliente["saldo"] = nuevo_saldo
            self.cliente["estado"] = "aporte"
            self.cliente["fecha_proximo_cobro"] = proximo_cobro
            self.cliente["ultimo_tipo"] = f"Aporte. Proximo cobro: {format_date_for_user(proximo_cobro)}"

        elif tipo == "No Pago":
            pago = 0
            self.cliente["estado"] = "no_pago"
            self.cliente["fecha_proximo_cobro"] = proximo_cobro
            self.cliente["ultimo_tipo"] = f"No pago. Proximo intento: {format_date_for_user(proximo_cobro)}"

        elif tipo == "Siguiente Dia":
            pago = 0
            self.cliente["estado"] = "siguiente"
            self.cliente["fecha_proximo_cobro"] = proximo_cobro
            self.cliente["ultimo_tipo"] = f"Siguiente cobro: {format_date_for_user(proximo_cobro)}"

        transaccion = {
            "cliente_id": self.cliente.get("id"),
            "cliente": self.cliente.get("nombre", ""),
            "tipo": tipo,
            "valor": pago,
            "metodo": self.metodo_pago.text,
            "fecha": today_iso(),
            "synced": 0,
        }

        update_client_in_db(self.cliente)
        insert_transaction_db(transaccion)
        refresh_memory_from_db()

        updated = get_client_by_id(self.cliente.get("id"))
        if updated:
            self.app_ref.selected_client = updated

        make_popup("Transaccion registrada", f"{tipo} registrado correctamente.")
        Clock.schedule_once(lambda *_: self.app_ref.go("gestion_cliente", remember=False), 0.6)


# ============================================================
# PANTALLA: NUEVO CLIENTE
# ============================================================

class NuevoClienteScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="nuevo_cliente", **kwargs)
        self.current_step = 1
        self.form_data = {}

        root = BoxLayout(orientation="vertical")
        root.add_widget(Header("Registro de Nuevo Cliente"))

        self.main_area = BoxLayout(orientation="vertical")
        root.add_widget(self.main_area)

        self.nav_container = BoxLayout(size_hint_y=None, height=dp(76))
        root.add_widget(self.nav_container)

        self.add_widget(root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.current_step = 1
        self.form_data = self.empty_form_data()

        self.nav_container.clear_widgets()
        self.nav_container.add_widget(BottomNav(self.app_ref, active="nuevo"))

        self.render_step()

    def empty_form_data(self):
        return {
            "documento": "",
            "nombre": "",
            "movil": "",
            "direccion": "",
            "documento_codeudor": "",
            "nombre_codeudor": "",
            "movil_codeudor": "",
            "valor_prestar": "",
            "interes": "",
            "numero_cuotas": "",
            "frecuencia": "Diario",
            "total_pagar": "0",
            "valor_cuota": "0",
            "valor_seguro": "",
            "beneficiario": "",
            "obs_seguro": "",
        }

    def save_current_step_values(self):
        if not hasattr(self, "active_inputs"):
            return

        for key, widget in self.active_inputs.items():
            self.form_data[key] = widget.text

    def calculate_credit_values(self):
        valor = parse_money_value(self.form_data.get("valor_prestar", ""))
        interes = parse_percent_value(self.form_data.get("interes", ""))

        try:
            cuotas = int(float(str(self.form_data.get("numero_cuotas", "")).replace(",", ".")))
        except Exception:
            cuotas = 0

        if valor <= 0 or cuotas <= 0:
            self.form_data["total_pagar"] = "0"
            self.form_data["valor_cuota"] = "0"
            return {"valor": valor, "interes": interes, "cuotas": cuotas, "total_interes": 0, "total": 0, "cuota": 0}

        total_interes = round(valor * (interes / 100))
        total = valor + total_interes
        cuota = round(total / cuotas)

        self.form_data["total_pagar"] = format_miles(total)
        self.form_data["valor_cuota"] = format_miles(cuota)

        return {"valor": valor, "interes": interes, "cuotas": cuotas, "total_interes": total_interes, "total": total, "cuota": cuota}

    def live_credit_update(self, *_):
        if not hasattr(self, "active_inputs"):
            return

        for key, widget in self.active_inputs.items():
            self.form_data[key] = widget.text

        calc = self.calculate_credit_values()

        if "total_pagar" in self.active_inputs:
            self.active_inputs["total_pagar"].text = self.form_data["total_pagar"]

        if "valor_cuota" in self.active_inputs:
            self.active_inputs["valor_cuota"].text = self.form_data["valor_cuota"]

        if hasattr(self, "resumen_credito_label"):
            disponible = calculate_cash_balance()
            estado_caja = "Disponible" if calc["valor"] <= disponible else "Fondos insuficientes"

            self.resumen_credito_label.text = (
                f"Saldo disponible en caja: {money(disponible)}\n"
                f"Valor a prestar: {money(calc['valor'])}\n"
                f"Estado de caja: {estado_caja}\n"
                f"Interes aplicado: {calc['interes']:.2f}% = {money(calc['total_interes'])}\n"
                f"Total a pagar: {money(calc['total'])}\n"
                f"Valor cuota: {money(calc['cuota'])}"
            )

    def step_header(self, title, subtitle):
        wrapper = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(96),
            padding=[dp(12), dp(10), dp(12), dp(6)],
            spacing=dp(6),
        )

        progress = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(32), spacing=dp(6))

        labels = ["1 Cliente", "2 Codeudor", "3 Credito", "4 Seguro"]

        for index, label in enumerate(labels, start=1):
            active = index == self.current_step
            done = index < self.current_step

            item = Label(
                text=label,
                color=WHITE if active else TEXT,
                bold=active or done,
                font_size="10sp",
                halign="center",
                valign="middle",
            )

            with item.canvas.before:
                Color(*(BLUE if active else (GOLD if done else (0.88, 0.90, 0.94, 1))))
                item.bg = RoundedRectangle(pos=item.pos, size=item.size, radius=[dp(12)])

            item.bind(pos=lambda widget, *_: setattr(widget.bg, "pos", widget.pos))
            item.bind(size=lambda widget, *_: setattr(widget.bg, "size", widget.size))

            progress.add_widget(item)

        title_label = Label(
            text=title,
            color=TEXT,
            bold=True,
            font_size="17sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(28),
        )
        title_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        subtitle_label = Label(
            text=subtitle,
            color=MUTED,
            font_size="12sp",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(22),
        )
        subtitle_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        wrapper.add_widget(progress)
        wrapper.add_widget(title_label)
        wrapper.add_widget(subtitle_label)

        return wrapper

    def field_box(self, label, widget, multiline=False):
        box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(76) if not multiline else dp(124),
            spacing=dp(5),
        )
        box.add_widget(FieldLabel(label))
        box.add_widget(widget)
        return box

    def make_card(self, widgets):
        height = dp(28)
        for widget in widgets:
            height += widget.height + dp(8)

        card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=height,
            padding=[dp(14), dp(14), dp(14), dp(14)],
            spacing=dp(8),
        )
        card.bg_color = WHITE

        for widget in widgets:
            card.add_widget(widget)

        return card

    def make_input(self, key, hint="", money_field=False, number_field=False, readonly=False, multiline=False):
        if money_field:
            widget = AutoMoneyInput(hint_text=hint, text=self.form_data.get(key, ""))
        elif number_field:
            widget = AutoNumberInput(hint_text=hint, text=self.form_data.get(key, ""))
        else:
            widget = AppTextInput(hint_text=hint, text=self.form_data.get(key, ""), multiline=multiline)

        widget.readonly = readonly
        self.active_inputs[key] = widget
        return widget

    def render_step(self):
        self.main_area.clear_widgets()
        self.active_inputs = {}

        scroll = ScrollView()
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(8), dp(12), dp(18)],
            spacing=dp(12),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        if self.current_step == 1:
            content.add_widget(self.step_header("Datos del cliente", "Informacion basica del cliente."))

            fields = [
                self.field_box("Documento", self.make_input("documento", "Numero de documento")),
                self.field_box("Nombre completo", self.make_input("nombre", "Nombre completo")),
                self.field_box("Movil +57", self.make_input("movil", "3000000000")),
                self.field_box("Direccion", self.make_input("direccion", "Direccion del cliente")),
            ]
            content.add_widget(self.make_card(fields))

        elif self.current_step == 2:
            content.add_widget(self.step_header("Datos del codeudor", "Informacion opcional."))

            fields = [
                self.field_box("Documento codeudor", self.make_input("documento_codeudor", "Opcional")),
                self.field_box("Nombre codeudor", self.make_input("nombre_codeudor", "Opcional")),
                self.field_box("Movil codeudor", self.make_input("movil_codeudor", "Opcional")),
            ]
            content.add_widget(self.make_card(fields))

        elif self.current_step == 3:
            calc = self.calculate_credit_values()
            content.add_widget(self.step_header("Credito en efectivo", "Total y cuota se calculan automaticamente."))

            producto = AppTextInput(text="5 - CREDITO EN EFECTIVO")
            producto.readonly = True

            frecuencia = Spinner(
                text=self.form_data.get("frecuencia", "Diario"),
                values=["Diario", "Semanal", "Quincenal", "Mensual"],
                size_hint_y=None,
                height=dp(44),
                background_normal="",
                background_color=WHITE,
                color=TEXT,
            )
            self.active_inputs["frecuencia"] = frecuencia

            valor_input = self.make_input("valor_prestar", "Ej: 500.000", money_field=True)
            interes_input = self.make_input("interes", "Ej: 20", number_field=True)
            cuotas_input = self.make_input("numero_cuotas", "Ej: 25", number_field=True)
            total_input = self.make_input("total_pagar", "0", money_field=True, readonly=True)
            cuota_input = self.make_input("valor_cuota", "0", money_field=True, readonly=True)

            valor_input.bind(text=self.live_credit_update)
            interes_input.bind(text=self.live_credit_update)
            cuotas_input.bind(text=self.live_credit_update)
            frecuencia.bind(text=self.live_credit_update)

            fields = [
                self.field_box("Producto", producto),
                self.field_box("Valor a prestar", valor_input),
                self.field_box("Interes %", interes_input),
                self.field_box("Numero de cuotas", cuotas_input),
                self.field_box("Frecuencia de cobro", frecuencia),
                self.field_box("Total a pagar", total_input),
                self.field_box("Valor de cada cuota", cuota_input),
            ]
            content.add_widget(self.make_card(fields))

            disponible = calculate_cash_balance()
            estado_caja = "Disponible" if calc["valor"] <= disponible else "Fondos insuficientes"

            resumen = Label(
                text=(
                    f"Saldo disponible en caja: {money(disponible)}\n"
                    f"Valor a prestar: {money(calc['valor'])}\n"
                    f"Estado de caja: {estado_caja}\n"
                    f"Interes aplicado: {calc['interes']:.2f}% = {money(calc['total_interes'])}\n"
                    f"Total a pagar: {money(calc['total'])}\n"
                    f"Valor cuota: {money(calc['cuota'])}"
                ),
                color=MUTED,
                font_size="12sp",
                halign="left",
                valign="top",
                size_hint_y=None,
                height=dp(112),
            )
            resumen.bind(size=lambda instance, value: setattr(instance, "text_size", value))
            self.resumen_credito_label = resumen

            resumen_card = RoundedBox(
                orientation="vertical",
                size_hint_y=None,
                height=dp(160),
                padding=[dp(12), dp(10), dp(12), dp(10)],
                spacing=dp(6),
            )
            resumen_card.bg_color = (0.98, 0.98, 1, 1)

            resumen_title = Label(
                text="Resumen matematico del credito",
                color=TEXT,
                bold=True,
                font_size="13sp",
                halign="left",
                size_hint_y=None,
                height=dp(24),
            )
            resumen_title.bind(size=lambda instance, value: setattr(instance, "text_size", value))

            resumen_card.add_widget(resumen_title)
            resumen_card.add_widget(resumen)
            content.add_widget(resumen_card)

        else:
            content.add_widget(self.step_header("Datos del seguro", "Informacion opcional."))

            fields = [
                self.field_box("Valor seguro", self.make_input("valor_seguro", "Ej: 10.000", money_field=True)),
                self.field_box("Beneficiario", self.make_input("beneficiario", "Nombre beneficiario")),
                self.field_box("Observaciones", self.make_input("obs_seguro", "Observaciones", multiline=True), multiline=True),
            ]
            content.add_widget(self.make_card(fields))

        buttons = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(48))

        back = Button(
            text="VOLVER" if self.current_step == 1 else "ATRAS",
            background_normal="",
            background_color=(0.55, 0.58, 0.63, 1),
            color=WHITE,
            bold=True,
            font_size="12sp",
        )
        back.bind(on_release=lambda *_: self.previous_step())

        if self.current_step < 4:
            next_button = Button(
                text="SIGUIENTE",
                background_normal="",
                background_color=BLUE,
                color=WHITE,
                bold=True,
                font_size="12sp",
            )
            next_button.bind(on_release=lambda *_: self.next_step())
        else:
            next_button = Button(
                text="CREAR CLIENTE",
                background_normal="",
                background_color=SUCCESS,
                color=WHITE,
                bold=True,
                font_size="12sp",
            )
            next_button.bind(on_release=lambda *_: self.create_client())

        buttons.add_widget(back)
        buttons.add_widget(next_button)
        content.add_widget(buttons)

        scroll.add_widget(content)
        self.main_area.add_widget(scroll)

    def next_step(self):
        self.save_current_step_values()

        if self.current_step == 3:
            self.calculate_credit_values()

        if self.current_step < 4:
            self.current_step += 1
            self.render_step()

    def previous_step(self):
        self.save_current_step_values()

        if self.current_step > 1:
            self.current_step -= 1
            self.render_step()
        else:
            self.app_ref.go("clientes", remember=False)

    def create_client(self):
        self.save_current_step_values()
        self.calculate_credit_values()

        nombre = self.form_data.get("nombre", "").strip().upper() or "CLIENTE NUEVO DEMO"
        movil = self.form_data.get("movil", "").strip() or "3000000000"

        valor_prestar = parse_money_value(self.form_data.get("valor_prestar", ""))
        total_pagar = parse_money_value(self.form_data.get("total_pagar", ""))
        cuota = parse_money_value(self.form_data.get("valor_cuota", ""))

        try:
            cuotas = int(float(str(self.form_data.get("numero_cuotas", "")).replace(",", ".")))
        except Exception:
            cuotas = 0

        if valor_prestar <= 0 or total_pagar <= 0 or cuota <= 0 or cuotas <= 0:
            make_popup("Datos incompletos", "Debe ingresar valor a prestar, interes y numero de cuotas.")
            self.current_step = 3
            self.render_step()
            return

        saldo_caja = calculate_cash_balance()

        if valor_prestar > saldo_caja:
            make_popup(
                "Fondos insuficientes",
                f"No se puede crear este prestamo.\n\n"
                f"Saldo disponible en caja: {money(saldo_caja)}\n"
                f"Valor solicitado: {money(valor_prestar)}\n\n"
                f"Debe ingresar mas dinero a caja o reducir el valor a prestar."
            )
            self.current_step = 3
            self.render_step()
            return

        frecuencia = self.form_data.get("frecuencia", "Diario")
        proximo_cobro = next_due_date(frecuencia)

        nuevo = {
            "id": None,
            "nombre": nombre,
            "telefono": f"+57 {movil}",
            "cuota": cuota,
            "saldo": total_pagar,
            "pagadas": 0,
            "pendientes": cuotas,
            "estado": "siguiente",
            "ultimo_tipo": f"Credito creado. Proximo cobro: {format_date_for_user(proximo_cobro)}",
            "documento": self.form_data.get("documento", "").strip(),
            "direccion": self.form_data.get("direccion", "").strip(),
            "frecuencia_cobro": frecuencia,
            "fecha_proximo_cobro": proximo_cobro,
        }

        nuevo["id"] = insert_client_db(nuevo)

        movimiento_prestamo = {
            "tipo": "Egreso",
            "concepto": "Prestamo otorgado",
            "valor": valor_prestar,
            "observaciones": f"Prestamo entregado a {nombre}",
            "fecha": today_iso(),
            "synced": 0,
        }

        insert_movement_db(movimiento_prestamo)
        refresh_financial_state()

        make_popup(
            "Cliente creado",
            f"Cliente y credito activados correctamente.\n"
            f"Valor entregado: {money(valor_prestar)}\n"
            f"Total a pagar: {money(total_pagar)}\n"
            f"Cuota: {money(cuota)}",
        )
        Clock.schedule_once(lambda *_: self.app_ref.go("clientes", remember=False), 0.6)


# ============================================================
# PANTALLA: EDITAR CLIENTE
# ============================================================

class EditarClienteScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="editar_cliente", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.cliente = self.app_ref.selected_client

        if not self.cliente:
            self.app_ref.go("clientes", remember=False)
            return

        self.build()

    def build(self):
        self.root.clear_widgets()
        self.root.add_widget(Header("Editar Cliente / Prestamo", show_back=True, on_back=lambda: self.app_ref.safe_back()))

        scroll = ScrollView()
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(12), dp(12), dp(24)],
            spacing=dp(12),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        card = RoundedBox(
            orientation="vertical",
            size_hint_y=None,
            height=dp(610),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            spacing=dp(8),
        )

        self.documento = AppTextInput(text=str(self.cliente.get("documento", "")))
        self.nombre = AppTextInput(text=str(self.cliente.get("nombre", "")))
        telefono = str(self.cliente.get("telefono", "")).replace("+57", "").strip()
        self.movil = AppTextInput(text=telefono)
        self.direccion = AppTextInput(text=str(self.cliente.get("direccion", "")))
        self.saldo = AutoMoneyInput(text=format_miles(self.cliente.get("saldo", 0)))
        self.cuota = AutoMoneyInput(text=format_miles(self.cliente.get("cuota", 0)))
        self.pendientes = AutoNumberInput(text=str(self.cliente.get("pendientes", 0)))

        fields = [
            ("Documento", self.documento),
            ("Nombre", self.nombre),
            ("Movil +57", self.movil),
            ("Direccion", self.direccion),
            ("Total a pagar / Saldo", self.saldo),
            ("Valor cuota", self.cuota),
            ("Cuotas pendientes", self.pendientes),
        ]

        for label, widget in fields:
            box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(68), spacing=dp(3))
            box.add_widget(FieldLabel(label))
            box.add_widget(widget)
            card.add_widget(box)

        save = SmallButton("Guardar Cambios", bg_color=SUCCESS)
        save.bind(on_release=lambda *_: self.save_changes())
        card.add_widget(save)

        content.add_widget(card)
        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def save_changes(self):
        saldo = parse_money_value(self.saldo.text)
        cuota = parse_money_value(self.cuota.text)

        try:
            pendientes = int(float(str(self.pendientes.text).replace(",", ".")))
        except Exception:
            pendientes = 0

        self.cliente["documento"] = self.documento.text.strip()
        self.cliente["nombre"] = self.nombre.text.strip().upper() or "SIN NOMBRE"
        self.cliente["telefono"] = f"+57 {self.movil.text.strip()}"
        self.cliente["direccion"] = self.direccion.text.strip()
        self.cliente["saldo"] = saldo
        self.cliente["cuota"] = cuota
        self.cliente["pendientes"] = pendientes
        self.cliente["ultimo_tipo"] = "Cliente actualizado"

        update_client_in_db(self.cliente)
        refresh_financial_state()

        updated = get_client_by_id(self.cliente.get("id"))
        if updated:
            self.app_ref.selected_client = updated

        make_popup(
            "Cambios guardados",
            "Cliente y prestamo actualizados correctamente.\n"
            "El resumen del dia fue recalculado."
        )
        Clock.schedule_once(lambda *_: self.app_ref.go("gestion_cliente", remember=False), 0.6)


# ============================================================
# PANTALLA: MOVIMIENTOS
# ============================================================

class MovimientosScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="movimientos", **kwargs)

        root = BoxLayout(orientation="vertical")
        root.add_widget(Header("Movimientos de Caja"))

        scroll = ScrollView()
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(14), dp(12), dp(90)],
            spacing=dp(12),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        type_card = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(104))
        type_card.add_widget(FieldLabel("Tipo de movimiento"))

        row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(46))

        self.egreso = ToggleButton(
            text="Egreso",
            group="mov",
            state="down",
            background_normal="",
            background_color=GOLD,
            color=DARK,
            bold=True,
        )
        self.ingreso = ToggleButton(
            text="Ingreso",
            group="mov",
            background_normal="",
            background_color=(0.88, 0.90, 0.94, 1),
            color=TEXT,
            bold=True,
        )

        self.egreso.bind(on_release=self.update_type)
        self.ingreso.bind(on_release=self.update_type)

        row.add_widget(self.egreso)
        row.add_widget(self.ingreso)

        type_card.add_widget(row)
        content.add_widget(type_card)

        form = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(330))

        form.add_widget(FieldLabel("Concepto"))
        self.concepto = Spinner(
            text="Seleccione concepto",
            values=["Transporte", "Alimentacion", "Papeleria", "Recaudo adicional", "Ajuste de caja", "Otro"],
            size_hint_y=None,
            height=dp(44),
            background_normal="",
            background_color=WHITE,
            color=TEXT,
        )
        form.add_widget(self.concepto)

        form.add_widget(FieldLabel("Valor"))
        self.valor = AutoMoneyInput(hint_text="Ej: 50.000")
        form.add_widget(self.valor)

        form.add_widget(FieldLabel("Observaciones"))
        self.obs = AppTextInput(hint_text="Escriba observaciones", multiline=True)
        form.add_widget(self.obs)

        save = PillButton("OK Guardar", bg_color=DARK)
        save.bind(on_release=lambda *_: self.save_movement())
        form.add_widget(save)

        content.add_widget(form)
        scroll.add_widget(content)
        root.add_widget(scroll)

        self.nav_container = BoxLayout(size_hint_y=None, height=dp(76))
        root.add_widget(self.nav_container)
        self.add_widget(root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()
        self.nav_container.clear_widgets()
        self.nav_container.add_widget(BottomNav(self.app_ref, active="caja"))

    def update_type(self, *_):
        self.egreso.background_color = GOLD if self.egreso.state == "down" else (0.88, 0.90, 0.94, 1)
        self.ingreso.background_color = GOLD if self.ingreso.state == "down" else (0.88, 0.90, 0.94, 1)

    def save_movement(self):
        tipo = "Egreso" if self.egreso.state == "down" else "Ingreso"
        valor = parse_money_value(self.valor.text)

        if valor <= 0:
            make_popup("Valor inválido", "Debe ingresar un valor mayor a cero.")
            return

        saldo_disponible = calculate_cash_balance()

        if tipo == "Egreso":
            if saldo_disponible <= 0:
                make_popup(
                    "Caja sin fondos",
                    "No se puede registrar este egreso porque el saldo en caja es cero."
                )
                return

            if valor > saldo_disponible:
                make_popup(
                    "Fondos insuficientes",
                    f"No se puede registrar el egreso.\\n\\n"
                    f"Saldo disponible en caja: {money(saldo_disponible)}\\n"
                    f"Valor del egreso: {money(valor)}\\n\\n"
                    f"Debe registrar un ingreso o reducir el gasto."
                )
                return

        movimiento = {
            "tipo": tipo,
            "concepto": self.concepto.text,
            "valor": valor,
            "observaciones": self.obs.text,
            "fecha": today_iso(),
            "synced": 0,
        }

        insert_movement_db(movimiento)
        refresh_memory_from_db()

        saldo_final = calculate_cash_balance()

        make_popup(
            "Movimiento guardado",
            f"{tipo} registrado por {money(valor)}.\\n"
            f"Saldo en caja: {money(saldo_final)}"
        )

        self.valor.text = ""
        self.obs.text = ""
        self.concepto.text = "Seleccione concepto"


# ============================================================
# PANTALLA: RESUMEN
# ============================================================

class MetricRow(BoxLayout):
    def __init__(self, left, right, highlight=False, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(38) if not highlight else dp(46),
            padding=[dp(10), 0, dp(10), 0],
            **kwargs,
        )

        bg_color = (0.98, 0.98, 1, 1) if not highlight else (1.0, 0.95, 0.78, 1)

        with self.canvas.before:
            Color(*bg_color)
            self.bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])

        self.bind(pos=self._update_bg, size=self._update_bg)

        left_label = Label(
            text=left,
            color=TEXT if highlight else MUTED,
            bold=highlight,
            font_size="12sp",
            halign="left",
            valign="middle",
        )
        left_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        right_label = Label(
            text=str(right),
            color=TEXT,
            bold=highlight,
            font_size="12sp",
            halign="right",
            valign="middle",
        )
        right_label.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        self.add_widget(left_label)
        self.add_widget(right_label)

    def _update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size


class ResumenScreen(Screen):
    sync_status = StringProperty("Pendiente")

    def __init__(self, **kwargs):
        super().__init__(name="resumen", **kwargs)
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self):
        self.app_ref = App.get_running_app()

        try:
            refresh_financial_state()
        except Exception as error:
            print("ERROR refresh resumen:", error)

        self.build()

    def build(self):
        try:
            refresh_financial_state()
        except Exception as error:
            print("ERROR build resumen refresh:", error)

        self.root.clear_widgets()
        self.root.add_widget(Header("::V12:: Resumen del Dia", show_back=True, on_back=lambda: self.app_ref.safe_back()))

        scroll = ScrollView()
        content = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(12), dp(12), dp(18)],
            spacing=dp(10),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))

        report = RoundedBox(orientation="vertical", spacing=dp(7), padding=dp(10), size_hint_y=None)
        report.bind(minimum_height=report.setter("height"))

        total_clientes = len(CLIENTES)
        clientes_nuevos = max(total_clientes - len(CLIENTES_DEMO), 0)

        transacciones_hoy = [item for item in TRANSACCIONES if is_today_record(item)]
        movimientos_hoy = [item for item in MOVIMIENTOS_CAJA if is_today_record(item)]

        pagos = len([item for item in transacciones_hoy if item.get("tipo") in ["Cuota", "Aporte"]])
        no_pagos = len([item for item in transacciones_hoy if item.get("tipo") == "No Pago"])
        aplazados = len([item for item in transacciones_hoy if item.get("tipo") in ["Siguiente Dia", "Siguiente Día"]])

        recaudo_dia = sum(item.get("valor", 0) for item in transacciones_hoy if item.get("tipo") in ["Cuota", "Aporte"])
        egresos = sum(item.get("valor", 0) for item in movimientos_hoy if item.get("tipo") == "Egreso")

        caja_inicial = CAJA_INICIAL_BASE
        recaudo_esperado = sum(
            cliente.get("cuota", 0)
            for cliente in CLIENTES
            if cliente.get("saldo", 0) > 0 and cliente.get("pendientes", 0) > 0
        )
        efectivo_transferencia = recaudo_dia
        ingresos = sum(item.get("valor", 0) for item in movimientos_hoy if item.get("tipo") == "Ingreso")
        retiros_caja = 0
        retiro_seguro = 0
        ingresos_seguro = 0
        caja_seguro = 0
        total_ventas = recaudo_dia + ingresos

        saldo_caja = calculate_cash_balance()

        try:
            pendientes_sync = count_pending_sync()
        except Exception:
            pendientes_sync = 0

        rows = [
            ("Vendedor", "CORREDOR - LUIS"),
            ("Fecha de Ruta", today_text()),
            ("Clientes Ausentes", str(no_pagos)),
            ("Aplazados Siguiente Dia", str(aplazados)),
            ("Numero Clientes", str(total_clientes)),
            ("Clientes Nuevos", str(clientes_nuevos)),
            ("Pagos Registrados", f"{pagos} / {total_clientes} Adicionales: 0"),
            ("Caja Inicial", money(caja_inicial)),
            ("Recaudo Esperado", money(recaudo_esperado)),
            ("Recaudo del dia", money(recaudo_dia)),
            ("Efectivo/Transferencia", money(efectivo_transferencia)),
            ("Total Ventas", money(total_ventas)),
            ("Retiros Caja", money(retiros_caja)),
            ("Egresos", money(egresos)),
            ("Ingresos", money(ingresos)),
            ("Retiro Caja Seguros", money(retiro_seguro)),
            ("Ingresos Seguros", money(ingresos_seguro)),
            ("Caja Seguros", money(caja_seguro)),
            ("Movimientos del dia", str(len(movimientos_hoy))),
            ("Pendientes nube", str(pendientes_sync)),
            ("Sincronizacion", self.sync_status),
        ]

        for left, right in rows:
            report.add_widget(MetricRow(left, right))

        report.add_widget(MetricRow("Saldo en Caja", money(saldo_caja), highlight=True))

        content.add_widget(report)

        actions = RoundedBox(orientation="vertical", size_hint_y=None, height=dp(122), spacing=dp(8))

        row1 = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(46))
        row1.add_widget(PillButton("No Pagos", bg_color=DARK))
        row1.add_widget(PillButton("Config.", bg_color=DARK))

        row2 = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(46))
        row2.add_widget(PillButton("Reaj.", bg_color=DARK))

        cloud = PillButton("SYNC Carga", bg_color=BLUE)
        cloud.bind(on_release=lambda *_: self.simulate_cloud_upload())
        row2.add_widget(cloud)

        actions.add_widget(row1)
        actions.add_widget(row2)

        content.add_widget(actions)
        scroll.add_widget(content)
        self.root.add_widget(scroll)

    def simulate_cloud_upload(self):
        self.sync_status = "Enviando datos..."
        self.build()

        def complete_sync(*_):
            mark_all_as_synced()
            refresh_memory_from_db()
            self.sync_status = "Sincronizado correctamente"
            self.build()
            make_popup("Carga completa", "Los datos fueron enviados a la nube correctamente.")

        Clock.schedule_once(complete_sync, 1.2)


# ============================================================
# APP PRINCIPAL
# ============================================================

class CobrosV12App(App):
    selected_client = None

    def build(self):
        self.title = "Cobros V12 Mobile"
        self.nav_stack = []
        self.selected_client = None

        try:
            init_database()
            ensure_client_schedule_columns()
            seed_database_if_empty()
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

        self.sm = ScreenManager(
            transition=NoTransition(),
            size_hint=size_hint,
            width=width,
        )

        self.sm.add_widget(ClientesScreen())
        self.sm.add_widget(GestionClienteScreen())
        self.sm.add_widget(CuotaScreen())
        self.sm.add_widget(NuevoClienteScreen())
        self.sm.add_widget(EditarClienteScreen())
        self.sm.add_widget(MovimientosScreen())
        self.sm.add_widget(ResumenScreen())

        self.shell.add_widget(self.sm)

        Window.bind(size=self.update_mobile_width)
        Window.bind(on_keyboard=self.on_keyboard)

        return self.shell

    def update_mobile_width(self, *_):
        if hasattr(self, "sm") and platform not in ("android", "ios"):
            self.sm.width = min(Window.width, dp(430))

    def on_start(self):
        print("Cobros V12 iniciado correctamente.")
        print("Base de datos:", get_db_path())

    def on_keyboard(self, window, key, scancode, codepoint, modifier):
        if key != 27:
            return False

        self.safe_back()
        return True

    def go(self, screen_name, remember=True):
        valid_routes = {
            "clientes",
            "gestion_cliente",
            "cuota",
            "nuevo_cliente",
            "editar_cliente",
            "movimientos",
            "resumen",
        }

        if screen_name not in valid_routes:
            screen_name = "clientes"

        if not hasattr(self, "sm"):
            return

        current = self.sm.current

        if current == screen_name:
            return

        if remember and current:
            if not self.nav_stack or self.nav_stack[-1] != current:
                self.nav_stack.append(current)
            self.nav_stack = self.nav_stack[-20:]

        self.sm.current = screen_name

    def safe_back(self):
        if not hasattr(self, "sm"):
            return

        current = self.sm.current

        if current == "clientes":
            return

        if current == "nuevo_cliente":
            screen = self.sm.get_screen("nuevo_cliente")
            if getattr(screen, "current_step", 1) > 1:
                screen.previous_step()
            else:
                self.go("clientes", remember=False)
            return

        if current in ["gestion_cliente", "movimientos", "resumen"]:
            self.go("clientes", remember=False)
            return

        if current in ["cuota", "editar_cliente"]:
            if self.selected_client:
                self.go("gestion_cliente", remember=False)
            else:
                self.go("clientes", remember=False)
            return

        self.go("clientes", remember=False)

    def confirm_exit(self):
        content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))

        message = Label(
            text="Desea salir de la aplicacion?",
            color=TEXT,
            font_size="15sp",
            halign="center",
            valign="middle",
        )
        message.bind(size=lambda instance, value: setattr(instance, "text_size", value))

        buttons = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(46))

        cancel = Button(
            text="Cancelar",
            background_normal="",
            background_color=(0.55, 0.58, 0.63, 1),
            color=WHITE,
            bold=True,
        )

        accept = Button(
            text="Salir",
            background_normal="",
            background_color=DANGER,
            color=WHITE,
            bold=True,
        )

        buttons.add_widget(cancel)
        buttons.add_widget(accept)

        content.add_widget(message)
        content.add_widget(buttons)

        popup = Popup(
            title="Salir",
            content=content,
            size_hint=(0.86, None),
            height=dp(220),
            auto_dismiss=False,
        )

        cancel.bind(on_release=popup.dismiss)

        def do_exit(*_):
            popup.dismiss()
            self.stop()

        accept.bind(on_release=do_exit)
        popup.open()


if __name__ == "__main__":
    CobrosV12App().run()
