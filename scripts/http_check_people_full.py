import os
import json
import urllib.request

BASE = "http://127.0.0.1:6162"


def req(method, path, body=None, token=None):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=90) as resp:
        return json.loads(resp.read().decode())


token = req("POST", "/auth/login", {
    "email": "demo.unq.01@rizoma.local",
    "password": os.environ["RIZOMA_DEMO_PASSWORD"],
})["access_token"]
people = req("GET", "/api/users/people/complementary", token=token)
for i, p in enumerate(people, 1):
    camino = " -> ".join(x["label"] for x in p.get("camino", []))
    print(i, p["name"], "|", p.get("connection_type"), "|", p.get("score_final"), "| camino=", camino or "-")
