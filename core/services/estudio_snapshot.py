from django.utils import timezone

def build_estudio_snapshot(estudio):
    """
    Snapshot defensivo e inmutable del estudio.
    Consolida datos sin acceder a atributos inexistentes.
    """

    datos = estudio.datos or {}

    return {
        "tecnico": {
            "nombre_proyecto": getattr(estudio, "nombre", None),
            "direccion": getattr(estudio, "direccion", None),
            "ref_catastral": getattr(estudio, "ref_catastral", None),
            "valor_referencia": getattr(estudio, "valor_referencia", None),
            "tipologia": datos.get("tipologia"),
            "superficie_m2": datos.get("superficie_m2"),
            "estado": datos.get("estado"),
            "situacion": datos.get("situacion"),
        },
        "economico": {
            "valor_adquisicion": datos.get("valor_adquisicion"),
            "valor_transmision": datos.get("valor_transmision"),
            "beneficio_estimado": datos.get("beneficio_estimado"),
            "roi_estimado": datos.get("roi_estimado"),
            "nivel_riesgo": datos.get("nivel_riesgo"),
        },
        "kpis": {
            "ratio_euro_beneficio": datos.get("ratio_euro_beneficio"),
            "colchon_seguridad": datos.get("colchon_seguridad"),
            "precio_breakeven": datos.get("precio_breakeven"),
        },
        "comite": {
            "recomendacion": datos.get("recomendacion_comite"),
            "observaciones": datos.get("observaciones_comite"),
        },
        "meta": {
            "estudio_id": estudio.id,
            "fecha_snapshot": timezone.now().isoformat(),
        }
    }