from django.utils import timezone

def build_estudio_snapshot(estudio):
    """
    Snapshot FINAL, único y autocontenido del estudio.
    Es la ÚNICA fuente de verdad para el PDF.
    No depende de vistas ni de cálculos posteriores.
    """

    datos = estudio.datos or {}

    snapshot = {
        "meta": {
            "estudio_id": estudio.id,
            "fecha_snapshot": timezone.now().isoformat(),
        },

        "inmueble": {
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
            "beneficio_bruto": datos.get("beneficio_estimado"),
            "roi": datos.get("roi_estimado"),
            "nivel_riesgo": datos.get("nivel_riesgo"),
        },

        "inversor": {
            "inversion_total": datos.get("valor_adquisicion"),
            "comision_pct": datos.get("comision_inversure_pct"),
            "comision_eur": datos.get("comision_inversure"),
            "beneficio_neto": datos.get("beneficio_neto"),
            "roi_neto": datos.get("roi_neto"),
        },

        "comite": {
            "recomendacion": datos.get("recomendacion_comite"),
            "observaciones": datos.get("observaciones_comite"),
        },

        "kpis": {
            "ratio_euro_beneficio": datos.get("ratio_euro_beneficio"),
            "colchon_seguridad": datos.get("colchon_seguridad"),
            "precio_breakeven": datos.get("precio_breakeven"),
        }
    }

    return snapshot
