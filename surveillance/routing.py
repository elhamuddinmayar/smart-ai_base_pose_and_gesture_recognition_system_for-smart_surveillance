from django.urls import re_path
from surveillance import consumers as surveillance_consumers
from camera import consumers as camera_consumers


""" 
1:from django.urls import re_path: This imports the re_path function from the django.urls module, which is used to define URL patterns for WebSocket connections.
2:from surveillance import consumers as surveillance_consumers: This imports the consumers module from the surveillance app and aliases it as surveillance_consumers. This module likely contains the WebSocket consumer classes for handling pose-related WebSocket connections.
3:from camera import consumers as camera_consumers: This imports the consumers module from the camera app and aliases it as camera_consumers. This module likely contains the WebSocket consumer classes for handling camera-related WebSocket connections.
"""


# Define WebSocket URL patterns for the surveillance application
websocket_urlpatterns = [
    # r'ws/pose/$': This is a regular expression that matches the WebSocket URL for pose-related connections. The $ at the end indicates the end of the URL.
    re_path(r'ws/pose/$',   surveillance_consumers.PoseConsumer.as_asgi()),
    re_path(r'ws/camera/$', camera_consumers.CameraConsumer.as_asgi()),
]