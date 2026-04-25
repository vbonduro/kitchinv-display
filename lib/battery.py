"""Battery voltage reader for Pico W via VSYS ADC (pin 29)."""


def read_pct() -> "int | None":
    """Return battery percentage 0-100, or None if ADC is unavailable.

    VSYS uses a 1/3 voltage divider; assumes a LiPo cell (3.0 V = 0%, 4.2 V = 100%).
    """
    try:
        import machine  # type: ignore[import]

        adc = machine.ADC(29)
        raw = adc.read_u16()
        voltage = raw * 3.3 * 3 / 65535
        return max(0, min(100, int((voltage - 3.0) / 1.2 * 100)))
    except Exception:
        return None
