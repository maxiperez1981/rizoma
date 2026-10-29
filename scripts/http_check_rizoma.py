import os
import json
import time
import urllib.request


BASE = "http://127.0.0.1:6162"


def request(method, path, body=None, token=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload, time.time() - t0


token_data, dt = request("POST", "/auth/login", {
    "email": "demo.unq.01@rizoma.local",
    "password": os.environ["RIZOMA_DEMO_PASSWORD"],
})
token = token_data["access_token"]
print("login_s", round(dt, 3))

me, dt = request("GET", "/api/users/me", token=token)
print("me", me["name"], me["profile_completeness"], "s=", round(dt, 3))

graph, dt = request("GET", "/api/users/me/rizoma-grafo", token=token)
print("graph nodes", len(graph.get("nodes", [])), "edges", len(graph.get("edges", [])), "s=", round(dt, 3))

paths, dt = request("GET", "/api/users/me/rizoma-caminos?limite=8", token=token)
print("paths", len(paths), "s=", round(dt, 3))
for item in paths[:3]:
    print("path", item["score"], " -> ".join(p["label"] for p in item["camino"]))

people, dt = request("GET", "/api/users/people/complementary", token=token)
print("people", len(people), "s=", round(dt, 3))
for item in people[:5]:
    print("person", item["name"], item.get("connection_type"), item.get("score_final"), "camino", bool(item.get("camino")))
