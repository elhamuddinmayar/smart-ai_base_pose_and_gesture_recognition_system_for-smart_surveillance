from django.apps import AppConfig
import sys
import os


"""
1:from django.apps import AppConfig is used to define the configuration for the 'surveillance' app. The SurveillanceConfig class inherits from AppConfig and specifies the default auto field type and the name of the app. The ready method is overridden to perform initialization tasks when the app is ready.
2:import sys and os are imported to handle command-line arguments and interact with the operating system, respectively. The ready method checks for specific management commands (like 'migrate', 'makemigrations', etc.) and skips the engine import if any of those commands are present, preventing unnecessary initialization during certain operations. If the engine import fails, it catches the exception and prints a warning message.
"""

class SurveillanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'surveillance'
    
    # The ready() method is called when the app is fully loaded. It checks for specific management commands and imports the engine module if none of those commands are present. This ensures that the shared frame buffer is initialized before any HTTP request is processed, while avoiding unnecessary initialization during certain management operations.
    def ready(self):
        ignored_cmds = [
            'migrate', 'makemigrations', 'shell', 'test',
            'collectstatic', 'createsuperuser',
        ]
        if any(cmd in sys.argv for cmd in ignored_cmds):
            return

        try:
            from surveillance import engine  # noqa: F401
        except Exception as e:
            print(f"[SurveillanceApp] Engine import warning: {e}")