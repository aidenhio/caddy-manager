"""Block type -> Tabler color, exposed to templates as the `type_color()`
Jinja global. `primary` is reserved for generic UI, never a block type."""

TYPE_COLORS = {
    "reverse_proxy": "azure",
    "redirect": "purple",
    "load_balancer": "pink",
    "static_site": "lime",
    "custom": "yellow",
}
DEFAULT_TYPE_COLOR = TYPE_COLORS["custom"]


def type_color(block_type):
    return TYPE_COLORS.get(block_type, DEFAULT_TYPE_COLOR)
