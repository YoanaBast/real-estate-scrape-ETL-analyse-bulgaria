import re, time, httpx
"""
this tests the connection to imot.bg
"""
HEADERS = {"User-Agent": "personal-research-project (tursqkushta@gmail.com)"}
URLS = {
    "results": "https://www.imot.bg/obiavi/prodazhbi/grad-varna",
    "detail": "https://www.imot.bg/obiava-1j177817033718276-prodava-kashta-oblast-varna-gr-provadiya-shashkanite",
}

with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
    for name, url in URLS.items():
        r = client.get(url)
        r.encoding = 'windows-1251'
        html = r.text
        title = re.search(r"<title>(.*?)</title>", html, re.S)
        print(name, r.status_code, len(r.content), "bytes")
        print("  content-type:", r.headers.get("content-type"))
        print("  title:", title.group(1).strip()[:80] if title else None)
        print("  has class=cena:", 'class="cena"' in html)
        print("  listing cards:", len(re.findall(r'id="ida\w+"', html)))
        time.sleep(2)