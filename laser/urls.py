from django.urls import path
from . import views

urlpatterns = [
    path('',                              views.index,             name='index'),
    path('api/images/',                   views.api_images,        name='api_images'),
    path('api/preview/',                  views.api_preview,       name='api_preview'),
    path('api/engrave/',                  views.api_engrave,       name='api_engrave'),
    path('api/engrave-layout/',           views.api_engrave_layout,name='api_engrave_layout'),
    path('api/stop/',                     views.api_stop,          name='api_stop'),
    path('api/status/',                   views.api_status,        name='api_status'),
    path('api/stream/',                   views.api_stream,        name='api_stream'),
    path('api/upload/',                   views.api_upload,        name='api_upload'),
    # Calibration
    path('api/calibrate/',               views.api_calibrate,     name='api_calibrate'),
    path('api/resume-recal/',            views.api_resume_recal,  name='api_resume_recal'),
    path('api/recal-log/',               views.api_recal_log,     name='api_recal_log'),
    # G-code files
    path('api/save-gcode/',              views.api_save_gcode,    name='api_save_gcode'),
    path('api/gcode-list/',              views.api_gcode_list,    name='api_gcode_list'),
    path('gcode/<str:filename>',         views.gcode_view,        name='gcode_view'),
    path('gcode/<str:filename>/download',views.gcode_download,    name='gcode_download'),
    # Media
    path('media-img/<str:name>',         views.media_img,         name='media_img'),
]
