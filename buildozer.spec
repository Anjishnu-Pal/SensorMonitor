[app]
title = SensorMonitor
package.name = sensormonitor
package.domain = com.sensormonitor

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,java

version = 1.09

requirements = python3,kivy,pyjnius

orientations = portrait,landscape
fullscreen = 0

# NFC Permissions for NHS 3152 communication
android.permissions = INTERNET,NFC,ACCESS_FINE_LOCATION,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,ACCESS_MEDIA_LOCATION

# Add Java source for SensorBridge and native C code for JNI
android.add_src = android_jni,native_sensor

# JNI setup
android.ndk = 25b
android.api = 33
android.minapi = 21

# NFC intent filter for automatic tag dispatch
android.manifest.intent_filters = nfc_intent_filter.xml

# Services
p4a.bootstrap = sdl2

# Skip cython compilation
android.archs = arm64-v8a

# Enable logcat output for NFC debugging
android.logcat_filters = *:S SensorBridge:V NHS3152_Native:V python:V

[buildozer]
log_level = 2
warn_on_root = 1
