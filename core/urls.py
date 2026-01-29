from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    # Home
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("checklist/pendientes/", views.checklist_pendientes, name="checklist_pendientes"),

    # Simulador / Estudios
    path("simulador/", views.simulador, name="simulador"),
    path("guardar-estudio/", views.guardar_estudio, name="guardar_estudio"),

    # PDF estudio
    path("estudios/pdf/<int:estudio_id>/", views.pdf_estudio_preview, name="pdf_estudio_preview"),
    path("proyectos/<int:proyecto_id>/memoria/pdf/", views.pdf_memoria_economica, name="pdf_memoria_economica"),

    # Estudios
    path("estudios/nuevo/", views.nuevo_estudio, name="nuevo_estudio"),
    path("estudios/", views.lista_estudio, name="lista_estudio"),
    path("estudios/borrar/<int:estudio_id>/", views.borrar_estudio, name="borrar_estudio"),

    # Conversión a proyecto
    path("convertir-a-proyecto/<int:estudio_id>/", views.convertir_a_proyecto, name="convertir_a_proyecto"),

    # Proyectos
    path("proyectos/", views.lista_proyectos, name="lista_proyectos"),
    path("proyectos/cerrados/", views.lista_proyectos_cerrados, name="lista_proyectos_cerrados"),
    # Detalle de proyecto (si existe en views)
    path("proyectos/<int:proyecto_id>/", views.proyecto, name="proyecto"),

    # Autosave / guardado de proyecto (POST)
    path("proyectos/<int:proyecto_id>/guardar/", views.guardar_proyecto, name="guardar_proyecto"),

    # Memoria económica (gastos / ingresos)
    path("proyectos/<int:proyecto_id>/gastos/", views.proyecto_gastos, name="proyecto_gastos"),
    path("proyectos/<int:proyecto_id>/gastos/<int:gasto_id>/", views.proyecto_gasto_detalle, name="proyecto_gasto_detalle"),
    path("proyectos/<int:proyecto_id>/gastos/<int:gasto_id>/factura/", views.proyecto_gasto_factura, name="proyecto_gasto_factura"),
    path("proyectos/<int:proyecto_id>/ingresos/", views.proyecto_ingresos, name="proyecto_ingresos"),
    path("proyectos/<int:proyecto_id>/ingresos/<int:ingreso_id>/", views.proyecto_ingreso_detalle, name="proyecto_ingreso_detalle"),
    path("proyectos/<int:proyecto_id>/documentos/", views.proyecto_documentos, name="proyecto_documentos"),
    path(
        "proyectos/<int:proyecto_id>/documentos/ficha-catastral/",
        views.proyecto_documento_ficha_catastral,
        name="proyecto_documento_ficha_catastral",
    ),
    path("proyectos/<int:proyecto_id>/documentos/<int:documento_id>/borrar/", views.proyecto_documento_borrar, name="proyecto_documento_borrar"),
    path("proyectos/<int:proyecto_id>/documentos/<int:documento_id>/principal/", views.proyecto_documento_principal, name="proyecto_documento_principal"),
    path("proyectos/<int:proyecto_id>/documentos/<int:documento_id>/flag/", views.proyecto_documento_flag, name="proyecto_documento_flag"),
    path("proyectos/<int:proyecto_id>/presentacion/", views.proyecto_presentacion_generar, name="proyecto_presentacion_generar"),
    path("proyectos/<int:proyecto_id>/presentacion/preview/<str:formato>/", views.proyecto_presentacion_preview, name="proyecto_presentacion_preview"),
    path("proyectos/<int:proyecto_id>/checklist/", views.proyecto_checklist, name="proyecto_checklist"),
    path("proyectos/<int:proyecto_id>/checklist/<int:item_id>/", views.proyecto_checklist_detalle, name="proyecto_checklist_detalle"),
    path("proyectos/<int:proyecto_id>/participaciones/", views.proyecto_participaciones, name="proyecto_participaciones"),
    path("proyectos/<int:proyecto_id>/participaciones/<int:participacion_id>/", views.proyecto_participacion_detalle, name="proyecto_participacion_detalle"),

    # Clientes
    path("clientes/", views.clientes, name="clientes"),
    path("clientes/nuevo/", views.clientes_form, name="clientes_form"),
    path("clientes/editar/<int:cliente_id>/", views.cliente_edit, name="cliente_edit"),
    path("clientes/importar/", views.clientes_import, name="clientes_import"),
    path("clientes/<int:cliente_id>/inversor/", views.cliente_inversor_link, name="cliente_inversor_link"),
    path("inversores/buscar/", views.inversor_buscar, name="inversor_buscar"),
    path("inversores/", views.inversores_list, name="inversores_list"),
    path("inversores/<int:perfil_id>/portal/", views.inversor_portal_admin, name="inversor_portal_admin"),
    path(
        "inversores/<int:perfil_id>/portal/config/",
        views.inversor_portal_config,
        name="inversor_portal_config",
    ),
    path("inversores/<int:perfil_id>/documentos/", views.inversor_documento_upload, name="inversor_documento_upload"),
    path(
        "inversores/<int:perfil_id>/documentos/<int:doc_id>/borrar/",
        views.inversor_documento_borrar,
        name="inversor_documento_borrar",
    ),
    path(
        "inversores/<int:perfil_id>/comunicaciones/preview/",
        views.inversor_comunicacion_preview,
        name="inversor_comunicacion_preview",
    ),
    path(
        "inversores/<int:perfil_id>/comunicaciones/send/",
        views.inversor_comunicacion_send,
        name="inversor_comunicacion_send",
    ),

    # Portal inversor (token)
    path("inversor/sw.js", views.inversor_service_worker, name="inversor_service_worker"),
    path("inversor/<str:token>/manifest.json", views.inversor_manifest, name="inversor_manifest"),
    path("inversor/<str:token>/push/public-key/", views.inversor_push_public_key, name="inversor_push_public_key"),
    path("inversor/<str:token>/push/subscribe/", views.inversor_push_subscribe, name="inversor_push_subscribe"),
    path("inversor/<str:token>/push/unsubscribe/", views.inversor_push_unsubscribe, name="inversor_push_unsubscribe"),
    path("inversor/<str:token>/", views.inversor_portal, name="inversor_portal"),
    path("inversor/<str:token>/solicitar/<int:proyecto_id>/", views.inversor_solicitar, name="inversor_solicitar"),
    path("inversor/<str:token>/beneficio/<int:participacion_id>/", views.inversor_beneficio_update, name="inversor_beneficio_update"),

    # Solicitudes de participación (interno)
    path("proyectos/<int:proyecto_id>/solicitudes/", views.proyecto_solicitudes, name="proyecto_solicitudes"),
    path("proyectos/<int:proyecto_id>/solicitudes/<int:solicitud_id>/", views.proyecto_solicitud_detalle, name="proyecto_solicitud_detalle"),
    path("proyectos/<int:proyecto_id>/difusion/", views.proyecto_difusion, name="proyecto_difusion"),
    path("proyectos/<int:proyecto_id>/comunicaciones/", views.proyecto_comunicaciones, name="proyecto_comunicaciones"),
]
