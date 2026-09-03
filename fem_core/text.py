from __future__ import annotations


def decode_engineering_text(content: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return content.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise AssertionError("latin-1 decoding should always succeed")
