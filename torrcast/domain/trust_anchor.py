"""Предметная единица trust_anchor приёмника."""


def trust_anchor(cert: str) -> str:
    """Чему приёмник должен доверять, проверяя нашу раздачу.

    Серт выпущен настоящим CA (LE) — доверяем **системному хранилищу**: ровно
    так его проверит ТВ, и только такая проверка закрывает требование Chromecast к
    доверенному HTTPS. Серт self-signed (дефолт `install.sh` до доставки LE) — доверяем
    ему самому: иначе проверять нечем.

    Различаем по файлу: OpenSSL берёт в доверенные только CA-сертификаты, поэтому у
    self-signed остаётся он сам (subject == issuer), а у цепочки LE — промежуточный
    (subject != issuer), листа в списке нет вовсе.
    """
    import ssl

    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=cert)
        anchors = context.get_ca_certs()
    except (OSError, ssl.SSLError):
        return cert
    if len(anchors) == 1 and anchors[0].get("subject") == anchors[0].get("issuer"):
        return cert
    return ""
