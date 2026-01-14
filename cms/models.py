from django.db import models
from wagtail import blocks
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.fields import StreamField
from wagtail.images import get_image_model_string
from wagtail.models import Page


class HomePage(Page):
    template = "cms/home_page.html"

    hero_tag = models.CharField(max_length=120, blank=True)
    hero_title = models.CharField(max_length=200, blank=True)
    hero_subtitle = models.CharField(max_length=320, blank=True)
    hero_cta_text = models.CharField(max_length=80, blank=True)
    hero_cta_url = models.CharField(max_length=200, blank=True)
    hero_bg_color = models.CharField(max_length=20, blank=True)
    hero_bg_image = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    hero_panel_image = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    hero_panel_title = models.CharField(max_length=120, blank=True)
    hero_panel_text = models.CharField(max_length=200, blank=True)
    hero_panel_footer = models.CharField(max_length=120, blank=True)
    meta_1_value = models.CharField(max_length=40, blank=True)
    meta_1_label = models.CharField(max_length=80, blank=True)
    meta_2_value = models.CharField(max_length=40, blank=True)
    meta_2_label = models.CharField(max_length=80, blank=True)
    meta_3_value = models.CharField(max_length=40, blank=True)
    meta_3_label = models.CharField(max_length=80, blank=True)

    sections = StreamField(
        [
            (
                "seccion",
                blocks.StructBlock(
                    [
                        ("icono", blocks.CharBlock(required=False, max_length=60)),
                        ("titulo", blocks.CharBlock(required=True, max_length=120)),
                        ("texto", blocks.TextBlock(required=False)),
                    ]
                ),
            )
        ],
        blank=True,
        use_json_field=True,
    )

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("hero_tag"),
                FieldPanel("hero_title"),
                FieldPanel("hero_subtitle"),
                FieldPanel("hero_cta_text"),
                FieldPanel("hero_cta_url"),
                FieldPanel("hero_bg_color"),
                FieldPanel("hero_bg_image"),
            ],
            heading="Hero",
        ),
        MultiFieldPanel(
            [
                FieldPanel("hero_panel_image"),
                FieldPanel("hero_panel_title"),
                FieldPanel("hero_panel_text"),
                FieldPanel("hero_panel_footer"),
            ],
            heading="Panel destacado",
        ),
        MultiFieldPanel(
            [
                FieldPanel("meta_1_value"),
                FieldPanel("meta_1_label"),
                FieldPanel("meta_2_value"),
                FieldPanel("meta_2_label"),
                FieldPanel("meta_3_value"),
                FieldPanel("meta_3_label"),
            ],
            heading="Indicadores",
        ),
        FieldPanel("sections"),
    ]

    subpage_types = []

    def get_context(self, request):
        context = super().get_context(request)
        from landing.models import Noticia

        context["noticias"] = Noticia.objects.filter(estado="publicado").order_by(
            "-fecha_publicacion",
            "-id",
        )[:3]
        return context
