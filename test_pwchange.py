"""Forced first-login password-change tests."""
import json
import urllib.request
import urllib.error
from http.cookiejar import CookieJar

BASE = "http://127.0.0.1:8000"


class Client:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

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

    def get(self, p): return self.req("GET", p)
    def post(self, p, b=None): return self.req("POST", p, b)


def show(label, ok):
    print(f"{'PASS' if ok else 'FAIL'}  {label}")
    return ok


results = []

admin = Client()
admin.post("/api/admin/login", {"email": "owner@titleapp.example", "password": "ownerpw123"})
biz_id = json.loads(admin.post("/api/admin/businesses", {"name": "PW Test Co"})[1])["id"]
created = json.loads(admin.post("/api/admin/users",
    {"business_id": biz_id, "email": "frank@pw.example", "name": "Frank Fox"})[1])
temp_pw = created["password"]

frank = Client()
results.append(show("frank login with temp pw -> 200",
                    frank.post("/api/login", {"email": "frank@pw.example", "password": temp_pw})[0] == 200))
me = json.loads(frank.get("/api/me")[1])
results.append(show("/me shows must_change_password = true", me["must_change_password"] is True))
results.append(show("gated: /api/jobs -> 403 before change", frank.get("/api/jobs")[0] == 403))
results.append(show("gated: /api/generate -> 403 before change",
                    frank.post("/api/generate", {"job": {"parcel": "1"}})[0] == 403))
results.append(show("change to short pw -> 400", frank.post("/api/change-password", {"new_password": "short"})[0] == 400))
results.append(show("change to valid pw -> 200", frank.post("/api/change-password", {"new_password": "frankNewPass1"})[0] == 200))
me2 = json.loads(frank.get("/api/me")[1])
results.append(show("/me shows must_change_password = false after change", me2["must_change_password"] is False))
results.append(show("ungated now: /api/jobs -> 200", frank.get("/api/jobs")[0] == 200))

# old temp password no longer works; new one does
results.append(show("old temp pw rejected -> 401",
                    Client().post("/api/login", {"email": "frank@pw.example", "password": temp_pw})[0] == 401))
results.append(show("new pw logs in -> 200",
                    Client().post("/api/login", {"email": "frank@pw.example", "password": "frankNewPass1"})[0] == 200))

# admin reset re-arms the forced change
newtemp = json.loads(admin.post(f"/api/admin/users/{created['id']}/reset-password", {})[1])["password"]
frank2 = Client()
frank2.post("/api/login", {"email": "frank@pw.example", "password": newtemp})
me3 = json.loads(frank2.get("/api/me")[1])
results.append(show("admin reset re-arms must_change", me3["must_change_password"] is True))
results.append(show("gated again after reset: /api/jobs -> 403", frank2.get("/api/jobs")[0] == 403))

print(f"\n{sum(results)}/{len(results)} checks passed")
