"""Block type colors -- the single place block-type -> Tabler color is
defined. Templates get this as the `type_color(block_type)` Jinja global
(registered in caddy_manager/__init__.py), so every page/badge/button stays
in sync if a color ever changes here. `primary` is reserved for generic UI
elements (nav, page buttons, etc.) and is never used to represent a block
type.
"""

TYPE_COLORS = {
    "reverse_proxy": "azure",
    "redirect": "purple",
    "load_balancer": "pink",
    "custom": "yellow",
}
DEFAULT_TYPE_COLOR = TYPE_COLORS["custom"]


def type_color(block_type):
    return TYPE_COLORS.get(block_type, DEFAULT_TYPE_COLOR)
