[app]

# ------------------------------------------------------------
# INFORMACIÓN GENERAL
# ------------------------------------------------------------

title = Cobros V12 Mobile

package.name = cobrosv12
package.domain = org.techstream

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,db,ttf,json

version = 1.0.1

# ------------------------------------------------------------
# DEPENDENCIAS
# ------------------------------------------------------------

requirements = python3,kivy==2.3.1,plyer,certifi,pyjnius

# ------------------------------------------------------------
# INTERFAZ
# ------------------------------------------------------------

orientation = portrait
fullscreen = 0

# ------------------------------------------------------------
# RECURSOS
# ------------------------------------------------------------

icon.filename = assets/icon.png

# Puedes dejarlo vacío si no tienes presplash.
presplash.filename =

# ------------------------------------------------------------
# ANDROID
# ------------------------------------------------------------

android.api = 34
android.minapi = 24
android.sdk = 34
android.ndk = 25b

android.accept_sdk_license = True

# La app trabaja con Supabase y notificaciones.
# Los PDF se publican mediante MediaStore, por lo que no se necesitan
# permisos antiguos de lectura o escritura del almacenamiento.
android.permissions = INTERNET,POST_NOTIFICATIONS

# Arquitecturas recomendadas.
# arm64-v8a cubre la mayoría de celulares actuales.
# armeabi-v7a permite instalar también en algunos equipos antiguos.
android.archs = arm64-v8a,armeabi-v7a

# Permite conservar correctamente archivos internos y SQLite.
android.private_storage = True

# Evita que Android haga copias automáticas inconsistentes de SQLite.
android.allow_backup = False

# ------------------------------------------------------------
# LOGS Y COMPILACIÓN
# ------------------------------------------------------------

[buildozer]

log_level = 2
warn_on_root = 1
