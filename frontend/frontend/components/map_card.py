import reflex as rx
from ..styles import TEXT_COLOR, TEXT_FONT, PAGE_COLOR
from ..state import MapState

def map_card() -> rx.Component:
    return rx.flex(
        # --- Map Rendering ---
        rx.box(
            
            rx.cond(
                MapState.is_generating,
                rx.center(
                    rx.spinner(color="blue", size="3"),
                    width="100%",
                    height="100%",
                ),
                # Use native iframe element
                rx.el.iframe(
                    src=MapState.map_url,
                    width="100%",
                    height="100%",
                    style={"border": "none"}
                ),
            ),
            width="100%",
            flex="1", # Take remaining space
            position="relative",
        ),

        # --- Bottom Bar ---
        rx.flex(
            # Left: Metodologia
            rx.hstack(
                rx.text(
                    "Metodologia",
                    color=TEXT_COLOR["branco"],
                    font_family=TEXT_FONT,
                    font_weight="bold",
                    font_size="14px",
                ),
                rx.icon(tag="eye", color=TEXT_COLOR["branco"], size=16),
                spacing="2",
                align_items="center",
                padding="12px",
                cursor="pointer",
                _hover={"opacity": 0.8},
            ),

            rx.spacer(),

            # Right: Version Selector
            rx.hstack(
                rx.text(
                    "Selecione a versão:",
                    color=TEXT_COLOR["branco"],
                    font_family=TEXT_FONT,
                    font_weight="bold",
                    font_size="14px",
                ),
                # Version Menu
                rx.menu.root(
                    rx.menu.trigger(
                        rx.button(
                            rx.hstack(
                                rx.text(MapState.current_version, font_weight="bold"),
                                rx.icon(tag="chevron-up", size=16), # Arrow pointing up indicating menu opens up
                                spacing="2",
                                align_items="center",
                            ),
                            bg="rgba(255, 255, 255, 0.2)",
                            color=TEXT_COLOR["branco"],
                            font_family=TEXT_FONT,
                            font_size="14px",
                            padding="12px 16px",
                            border_radius="20px",
                            _hover={"bg": "rgba(255, 255, 255, 0.3)"},
                        ),
                    ),
                    rx.menu.content(
                        rx.menu.item("v8.0", on_click=MapState.set_version("8.0")),
                        rx.menu.item("v8.1", on_click=MapState.set_version("8.1")),
                        rx.menu.item("v8.2", on_click=MapState.set_version("8.2")),
                        rx.menu.item("v8.3", on_click=MapState.set_version("8.3")),
                        bg=PAGE_COLOR["branco"],
                        color=TEXT_COLOR["azul_brasil"],
                        font_family=TEXT_FONT,
                        border_radius="8px",
                        box_shadow="0px 4px 12px rgba(0, 0, 0, 0.1)",
                        side="top", # Opens upwards
                        align="end",
                    ),
                ),
                
                spacing="3",
                align_items="center",
                padding="8px",
            ),
            
            width="100%",
            bg=PAGE_COLOR["azul_brasil"],
            justify="between",
            align="center",
            z_index="10",
        ),

        direction="column",
        width="100%",
        height="700px", # Fixed total height
        border_radius="8px",
        overflow="hidden",
        box_shadow="0px 4px 12px rgba(0, 0, 0, 0.1)",
        on_mount=MapState.generate_map,
    )
