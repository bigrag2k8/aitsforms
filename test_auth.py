"""End-to-end auth + multitenancy test using two independent cookie jars."""
import json
import urllib.request
import urllib.error
from http.cookiejar import CookieJar

BASE = "http://127.0.0.1:8000"


class Client:
    def __init__(self):
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )

    def req(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(BASE + path, data=data, method=method)
        if data:
            r.add_header("Content-Type", "application/json")
        try:
            resp = self.opener.open(r)
            return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def get(self, p):
        return self.req("GET", p)

    def post(self, p, body=None):
        return self.req("POST", p, body)


def show(label, ok):
    print(f"{'PASS' if ok else 'FAIL'}  {label}")
    return ok


results = []

anon = Client()
results.append(show("anon /api/jobs -> 401", anon.get("/api/jobs")[0] == 401))

alice = Client()
s, _ = alice.post("/api/login", {"email": "alice@buckeye.example", "password": "alicepw123"})
results.append(show("alice login -> 200", s == 200))
s, b = alice.get("/api/me")
me = json.loads(b)
results.append(show("alice /me name+business", me["user"]["name"] == "Alice Adams" and me["business"]["name"] == "Buckeye Title Co"))

# Alice creates a job
s, b = alice.post("/api/generate", {"job": {"parcel": "100", "suffix": "WD", "county": "Franklin",
                                            "chain": [{"grantor": "X", "grantee": "Y"}]}})
alice_job = json.loads(b)["job_id"]
results.append(show("alice generate -> job_id", bool(alice_job)))
s, b = alice.get("/api/jobs")
results.append(show("alice sees her job", any(j["id"] == alice_job for j in json.loads(b))))

# Carol (other business) — isolation
carol = Client()
carol.post("/api/login", {"email": "carol@capital.example", "password": "carolpw123"})
s, b = carol.get("/api/jobs")
results.append(show("carol does NOT see alice's job", all(j["id"] != alice_job for j in json.loads(b))))
results.append(show("carol GET alice's job -> 404", carol.get(f"/api/jobs/{alice_job}")[0] == 404))
results.append(show("carol download alice's file -> 404",
                    carol.get(f"/api/download/{alice_job}/RE46_100_WD.docx")[0] == 404))

# Inactive business blocks access
import backend.storage as storage  # noqa: E402
storage.set_business_active(2, False)
results.append(show("carol /me after deactivate -> 401", carol.get("/api/me")[0] == 401))
carol2 = Client()
s, _ = carol2.post("/api/login", {"email": "carol@capital.example", "password": "carolpw123"})
results.append(show("carol re-login while inactive -> 403", s == 403))
storage.set_business_active(2, True)  # restore

# Logout
results.append(show("alice logout -> 200", alice.post("/api/logout")[0] == 200))
results.append(show("alice /me after logout -> 401", alice.get("/api/me")[0] == 401))

print(f"\n{sum(results)}/{len(results)} checks passed")
