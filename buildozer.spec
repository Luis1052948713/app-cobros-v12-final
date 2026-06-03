[app]
title = Cobros V12 Mobile
package.name = cobrosv12
package.domain = org.techstream
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,db,ttf
version = 1.0
requirements = python3,kivy==2.3.1
orientation = portrait
fullscreen = 0

# Entry point
# Buildozer will use main.py automatically

# Android
android.api = 34
android.minapi = 24
android.sdk = 34
android.ndk = 25b
android.accept_sdk_license = True
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE

# App icon (optional)
# icon.filename = assets/icon.png

# Keep local database if bundled/created
presplash.filename =
icon.filename = assets/icon.png

[buildozer]
log_level = 2
warn_on_root = 1
