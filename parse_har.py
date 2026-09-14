import json
import sys

STATIC_EXT = ('.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.woff', '.woff2',
              '.svg', '.ico', '.ttf', '.eot', '.map', '.mp4', '.webp', '.avif')


def load_har(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def main():
    if len(sys.argv) < 2:
        print('用法: python parse_har.py <xxx.har>')
        return
    path = sys.argv[1]
    har = load_har(path)
    entries = har.get('log', {}).get('entries', [])
    out_lines = []
    for i, e in enumerate(entries):
        req = e.get('request', {})
        res = e.get('response', {})
        url = req.get('url', '')
        if url.lower().endswith(STATIC_EXT):
            continue
        method = req.get('method', '')
        status = res.get('status', '')
        mime = res.get('content', {}).get('mimeType', '')
        post = req.get('postData', {})
        body = post.get('text', '') if post else ''
        resp_text = res.get('content', {}).get('text', '')
        lines = [
            '=' * 80,
            '[%d] %s %s' % (i, method, url),
            '    status=%s mime=%s' % (status, mime),
        ]
        if body:
            lines.append('    body=%s' % body[:600])
        if resp_text:
            lines.append('    resp=%s' % resp_text[:600])
        out_lines.extend(lines)
        print('\n'.join(lines))
    out_path = path.replace('.har', '_analysis.txt')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out_lines))
    print('\n已写出分析结果 ->', out_path)


if __name__ == '__main__':
    main()
