"""Read only PCM inline parts; avoid SDK convenience-property mixed-part warnings."""
def response_pcm(response):
    content = getattr(response, 'server_content', None)
    turn = getattr(content, 'model_turn', None) if content else None
    parts = getattr(turn, 'parts', None) if turn else None
    if parts is not None:
        chunks = []
        for part in parts:
            blob = getattr(part, 'inline_data', None)
            mime = str(getattr(blob, 'mime_type', '') or '').lower()
            data = getattr(blob, 'data', None)
            if mime.startswith('audio/pcm') and isinstance(data, (bytes, bytearray, memoryview)):
                chunks.append(bytes(data))
        return b''.join(chunks)
    # Test/older adapter compatibility only; do not touch a provider .data property.
    data = getattr(response, '__dict__', {}).get('data')
    return bytes(data) if isinstance(data, (bytes, bytearray, memoryview)) else b''
