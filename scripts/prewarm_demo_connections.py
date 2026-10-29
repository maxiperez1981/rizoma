import os
import json
import time
import urllib.request

BASE = "http://127.0.0.1:6162"
PASSWORD = os.environ["RIZOMA_DEMO_PASSWORD"]
EMAILS = [
    "demo.unq.01@rizoma.local",
    "demo.unq.03@rizoma.local",
    "demo.unq.16@rizoma.local",
    "demo.unq.25@rizoma.local",
    "demo.unq.43@rizoma.local",
]


def req(method, path, body=None, token=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    t0 = time.time()
    with urllib.request.urlopen(r, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload, time.time() - t0


for email in EMAILS:
    token, _ = req("POST", "/auth/login", {"email": email, "password": PASSWORD})
    people, dt = req("GET", "/api/users/people/complementary", token=token["access_token"])
    indirect = sum(1 for p in people if p.get("camino"))
    print(email, "connections=", len(people), "indirect=", indirect, "seconds=", round(dt, 2))
