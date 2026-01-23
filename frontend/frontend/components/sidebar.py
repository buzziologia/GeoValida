import reflex as rx

def sidebar() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.heading("Menu", size="5", margin_bottom="1em"),
            rx.link("Home", href="/", color="white", padding="0.5em", width="100%"),
            rx.link("Analytics", href="/analytics", color="white", padding="0.5em", width="100%"),
            rx.link("Settings", href="/settings", color="white", padding="0.5em", width="100%"),
            padding="1em",
            height="100vh",
            bg="black",
            width="250px",
        )
    )
