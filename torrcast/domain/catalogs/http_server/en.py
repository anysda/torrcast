"""English captions of the http_server cluster."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Return the English catalog of the http_server cluster."""
    return {
        "http_server.no_route_to_tv": "no route to the TV {tv}",
        "http_server.address_unset": "(address not set)",
        "http_server.cert_unreadable": "cannot read the certificate {path}: {reason}",
        "http_server.port_unavailable": "port {port} is busy or unavailable: {reason}",
        "http_server.trace_request": "request {name}{span} - waited {waited} s - {got}",
        "http_server.trace_sent": "sent {name} - {size} MB in {seconds} s - {rate} Mbit/s",
        "http_server.trace_megabytes": "{size} MB",
    }
