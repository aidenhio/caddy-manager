"""Single source of truth for block-type metadata -- label, Tabler color, icon
SVG, and description -- used across the Python views and every Jinja template
that references a block type. Exposed to templates via a Flask context
processor (see __init__.py). `primary` is reserved for generic UI, never a
block type.
"""
from markupsafe import Markup

BLOCK_TYPES = {
    "reverse_proxy": {
        "label": "Reverse Proxy",
        "color": "azure",
        "description": "Forward requests to a single backend service",
        "icon_paths": (
            "M9 14l-4 -4l4 -4",
            "M5 10h11a4 4 0 1 1 0 8h-1",
        ),
    },
    "redirect": {
        "label": "Redirect",
        "color": "purple",
        "description": "Send visitors from one URL to another",
        "icon_paths": (
            "M6 18v-6a3 3 0 0 1 3 -3h10l-4 -4m0 8l4 -4",
        ),
    },
    "load_balancer": {
        "label": "Load Balancer",
        "color": "pink",
        "description": "Distribute traffic across multiple upstream hosts",
        "icon_paths": (
            "M12 3v18",
            "M16 7l-4 -4l-4 4",
            "M16 11h5v5",
            "M8 11h-5v5",
            "M3 11l8.293 8.293c.453 .453 .707 1.067 .707 1.707",
            "M21 11l-8.293 8.293a2.4 2.4 0 0 0 -.707 1.707",
        ),
    },
    "static_site": {
        "label": "Static Site",
        "color": "lime",
        "description": "Serve static files straight from a directory",
        "icon_paths": (
            "M5 4h4l3 3h7a1 1 0 0 1 1 1v9a1 1 0 0 1 -1 1h-14a1 1 0 0 1 -1 -1v-12a1 1 0 0 1 1 -1",
        ),
    },
    "custom": {
        "label": "Custom",
        "color": "yellow",
        "description": "Write raw Caddyfile directives yourself",
        "icon_paths": (
            "M6 19a2 2 0 0 1 -2 -2v-4l-1 -1l1 -1v-4a2 2 0 0 1 2 -2",
            "M12 11.875l3 -1.687",
            "M12 11.875v3.375",
            "M12 11.875l-3 -1.687",
            "M12 11.875l3 1.688",
            "M12 8.5v3.375",
            "M12 11.875l-3 1.688",
            "M18 19a2 2 0 0 0 2 -2v-4l1 -1l-1 -1v-4a2 2 0 0 0 -2 -2",
        ),
    },
}

# Iteration order for anything that lists every block type (Quick Add
# dropdowns, the New Site Block modal, the Site Blocks by Type widget).
BLOCK_TYPE_ORDER = tuple(BLOCK_TYPES.keys())

DEFAULT_TYPE = "custom"


def _meta(block_type):
    return BLOCK_TYPES.get(block_type, BLOCK_TYPES[DEFAULT_TYPE])


def type_label(block_type):
    return _meta(block_type)["label"]


def type_color(block_type):
    return _meta(block_type)["color"]


def type_description(block_type):
    return _meta(block_type)["description"]


def type_icon(block_type, css_class="icon"):
    """The type's Tabler icon as a ready-to-render <svg> Markup string."""
    paths = _meta(block_type)["icon_paths"]
    path_tags = "".join(f'<path d="{d}" />' for d in paths)
    return Markup(
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        f'class="{css_class}">'
        f'<path stroke="none" d="M0 0h24v24H0z" fill="none" />{path_tags}</svg>'
    )
